import logging
import asyncio
import hashlib
import json
import time
from datetime import timedelta
from urllib.parse import quote

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import AROMA_LINK_SSL, DOMAIN

_LOGGER = logging.getLogger(__name__)
AROMA_LINK_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/91.0.4472.124 Safari/537.36"
)


class AromaLinkAuthCoordinator(DataUpdateCoordinator):
    """Coordinator for handling authentication and session management."""

    def __init__(self, hass, username, password, user_id=None):
        """Initialize the auth coordinator."""
        self.username = username
        self.password = password
        self.jsessionid = None
        self.access_token = None
        self.refresh_token = None
        self.language_code = "EN"
        self.user_id = user_id
        self.session = async_get_clientsession(hass)
        self._last_login_time = 0

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_auth",
            # Check auth every 15 minutes
            update_interval=timedelta(minutes=15),
        )

    async def _async_update_data(self):
        """Fetch authentication data."""
        # Simply ensure login is valid
        await self._ensure_login()
        return {
            "jsessionid": self.jsessionid,
            "access_token": self.access_token,
            "user_id": self.user_id,
            "last_login": self._last_login_time,
        }

    async def _ensure_login(self):
        """Ensure we have a valid session, login if needed."""
        current_time = time.time()
        session_age = current_time - self._last_login_time

        has_web_session = self.jsessionid is not None and not self.jsessionid.startswith("temp_")
        has_app_session = self.access_token is not None and self.user_id is not None

        if not has_web_session and self.jsessionid and self.jsessionid.startswith("temp_"):
            has_web_session = True

        if not (has_web_session or has_app_session) or session_age > 1200:
            _LOGGER.debug(
                "Session expired, temporary, or not established. Attempting login.")
            login_success = await self._login()
            if not login_success:
                _LOGGER.error("Failed to login during ensure_login.")
                raise UpdateFailed(
                    "Authentication failed, cannot update auth state.")
        return True

    async def _login(self):
        """Login to Aroma-Link web and app APIs."""
        app_login_success = await self._login_app()
        web_login_success = await self._login_web()

        if app_login_success or web_login_success:
            self._last_login_time = time.time()
            if app_login_success:
                _LOGGER.info("Successfully authenticated against Aroma-Link app API.")
            if web_login_success:
                _LOGGER.info("Successfully authenticated against Aroma-Link web API.")
            return True

        return False

    async def _login_web(self):
        """Login to the Aroma-Link website and capture the session cookie."""
        login_url = "https://www.aroma-link.com/login"
        data = {"username": self.username, "password": self.password}
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.aroma-link.com",
            "Referer": "https://www.aroma-link.com/",
            "User-Agent": AROMA_LINK_USER_AGENT,
        }

        try:
            _LOGGER.debug(
                "Attempting initial GET to aroma-link.com for cookies.")
            async with self.session.get(
                "https://www.aroma-link.com/",
                timeout=10,
                ssl=AROMA_LINK_SSL,
            ) as initial_response:
                initial_response.raise_for_status()
                _LOGGER.debug(
                    f"Initial GET successful (status {initial_response.status}).")

            _LOGGER.debug(
                f"Attempting login to {login_url} as {self.username}.")
            async with self.session.post(
                login_url,
                data=data,
                headers=headers,
                timeout=10,
                ssl=AROMA_LINK_SSL,
            ) as response:
                response_text = await response.text()
                _LOGGER.debug(f"Login response status: {response.status}")
                self._update_auth_artifacts(response=response, response_text=response_text)

                if response.status == 200:
                    jsessionid_found = await self._extract_jsessionid(response, response_text)

                    if jsessionid_found:
                        self.jsessionid = jsessionid_found
                        return True
                    else:
                        _LOGGER.error(
                            "No JSESSIONID cookie found in response.")
                        return False
                else:
                    _LOGGER.error(
                        f"Login failed with status code: {response.status}.")
                    return False
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout during login process.")
            return False
        except Exception as e:
            _LOGGER.error(f"Web login error: {e}", exc_info=True)
            return False

    async def _login_app(self):
        """Authenticate against the Aroma-Link mobile app endpoints."""
        hashed_password = hashlib.md5(self.password.encode("utf-8")).hexdigest()
        base_headers = {
            "User-Agent": AROMA_LINK_USER_AGENT,
        }

        try:
            login_form = aiohttp.FormData()
            login_form.add_field("userName", self.username)
            login_form.add_field("password", hashed_password)
            async with self.session.post(
                "http://www.aroma-link.com/v1/app/user/newLogin",
                headers=base_headers,
                data=login_form,
                timeout=15,
            ) as response:
                response_text = await response.text()
                if response.status != 200:
                    _LOGGER.error("App login failed with status code: %s.", response.status)
                    return False
                self._update_auth_artifacts(response=response, response_text=response_text)

            token_form = aiohttp.FormData()
            token_form.add_field("userName", self.username)
            token_form.add_field("password", hashed_password)
            async with self.session.post(
                "http://www.aroma-link.com/v2/app/token",
                headers=base_headers,
                data=token_form,
                timeout=15,
            ) as response:
                response_text = await response.text()
                if response.status != 200:
                    _LOGGER.error("App token request failed with status code: %s.", response.status)
                    return False
                payload = self._parse_json_response(response_text, "app token")
                if payload is None:
                    return False
                self._update_auth_artifacts(response=response, payload=payload)
                refresh_token = self._find_nested_value(
                    payload,
                    {"refreshtoken", "refresh_token"},
                )
                if isinstance(refresh_token, str) and refresh_token:
                    self.refresh_token = refresh_token

            if self.refresh_token:
                refresh_form = aiohttp.FormData()
                refresh_form.add_field("refreshToken", self.refresh_token)
                async with self.session.post(
                    "http://www.aroma-link.com/v2/app/refresh/token",
                    headers=base_headers,
                    data=refresh_form,
                    timeout=15,
                ) as response:
                    response_text = await response.text()
                    if response.status == 200:
                        payload = self._parse_json_response(response_text, "refresh token")
                        if payload is not None:
                            self._update_auth_artifacts(response=response, payload=payload)
                    else:
                        _LOGGER.warning(
                            "App refresh token request failed with status code: %s.",
                            response.status,
                        )

            if self.access_token is None:
                _LOGGER.error("App auth did not return an access token.")
                return False

            await self._fetch_app_user_profile()
            return self.user_id is not None
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout during app login process.")
            return False
        except Exception as e:
            _LOGGER.error(f"App login error: {e}", exc_info=True)
            return False

    async def _extract_jsessionid(self, response, response_text):
        """Extract JSESSIONID from various sources."""
        jsessionid = None

        # Method 1: Try to get JSESSIONID from cookie jar
        filtered_cookies = self.session.cookie_jar.filter_cookies(response.url)

        if "JSESSIONID" in filtered_cookies:
            jsessionid_morsel = filtered_cookies["JSESSIONID"]
            jsessionid = jsessionid_morsel.value
            _LOGGER.debug(
                f"Found JSESSIONID in cookie jar: {jsessionid[:5]}...")
            return jsessionid

        # Method 2: If not found in jar, check response headers
        if 'Set-Cookie' in response.headers:
            cookie_header = response.headers['Set-Cookie']
            if 'JSESSIONID=' in cookie_header:
                try:
                    start = cookie_header.index('JSESSIONID=') + 11
                    end = cookie_header.index(
                        ';', start) if ';' in cookie_header[start:] else len(cookie_header)
                    jsessionid = cookie_header[start:end]
                    _LOGGER.debug(
                        f"Extracted JSESSIONID from header: {jsessionid[:5]}...")
                    return jsessionid
                except Exception as e:
                    _LOGGER.error(
                        f"Error extracting JSESSIONID from header: {e}")

        # Method 3: Check if login was successful from response text
        if "success" in response_text.lower():
            _LOGGER.warning(
                "Login appears successful based on response text, but no JSESSIONID found. Using temporary ID.")
            jsessionid = f"temp_login_success_{time.time()}"
            return jsessionid

        return None

    def _update_auth_artifacts(self, response=None, response_text=None, payload=None):
        """Extract token-like auth artifacts from responses when present."""
        header_names = ("Access-Token", "access-token", "accessToken", "Authorization")
        cookie_names = ("accessToken", "access_token", "token")
        token_keys = {"accesstoken", "access_token", "token", "authorization"}
        user_keys = {"userid", "user_id", "uid"}

        if response is not None:
            for header_name in header_names:
                token = response.headers.get(header_name)
                if token:
                    if header_name.lower() == "authorization" and token.lower().startswith("bearer "):
                        token = token[7:]
                    self.access_token = token
                    break

            filtered_cookies = self.session.cookie_jar.filter_cookies(response.url)
            for cookie_name in cookie_names:
                if cookie_name in filtered_cookies:
                    self.access_token = filtered_cookies[cookie_name].value
                    break

        if payload is None and response_text:
            try:
                payload = json.loads(response_text)
            except Exception:
                payload = None

        if payload is not None:
            token = self._find_nested_value(payload, token_keys)
            if isinstance(token, str) and token:
                if token.lower().startswith("bearer "):
                    token = token[7:]
                self.access_token = token

            user_id = self._find_nested_value(payload, user_keys)
            if user_id is not None:
                self.user_id = str(user_id)

        if self.access_token:
            _LOGGER.debug("Captured Aroma-Link access token from auth response.")
        if self.user_id:
            _LOGGER.debug("Captured Aroma-Link user ID %s from auth response.", self.user_id)

    def _find_nested_value(self, value, keys):
        """Search nested JSON-like structures for the first matching key."""
        if isinstance(value, dict):
            for key, nested_value in value.items():
                if key.replace("-", "_").lower() in keys:
                    return nested_value
                found = self._find_nested_value(nested_value, keys)
                if found is not None:
                    return found

        if isinstance(value, list):
            for item in value:
                found = self._find_nested_value(item, keys)
                if found is not None:
                    return found

        return None

    def _app_auth_headers(self):
        """Build headers for app-authenticated requests."""
        if not self.access_token:
            return None

        return {
            "User-Agent": AROMA_LINK_USER_AGENT,
            "Access-Token": self.access_token,
            "Authorization": f"Bearer {self.access_token}",
        }

    async def _fetch_app_user_profile(self):
        """Fetch the current app user profile to capture the stable user ID."""
        headers = self._app_auth_headers()
        if headers is None:
            return

        if not self.user_id:
            _LOGGER.debug("Skipping app user profile fetch because no user ID is known yet.")
            return

        profile_url = (
            f"http://www.aroma-link.com/v1/app/user/{self.user_id}"
            f"?email={quote(self.username)}&language={self.language_code}"
        )

        try:
            async with self.session.get(profile_url, headers=headers, timeout=15) as response:
                response_text = await response.text()
                if response.status != 200:
                    _LOGGER.warning(
                        "App user profile request failed with status code: %s.",
                        response.status,
                    )
                    return

                payload = self._parse_json_response(response_text, "user profile")
                if payload is not None:
                    self._update_auth_artifacts(response=response, payload=payload)
        except Exception as err:
            _LOGGER.warning("Failed to fetch app user profile: %s", err)

    def _parse_json_response(self, response_text, context):
        """Parse JSON responses from the app endpoints."""
        try:
            return json.loads(response_text)
        except json.JSONDecodeError as err:
            _LOGGER.error("Failed to parse %s response as JSON: %s", context, err)
            return None
