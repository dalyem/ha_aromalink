import voluptuous as vol
import logging
import json
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import aiohttp

from .const import (
    AROMA_LINK_SSL,
    AROMA_LINK_TRACE_REQUESTS,
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICE_ID,
    CONF_POLL_INTERVAL_SECONDS,
    DEFAULT_POLL_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


def _log_request(method, url, extra=None):
    """Temporarily log outgoing Aroma-Link requests during config flow."""
    if not AROMA_LINK_TRACE_REQUESTS:
        return

    suffix = f" | {extra}" if extra else ""
    _LOGGER.warning("Aroma-Link request: %s %s%s", method, url, suffix)


def _log_response(method, url, status):
    """Temporarily log Aroma-Link responses during config flow."""
    if not AROMA_LINK_TRACE_REQUESTS:
        return

    _LOGGER.warning("Aroma-Link response: %s %s -> %s", method, url, status)

class AromaLinkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Aroma-Link."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow."""
        return AromaLinkOptionsFlowHandler(config_entry)

    def __init__(self):
        """Initialize the config flow."""
        self._username = None
        self._password = None
        self._jsessionid = None
        self._devices = []
        self._reauth_entry = None
        
    async def async_step_user(self, user_input=None):
        """Handle the initial step - username and password."""
        errors = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            
            _LOGGER.debug(f"Setting up with username: {username}")
            
            # Try to authenticate
            session, jsessionid, devices = await self._authenticate(username, password)
            
            if jsessionid:
                self._username = username
                self._password = password
                self._jsessionid = jsessionid
                self._devices = devices
                
                # Create a unique ID based on the username
                await self.async_set_unique_id(username)
                self._abort_if_unique_id_configured()
                
                # If we have devices, create entry with all devices
                if devices:
                    device_names = [d.get("deviceName", f"Device {d['deviceId']}") for d in devices]
                    user_id = next(
                        (
                            str(device.get("userId") or device.get("user_id"))
                            for device in devices
                            if device.get("userId") or device.get("user_id")
                        ),
                        None,
                    )
                    _LOGGER.info(f"Adding {len(devices)} devices: {device_names}")
                    
                    return self.async_create_entry(
                        title=f"Aroma-Link ({username})",
                        data={
                            CONF_USERNAME: username,
                            CONF_PASSWORD: password,
                            "user_id": user_id,
                            "devices": [
                                {
                                    CONF_DEVICE_ID: str(device["deviceId"]),
                                    "device_name": device.get("deviceName", f"Device {device['deviceId']}"),
                                    "user_id": str(device.get("userId")) if device.get("userId") else None,
                                }
                                for device in devices
                            ]
                        }
                    )
                else:
                    # No devices found, show an error
                    errors["base"] = "no_devices"
            else:
                errors["base"] = "cannot_connect"

        # Show the initial form for username/password
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )
        
    async def _authenticate(self, username, password):
        """Authenticate with Aroma-Link API and retrieve device list.
        
        Returns:
            tuple: (session, jsessionid, devices)
            - session: The authenticated aiohttp ClientSession
            - jsessionid: The JSESSIONID cookie value if authentication successful, None otherwise
            - devices: List of discovered devices, or empty list if none found
        """
        session = async_get_clientsession(self.hass)
        jsessionid = None
        devices = []
        
        login_url = "https://www.aroma-link.com/login"
        
        data = {
            "username": username,
            "password": password
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.aroma-link.com",
            "Referer": "https://www.aroma-link.com/"
        }
        
        try:
            # First, attempt login to get JSESSIONID
            _LOGGER.debug(f"Attempting login for {username}")
            _log_request("POST", login_url, extra="config_flow=true")
            async with session.post(
                login_url,
                data=data,
                headers=headers,
                ssl=AROMA_LINK_SSL,
            ) as response:
                _log_response("POST", login_url, response.status)
                _LOGGER.debug(f"Login response status: {response.status}")
                
                response_text = await response.text()
                _LOGGER.debug(f"Login response body: {response_text[:200]}...")
                
                if response.status == 200:
                    # Try multiple methods to get the JSESSIONID cookie
                    jsessionid = await self._extract_jsessionid(session, response, response_text, username)
                    
                    if jsessionid:
                        _LOGGER.info(f"Successfully logged in as {username}")
                        
                        # Now fetch device list
                        _LOGGER.debug("Fetching device list")
                        devices = await self._fetch_device_list(session, jsessionid)
                        
                        _LOGGER.info(f"Found {len(devices)} devices for {username}")
                        return session, jsessionid, devices
                    else:
                        _LOGGER.error("No JSESSIONID cookie found. Authentication failed.")
                        
                        # Check response for potential error messages
                        if "error" in response_text.lower() or "invalid" in response_text.lower():
                            try:
                                # Try to extract error message from response
                                error_msg = "Unknown error"
                                if "msg" in response_text:
                                    try:
                                        json_resp = json.loads(response_text)
                                        if "msg" in json_resp:
                                            error_msg = json_resp["msg"]
                                    except:
                                        pass
                                _LOGGER.error(f"Server returned error: {error_msg}")
                            except:
                                _LOGGER.error("Could not parse error message from response")
                else:
                    _LOGGER.error(f"Login failed with status code: {response.status}")
        except aiohttp.ClientError as e:
            _LOGGER.error(f"Network error while authenticating: {e}")
        except json.JSONDecodeError as e:
            _LOGGER.error(f"Error parsing JSON response: {e}")
        except Exception as e:
            _LOGGER.error(f"Unexpected error during authentication: {e}", exc_info=True)
        
        return session, None, []
        
    async def _extract_jsessionid(self, session, response, response_text, username):
        """Extract JSESSIONID using multiple methods."""
        jsessionid = None
        
        # Method 1: Try to get JSESSIONID from cookie jar
        filtered_cookies = session.cookie_jar.filter_cookies(response.url)
        _LOGGER.debug(f"Filtered cookies from jar: {filtered_cookies}")
        
        if "JSESSIONID" in filtered_cookies:
            jsessionid_morsel = filtered_cookies["JSESSIONID"]
            jsessionid = jsessionid_morsel.value
            _LOGGER.debug(f"Found JSESSIONID in cookie jar: {jsessionid[:5]}...")
            return jsessionid
        
        # Method 2: If not found in jar, check response headers
        if 'Set-Cookie' in response.headers:
            _LOGGER.debug(f"Looking for JSESSIONID in Set-Cookie header")
            cookie_header = response.headers['Set-Cookie']
            if 'JSESSIONID=' in cookie_header:
                try:
                    start = cookie_header.index('JSESSIONID=') + 11
                    end = cookie_header.index(';', start) if ';' in cookie_header[start:] else len(cookie_header)
                    jsessionid = cookie_header[start:end]
                    _LOGGER.debug(f"Extracted JSESSIONID from header: {jsessionid[:5]}...")
                    return jsessionid
                except Exception as e:
                    _LOGGER.error(f"Error extracting JSESSIONID from header: {e}")
        
        # Method 3: Check if login was successful from response text
        if "success" in response_text.lower():
            _LOGGER.warning("Login appears successful based on response text, but no JSESSIONID found. Using temporary ID.")
            jsessionid = f"temp_login_success_{username}"
            return jsessionid
            
        return None
        
    async def _fetch_device_list(self, session, jsessionid):
        """Fetch the list of devices for the authenticated user."""
        language_code = "EN"
        device_list_url = "https://www.aroma-link.com/device/list/v2?limit=10&offset=0&selectUserId=&groupId=&deviceName=&imei=&deviceNo=&workStatus=&continentId=&countryId=&areaId=&sort=&order="
        
        devices = []
        
        try:
            # First do an initial page load to ensure cookies are set properly
            try:
                _LOGGER.debug("Making initial request to device page")
                _log_request("GET", "https://www.aroma-link.com/device/list", extra="config_flow=true")
                async with session.get(
                    "https://www.aroma-link.com/device/list",
                    timeout=10,
                    ssl=AROMA_LINK_SSL,
                ) as init_response:
                    _log_response("GET", "https://www.aroma-link.com/device/list", init_response.status)
                    _LOGGER.debug(f"Initial page request status: {init_response.status}")
            except Exception as e:
                _LOGGER.warning(f"Initial page request failed, but continuing: {e}")
            
            device_headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "https://www.aroma-link.com",
                "Referer": "https://www.aroma-link.com/device/list",
                "Cookie": f"languagecode={language_code}; JSESSIONID={jsessionid}"
            }
            
            _LOGGER.debug(f"Fetching device list with URL: {device_list_url}")
            _log_request("GET", device_list_url, extra="config_flow=true")
            async with session.get(
                device_list_url,
                headers=device_headers,
                ssl=AROMA_LINK_SSL,
            ) as device_response:
                _log_response("GET", device_list_url, device_response.status)
                _LOGGER.debug(f"Device list response status: {device_response.status}")
                
                if device_response.status == 200:
                    device_response_text = await device_response.text()
                    _LOGGER.debug(f"Device list response (first 200 chars): {device_response_text[:200]}")
                    
                    try:
                        device_data = json.loads(device_response_text)
                        
                        if "rows" in device_data and device_data["rows"]:
                            device_ids = [d.get("deviceId") for d in device_data["rows"]]
                            _LOGGER.info(f"Found devices: {device_ids}")
                            return device_data["rows"]
                        else:
                            _LOGGER.warning("No devices found in the account")
                    except json.JSONDecodeError as e:
                        _LOGGER.error(f"Failed to parse device list response as JSON: {e}")
                else:
                    _LOGGER.error(f"Device list request failed with status: {device_response.status}")
        except Exception as e:
            _LOGGER.error(f"Error fetching device list: {e}", exc_info=True)
            
        return devices


class AromaLinkOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Aroma-Link options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_POLL_INTERVAL_SECONDS,
            DEFAULT_POLL_INTERVAL_SECONDS,
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_INTERVAL_SECONDS,
                        default=current_interval,
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                }
            ),
        )
