import logging
import asyncio
import time
from datetime import timedelta

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class AromaLinkAuthCoordinator(DataUpdateCoordinator):
    """Coordinator for handling authentication and session management."""

    def __init__(self, hass, username, password):
        """Initialize the auth coordinator."""
        self.username = username
        self.password = password
        self.jsessionid = None
        self.language_code = "EN"
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
        return {"jsessionid": self.jsessionid, "last_login": self._last_login_time}

    async def _ensure_login(self):
        """Ensure we have a valid session, login if needed."""
        current_time = time.time()
        session_age = current_time - self._last_login_time

        # 20 min or temp ID
        if self.jsessionid is None or self.jsessionid.startswith("temp_") or session_age > 1200:
            _LOGGER.debug(
                "Session expired, temporary, or not established. Attempting login.")
            login_success = await self._login()
            if not login_success:
                _LOGGER.error("Failed to login during ensure_login.")
                raise UpdateFailed(
                    "Authentication failed, cannot update auth state.")
        return True

    async def _login(self):
        """Login to Aroma-Link and get session ID."""
        login_url = "https://www.aroma-link.com/login"
        data = {"username": self.username, "password": self.password}
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.aroma-link.com",
            "Referer": "https://www.aroma-link.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        try:
            _LOGGER.debug(
                "Attempting initial GET to aroma-link.com for cookies.")
            async with self.session.get("https://www.aroma-link.com/", timeout=10) as initial_response:
                initial_response.raise_for_status()
                _LOGGER.debug(
                    f"Initial GET successful (status {initial_response.status}).")

            _LOGGER.debug(
                f"Attempting login to {login_url} as {self.username}.")
            async with self.session.post(login_url, data=data, headers=headers, timeout=10) as response:
                response_text = await response.text()
                _LOGGER.debug(f"Login response status: {response.status}")

                if response.status == 200:
                    jsessionid_found = await self._extract_jsessionid(response, response_text)

                    if jsessionid_found:
                        self.jsessionid = jsessionid_found
                        self._last_login_time = time.time()
                        _LOGGER.info(
                            f"Successfully logged in as {self.username}.")
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
            _LOGGER.error(f"Login error: {e}", exc_info=True)
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
