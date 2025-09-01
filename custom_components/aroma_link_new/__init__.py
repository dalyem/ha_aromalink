"""The Aroma-Link integration."""
import logging
import asyncio
from datetime import timedelta
import time
import json

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import voluptuous as vol

from .const import (
    DOMAIN,
    CONF_DEVICE_ID,
    SERVICE_SET_SCHEDULER,
    SERVICE_RUN_DIFFUSER,
    ATTR_DURATION,
    ATTR_DIFFUSE_TIME,
    ATTR_WORK_DURATION,
    ATTR_PAUSE_DURATION,
    ATTR_WEEK_DAYS,
    DEFAULT_DIFFUSE_TIME,
    DEFAULT_WORK_DURATION,
    DEFAULT_PAUSE_DURATION,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch", "button", "number", "sensor"]

SET_SCHEDULER_SCHEMA = vol.Schema({
    vol.Required(ATTR_WORK_DURATION): vol.All(vol.Coerce(int), vol.Range(min=5, max=900)),
    vol.Optional(ATTR_PAUSE_DURATION): vol.All(vol.Coerce(int), vol.Range(min=5, max=900)),
    vol.Optional(ATTR_WEEK_DAYS): vol.All(
        cv.ensure_list, [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))]
    ),
    vol.Optional("device_id"): cv.string,
})

RUN_DIFFUSER_SCHEMA = vol.Schema({
    vol.Optional(ATTR_WORK_DURATION): vol.All(vol.Coerce(int), vol.Range(min=5, max=900)),
    vol.Optional(ATTR_PAUSE_DURATION): vol.All(vol.Coerce(int), vol.Range(min=5, max=900)),
    vol.Optional("device_id"): cv.string,
})


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Aroma-Link component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


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
            update_interval=timedelta(minutes=15),  # Check auth every 15 minutes
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
        
        if self.jsessionid is None or self.jsessionid.startswith("temp_") or session_age > 1200:  # 20 min or temp ID
            _LOGGER.debug("Session expired, temporary, or not established. Attempting login.")
            login_success = await self._login()
            if not login_success:
                _LOGGER.error("Failed to login during ensure_login.")
                raise UpdateFailed("Authentication failed, cannot update auth state.")
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
            _LOGGER.debug("Attempting initial GET to aroma-link.com for cookies.")
            async with self.session.get("https://www.aroma-link.com/", timeout=10) as initial_response:
                initial_response.raise_for_status() 
                _LOGGER.debug(f"Initial GET successful (status {initial_response.status}).")

            _LOGGER.debug(f"Attempting login to {login_url} as {self.username}.")
            async with self.session.post(login_url, data=data, headers=headers, timeout=10) as response:
                response_text = await response.text()
                _LOGGER.debug(f"Login response status: {response.status}")

                if response.status == 200:
                    jsessionid_found = await self._extract_jsessionid(response, response_text)
                    
                    if jsessionid_found:
                        self.jsessionid = jsessionid_found
                        self._last_login_time = time.time()
                        _LOGGER.info(f"Successfully logged in as {self.username}.")
                        return True
                    else:
                        _LOGGER.error("No JSESSIONID cookie found in response.")
                        return False
                else:
                    _LOGGER.error(f"Login failed with status code: {response.status}.")
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
            _LOGGER.debug(f"Found JSESSIONID in cookie jar: {jsessionid[:5]}...")
            return jsessionid
        
        # Method 2: If not found in jar, check response headers
        if 'Set-Cookie' in response.headers:
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
            jsessionid = f"temp_login_success_{time.time()}"
            return jsessionid
            
        return None


class AromaLinkDeviceCoordinator(DataUpdateCoordinator):
    """Coordinator for handling device data and control."""
    
    def __init__(self, hass, auth_coordinator, device_id, device_name):
        """Initialize the device coordinator."""
        self.hass = hass
        self.auth_coordinator = auth_coordinator
        self.device_id = device_id
        self.device_name = device_name
        self._diffuse_time = DEFAULT_DIFFUSE_TIME
        self._work_duration = DEFAULT_WORK_DURATION
        self._pause_duration = DEFAULT_PAUSE_DURATION
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{device_id}",
            update_interval=timedelta(minutes=1),
        )
    
    @property
    def diffuse_time(self):
        """Return the diffuse time."""
        return self._diffuse_time
        
    @diffuse_time.setter
    def diffuse_time(self, value):
        """Set the diffuse time."""
        self._diffuse_time = value
        
    @property
    def work_duration(self):
        """Return the work duration."""
        return self._work_duration
        
    @work_duration.setter
    def work_duration(self, value):
        """Set the work duration."""
        self._work_duration = value
        
    @property
    def pause_duration(self):
        """Return the pause duration."""
        return self._pause_duration
        
    @pause_duration.setter
    def pause_duration(self, value):
        """Set the pause duration."""
        self._pause_duration = value
    
    async def fetch_work_time_settings(self, week_day=0):
        """Fetch current work time settings from API."""
        await self.auth_coordinator._ensure_login()
        jsessionid = self.auth_coordinator.jsessionid
        
        url = f"https://www.aroma-link.com/device/workTime/{self.device_id}?week={week_day}"
        
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.aroma-link.com",
            "Referer": f"https://www.aroma-link.com/device/command/{self.device_id}",
        }
        
        if jsessionid and not jsessionid.startswith("temp_"):
            headers["Cookie"] = f"languagecode={self.auth_coordinator.language_code}; JSESSIONID={jsessionid}"
        
        try:
            _LOGGER.debug(f"Fetching work time settings for device {self.device_id} day {week_day}")
            async with self.auth_coordinator.session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    response_json = await response.json()
                    
                    if response_json.get("code") == 200 and "data" in response_json and response_json["data"]:
                        # Find the enabled setting (enabled: 1)
                        for setting in response_json["data"]:
                            if setting.get("enabled") == 1:
                                self._work_duration = setting.get("workSec", self._work_duration)
                                self._pause_duration = setting.get("pauseSec", self._pause_duration)
                                _LOGGER.debug(f"Found settings: work={self._work_duration}s, pause={self._pause_duration}s")
                                return {
                                    "work_duration": self._work_duration,
                                    "pause_duration": self._pause_duration,
                                    "week_day": week_day
                                }
                    
                    _LOGGER.warning(f"No enabled work time settings found for device {self.device_id}")
                    return None
                elif response.status in [401, 403]:
                    _LOGGER.warning(f"Authentication error on fetch_work_time_settings ({response.status}).")
                    self.auth_coordinator.jsessionid = None
                    return None
                else:
                    _LOGGER.error(f"Failed to fetch work time settings for device {self.device_id}: {response.status}")
                    return None
        except Exception as e:
            _LOGGER.error(f"Error fetching work time settings for device {self.device_id}: {e}")
            return None
    
    def get_device_info(self):
        """Get device info for entity setup."""
        return {
            "id": self.device_id,
            "name": self.device_name
        }
    
    async def _async_update_data(self):
        """Fetch current device state from API."""
        # Ensure auth is valid
        await self.auth_coordinator._ensure_login()
        jsessionid = self.auth_coordinator.jsessionid
        
        url = f"https://www.aroma-link.com/device/deviceInfo/now/{self.device_id}?timeout=1000"
        
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.aroma-link.com",
            "Referer": f"https://www.aroma-link.com/device/command/{self.device_id}",
        }
        
        # Only add Cookie header if we have a valid JSESSIONID
        if jsessionid and not jsessionid.startswith("temp_"):
            headers["Cookie"] = f"languagecode={self.auth_coordinator.language_code}; JSESSIONID={jsessionid}"
        
        try:
            _LOGGER.debug(f"Fetching info for device {self.device_id} from: {url}")
            async with self.auth_coordinator.session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    response_json = await response.json()
                    
                    if response_json.get("code") == 200 and "data" in response_json:
                        device_data = response_json["data"]
                        is_on = device_data.get("onOff") == 1
                        return {
                            "state": is_on,
                            "onOff": device_data.get("onOff"),
                            "workStatus": device_data.get("workStatus"),
                            "workRemainTime": device_data.get("workRemainTime"),
                            "pauseRemainTime": device_data.get("pauseRemainTime"),
                            "raw_device_data": device_data,
                            "device_id": self.device_id,
                            "device_name": self.device_name
                        }
                    else:
                        error_msg = response_json.get("msg", "Unknown error")
                        _LOGGER.error(f"API error for device {self.device_id}: {error_msg}")
                        raise UpdateFailed(f"API error: {error_msg}")
                elif response.status in [401, 403]:
                    _LOGGER.warning(f"Authentication error ({response.status}) for device {self.device_id}. Forcing re-login.")
                    self.auth_coordinator.jsessionid = None
                    raise UpdateFailed(f"Authentication error")
                else:
                    _LOGGER.error(f"Failed to fetch device {self.device_id} info, status: {response.status}")
                    raise UpdateFailed(f"Error fetching device info: status {response.status}")
        except Exception as e:
            _LOGGER.error(f"Error fetching device {self.device_id} info: {e}")
            raise UpdateFailed(f"Error: {e}")
    
    async def turn_on_off(self, state_to_set):
        """Turn the diffuser on or off."""
        await self.auth_coordinator._ensure_login()
        jsessionid = self.auth_coordinator.jsessionid
                
        url = "https://www.aroma-link.com/device/switch"
        
        data = {
            "deviceId": self.device_id,
            "onOff": 1 if state_to_set else 0
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.aroma-link.com",
            "Referer": f"https://www.aroma-link.com/device/command/{self.device_id}",
        }
        
        if jsessionid and not jsessionid.startswith("temp_"):
            headers["Cookie"] = f"languagecode={self.auth_coordinator.language_code}; JSESSIONID={jsessionid}"
        
        try:
            async with self.auth_coordinator.session.post(url, data=data, headers=headers, timeout=10) as response:
                if response.status == 200:
                    _LOGGER.info(f"Successfully commanded device {self.device_id} to {'on' if state_to_set else 'off'}")
                    await self.async_request_refresh()
                    return True
                elif response.status in [401, 403]:
                    _LOGGER.warning(f"Authentication error on turn_on_off ({response.status}).")
                    self.auth_coordinator.jsessionid = None
                    return False
                else:
                    _LOGGER.error(f"Failed to control device {self.device_id}: {response.status}")
                    return False
        except Exception as e:
            _LOGGER.error(f"Control error for device {self.device_id}: {e}")
            return False
    
    async def set_scheduler(self, work_duration=None, pause_duration=None, week_days=None):
        """Set the scheduler for the diffuser."""
        await self.auth_coordinator._ensure_login()
        jsessionid = self.auth_coordinator.jsessionid
                
        url = "https://www.aroma-link.com/device/workSet"
        
        if week_days is None:
            week_days = [0, 1, 2, 3, 4, 5, 6]  # Default to all days
        
        # Use provided values or fall back to stored values
        work_duration = work_duration if work_duration is not None else self._work_duration
        pause_duration = pause_duration if pause_duration is not None else self._pause_duration
                
        payload = {
            "deviceId": self.device_id,
            "type": "workTime",
            "week": week_days,
            "workTimeList": [
                {
                    "startTime": "00:00",
                    "endTime": "23:59",
                    "enabled": 1,
                    "consistenceLevel": "1",
                    "workDuration": str(work_duration),
                    "pauseDuration": str(pause_duration)
                },
                {
                    "startTime": "00:00",
                    "endTime": "24:00",
                    "enabled": 0,
                    "consistenceLevel": "1",
                    "workDuration": "10",
                    "pauseDuration": "900"
                },
                {
                    "startTime": "00:00",
                    "endTime": "24:00",
                    "enabled": 0,
                    "consistenceLevel": "1",
                    "workDuration": "10",
                    "pauseDuration": "900"
                },
                {
                    "startTime": "00:00",
                    "endTime": "24:00",
                    "enabled": 0,
                    "consistenceLevel": "1",
                    "workDuration": "10",
                    "pauseDuration": "900"
                },
                {
                    "startTime": "00:00",
                    "endTime": "24:00",
                    "enabled": 0,
                    "consistenceLevel": "1",
                    "workDuration": "10",
                    "pauseDuration": "900"
                }
            ]
        }
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.aroma-link.com",
            "Referer": f"https://www.aroma-link.com/device/command/{self.device_id}",
        }
        
        if jsessionid and not jsessionid.startswith("temp_"):
            headers["Cookie"] = f"languagecode={self.auth_coordinator.language_code}; JSESSIONID={jsessionid}"

        try:
            async with self.auth_coordinator.session.post(url, json=payload, headers=headers, timeout=10) as response:
                if response.status == 200:
                    _LOGGER.info(f"Successfully set scheduler for device {self.device_id}")
                    await self.async_request_refresh()
                    return True
                elif response.status in [401, 403]:
                    _LOGGER.warning(f"Authentication error on set_scheduler ({response.status}).")
                    self.auth_coordinator.jsessionid = None
                    return False
                else:
                    _LOGGER.error(f"Failed to set scheduler for device {self.device_id}: {response.status}")
                    return False
        except Exception as e:
            _LOGGER.error(f"Scheduler error for device {self.device_id}: {e}")
            return False
    
    async def run_diffuser(self, work_duration=None, pause_duration=None, run_time=5):
        """Run the diffuser for a specific time."""
        # Use default values if specific ones aren't provided
        current_work_duration = work_duration if work_duration is not None else self._work_duration
        current_pause_duration = pause_duration if pause_duration is not None else self._pause_duration
        run_time = 5  # Reduced run time to 5 seconds to avoid long delays

        _LOGGER.info(f"Setting up device {self.device_id} to run for {run_time} seconds with {current_work_duration} second diffusion cycles and {current_pause_duration} second pauses")
        
        # Set scheduler
        if not await self.set_scheduler(current_work_duration, current_pause_duration):
            _LOGGER.error(f"Failed to set scheduler for device {self.device_id}")
            return False
        
        await asyncio.sleep(1) # Allow time for scheduler settings to apply
        
        if not await self.turn_on_off(True):
            _LOGGER.error(f"Failed to turn on device {self.device_id}")
            return False
        
        _LOGGER.info(f"Device {self.device_id} turned on. Will turn off automatically after {run_time} seconds.")

        # Schedule turn off after the specified time
        async def turn_off_later():
            await asyncio.sleep(run_time)
            _LOGGER.info(f"Timer complete for device {self.device_id}. Attempting to turn off.")
            if not await self.turn_on_off(False):
                _LOGGER.error(f"Failed to automatically turn off device {self.device_id}")
            else:
                _LOGGER.info(f"Device {self.device_id} turned off successfully after timer")
        
        self.hass.async_create_task(turn_off_later())
        
        return True

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Aroma-Link component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Aroma-Link from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    devices = entry.data.get("devices", [])
    
    if not devices and CONF_DEVICE_ID in entry.data:
        # Support for old configuration format with single device
        device_id = entry.data[CONF_DEVICE_ID]
        device_name = entry.data.get("device_name", "Unknown")
        devices = [{CONF_DEVICE_ID: device_id, "device_name": device_name}]
    
    if not devices:
        _LOGGER.error("No devices found in config entry")
        return False
    
    _LOGGER.info(f"Setting up Aroma-Link integration with {len(devices)} devices")
    
    # Create a single shared coordinator for authentication
    auth_coordinator = AromaLinkAuthCoordinator(
        hass,
        username=username,
        password=password
    )
    
    # Force first login and initialization
    await auth_coordinator.async_config_entry_first_refresh()
    
    # Store coordinators for each device
    device_coordinators = {}
    
    # Create coordinator for each device
    for device in devices:
        device_id = device[CONF_DEVICE_ID]
        device_name = device.get("device_name", f"Device {device_id}")
        
        _LOGGER.info(f"Initializing device coordinator for {device_name} ({device_id})")
        
        device_coordinator = AromaLinkDeviceCoordinator(
            hass,
            auth_coordinator=auth_coordinator,
            device_id=device_id,
            device_name=device_name
        )
        
        # Do first refresh for each device
        try:
            await device_coordinator.async_config_entry_first_refresh()
            device_coordinators[device_id] = device_coordinator
        except Exception as e:
            _LOGGER.error(f"Error initializing device {device_id}: {e}")
    
    if not device_coordinators:
        _LOGGER.error("Failed to initialize any devices")
        return False
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "auth_coordinator": auth_coordinator,
        "device_coordinators": device_coordinators,
    }
    
    # Register services
    async def set_scheduler_service(call: ServiceCall):
        """Service to set diffuser scheduler."""
        device_id = call.data.get("device_id")
        work_duration = call.data.get(ATTR_WORK_DURATION)
        pause_duration = call.data.get(ATTR_PAUSE_DURATION)
        week_days = call.data.get(ATTR_WEEK_DAYS, [0, 1, 2, 3, 4, 5, 6])
        
        # If device_id specified, use that coordinator
        if device_id and device_id in device_coordinators:
            await device_coordinators[device_id].set_scheduler(work_duration, pause_duration, week_days)
        elif len(device_coordinators) == 1:
            # If only one device, use that
            first_device_id = list(device_coordinators.keys())[0]
            await device_coordinators[first_device_id].set_scheduler(work_duration, pause_duration, week_days)
        else:
            _LOGGER.error("Multiple devices available, must specify device_id")
    
    async def run_diffuser_service(call: ServiceCall):
        """Service to run diffuser for a specific time."""
        device_id = call.data.get("device_id")
        work_duration = call.data.get(ATTR_WORK_DURATION)
        pause_duration = call.data.get(ATTR_PAUSE_DURATION)
        
        # If device_id specified, use that coordinator
        if device_id and device_id in device_coordinators:
            await device_coordinators[device_id].run_diffuser(work_duration, pause_duration=pause_duration)
        elif len(device_coordinators) == 1:
            # If only one device, use that
            first_device_id = list(device_coordinators.keys())[0]
            await device_coordinators[first_device_id].run_diffuser(work_duration, pause_duration=pause_duration)
        else:
            _LOGGER.error("Multiple devices available, must specify device_id")

    hass.services.async_register(
        DOMAIN, 
        SERVICE_SET_SCHEDULER, 
        set_scheduler_service, 
        schema=SET_SCHEDULER_SCHEMA
    )

    hass.services.async_register(
        DOMAIN, 
        SERVICE_RUN_DIFFUSER, 
        run_diffuser_service, 
        schema=RUN_DIFFUSER_SCHEMA
    )

    # Use the new method
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True



class AromaLinkCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(self, hass, username, password, device_id=None):
        """Initialize."""
        self.username = username
        self.password = password
        self.device_id = device_id  # This can now be None initially
        self.jsessionid = None
        self.language_code = "EN"
        self.session = async_get_clientsession(hass)
        self.hass = hass
        self._diffuse_time = DEFAULT_DIFFUSE_TIME
        self._work_duration = DEFAULT_WORK_DURATION
        self._last_login_time = 0  # Track when we last logged in
        self._devices = []  # Store the list of devices

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=1),
        )
        
    async def fetch_device_list(self):
        """Fetch the list of available devices."""
        await self._ensure_login()  # Ensures self.jsessionid is valid
        
        url = "https://www.aroma-link.com/device/list/v2?limit=10&offset=0&selectUserId=&groupId=&deviceName=&imei=&deviceNo=&workStatus=&continentId=&countryId=&areaId=&sort=&order="
        
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.aroma-link.com",
            "Referer": "https://www.aroma-link.com/device/list",
        }
        
        if self.jsessionid and not self.jsessionid.startswith("temp_"):
            headers["Cookie"] = f"languagecode={self.language_code}; JSESSIONID={self.jsessionid}"
        
        try:
            _LOGGER.debug(f"Fetching device list from: {url}")
            async with self.session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    response_json = await response.json()
                    _LOGGER.debug(f"Device list raw response: {response_json}")
                    
                    if "rows" in response_json and response_json["rows"]:
                        self._devices = response_json["rows"]
                        
                        if not self.device_id and self._devices:
                            # Use the first device ID if none was specified
                            self.device_id = self._devices[0]["deviceId"]
                            _LOGGER.info(f"Using first available device: {self.device_id} ({self._devices[0].get('deviceName', 'Unknown')})")
                        
                        return self._devices
                    else:
                        _LOGGER.error("No devices found in the response")
                        raise UpdateFailed("No devices found in your Aroma-Link account")
                elif response.status in [401, 403]:
                    _LOGGER.warning(f"Authentication error ({response.status}) fetching device list. JSESSIONID might be invalid.")
                    self.jsessionid = None
                    raise UpdateFailed(f"Authentication error fetching device list: {response.status}")
                else:
                    _LOGGER.error(f"Failed to fetch device list, status: {response.status}, response: {await response.text()[:200]}")
                    raise UpdateFailed(f"Error fetching device list: status {response.status}")
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout fetching device list")
            raise UpdateFailed("Timeout fetching device list")
        except Exception as e:
            _LOGGER.error(f"Unexpected error fetching device list: {e}", exc_info=True)
            raise UpdateFailed(f"Unexpected error communicating with API: {e}")
        
        return []
        
    @property
    def diffuse_time(self):
        """Return the diffuse time."""
        return self._diffuse_time
        
    @diffuse_time.setter
    def diffuse_time(self, value):
        """Set the diffuse time."""
        self._diffuse_time = value
        
    @property
    def work_duration(self):
        """Return the work duration."""
        return self._work_duration
    
    @work_duration.setter
    def work_duration(self, value):
        """Set the work duration."""
        self._work_duration = value
    
    def get_device_info(self):
        """Get device info for entity setup."""
        return {
            "id": self.device_id,
            "name": self.device_name
        }
    
    async def _async_update_data(self):
        """Fetch current device state from API."""
        await self._ensure_login()  # Ensures self.jsessionid is valid

        # If we don't have a device ID yet, get the device list first
        if not self.device_id:
            await self.fetch_device_list()
            if not self.device_id:
                raise UpdateFailed("No devices found in your Aroma-Link account")

        url = f"https://www.aroma-link.com/device/deviceInfo/now/{self.device_id}?timeout=1000"
        
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.aroma-link.com",
            "Referer": f"https://www.aroma-link.com/device/command/{self.device_id}",
        }
        
        # Only add Cookie header if we have a valid JSESSIONID (not temporary)
        if self.jsessionid and not self.jsessionid.startswith("temp_"):
            headers["Cookie"] = f"languagecode={self.language_code}; JSESSIONID={self.jsessionid}"
        else:
            _LOGGER.debug("No valid JSESSIONID for device info call, ensure_login should handle.")

        try:
            _LOGGER.debug(f"Fetching device info from: {url}")
            async with self.session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    response_json = await response.json()
                    _LOGGER.debug(f"Device info raw response: {response_json}")
                    
                    if response_json.get("code") == 200 and "data" in response_json:
                        device_data = response_json["data"]
                        is_on = device_data.get("onOff") == 1
                        return {
                            "state": is_on,
                            "onOff": device_data.get("onOff"),
                            "workStatus": device_data.get("workStatus"),
                            "workRemainTime": device_data.get("workRemainTime"),
                            "pauseRemainTime": device_data.get("pauseRemainTime"),
                            "raw_device_data": device_data,
                            "device_id": self.device_id,  # Include the device ID in the data
                            "device_name": next((device.get("deviceName", "Unknown") for device in self._devices if device.get("deviceId") == self.device_id), "Unknown")
                        }
                    else:
                        _LOGGER.error(f"API error or malformed data fetching device info: {response_json.get('msg', 'Unknown error')}")
                        raise UpdateFailed(f"API error or malformed data: {response_json.get('msg', 'No message')}")
                elif response.status in [401, 403]:
                    _LOGGER.warning(f"Authentication error ({response.status}) fetching device info. JSESSIONID might be invalid. Forcing re-login on next attempt.")
                    self.jsessionid = None
                    raise UpdateFailed(f"Authentication error fetching device info: {response.status}")
                else:
                    _LOGGER.error(f"Failed to fetch device info, status: {response.status}, response: {await response.text()[:200]}")
                    raise UpdateFailed(f"Error fetching device info: status {response.status}")
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout fetching device info.")
            raise UpdateFailed("Timeout fetching device info.")
        except Exception as e:
            _LOGGER.error(f"Unexpected error fetching device info: {e}", exc_info=True)
            raise UpdateFailed(f"Unexpected error communicating with API: {e}")

    async def _ensure_login(self):
        """Ensure we have a valid session, login if needed."""
        current_time = time.time()
        session_age = current_time - self._last_login_time
        
        if self.jsessionid is None or self.jsessionid.startswith("temp_") or session_age > 1200:  # 20 min or temp ID
            _LOGGER.debug("Session expired, temporary, or not established. Attempting login.")
            login_success = await self._login()
            if not login_success:
                _LOGGER.error("Failed to login during ensure_login.")
                raise UpdateFailed("Authentication failed, cannot update device state.")
        # _LOGGER.debug("Session appears valid.") # Can be noisy
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
            _LOGGER.debug("Attempting initial GET to aroma-link.com for cookies.")
            async with self.session.get("https://www.aroma-link.com/", timeout=10) as initial_response:
                initial_response.raise_for_status() 
                _LOGGER.debug(f"Initial GET successful (status {initial_response.status}). Cookies: {self.session.cookie_jar.filter_cookies('https://www.aroma-link.com')}")

            _LOGGER.debug(f"Attempting login to {login_url} as {self.username}.")
            async with self.session.post(login_url, data=data, headers=headers, timeout=10) as response:
                response_text = await response.text()
                _LOGGER.debug(f"Login response status: {response.status}, body: {response_text[:200]}...")

                if response.status == 200:
                    jsessionid_found = None
                    
                    # Method 1: Try to get JSESSIONID from cookie jar
                    filtered_cookies = self.session.cookie_jar.filter_cookies(response.url)
                    _LOGGER.debug(f"Filtered cookies from jar: {filtered_cookies}")
                    
                    if "JSESSIONID" in filtered_cookies:
                        jsessionid_morsel = filtered_cookies["JSESSIONID"]
                        jsessionid_found = jsessionid_morsel.value
                        _LOGGER.debug(f"Found JSESSIONID '{jsessionid_found}' in cookie jar.")
                    
                    # Method 2: If not found in jar, check response headers
                    if not jsessionid_found and 'Set-Cookie' in response.headers:
                        _LOGGER.debug(f"Looking for JSESSIONID in Set-Cookie header: {response.headers['Set-Cookie']}")
                        cookie_header = response.headers['Set-Cookie']
                        if 'JSESSIONID=' in cookie_header:
                            try:
                                start = cookie_header.index('JSESSIONID=') + 11
                                end = cookie_header.index(';', start) if ';' in cookie_header[start:] else len(cookie_header)
                                jsessionid_found = cookie_header[start:end]
                                _LOGGER.debug(f"Extracted JSESSIONID from header: {jsessionid_found}")
                            except Exception as e:
                                _LOGGER.error(f"Error extracting JSESSIONID from header: {e}")
                    
                    # Method 3: Check if login was successful from response text
                    if jsessionid_found:
                        self.jsessionid = jsessionid_found
                        self._last_login_time = time.time()
                        _LOGGER.info(f"Successfully logged in as {self.username}. JSESSIONID obtained: {jsessionid_found[:5]}...")
                        return True
                    elif "success" in response_text.lower():
                        _LOGGER.warning("Login response indicates success, but JSESSIONID not found. Creating temporary session ID.")
                        self.jsessionid = f"temp_login_success_{time.time()}"
                        self._last_login_time = time.time()
                        return True

                        _LOGGER.error(f"Failed to get JSESSIONID from login response (cookie not found). Body: {response_text[:500]}")
                        self.jsessionid = None 
                        return False
                else:
                    _LOGGER.error(f"Login failed with status code: {response.status}. Response: {response_text[:500]}")
                    self.jsessionid = None
                    return False
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout during login process.")
            self.jsessionid = None
            return False
        except Exception as e:
            _LOGGER.error(f"Login error: {e}", exc_info=True) # exc_info=True is good for debugging
            self.jsessionid = None
            return False


    async def turn_on_off(self, state_to_set):
        """Turn the diffuser on or off."""
        await self._ensure_login()
        
        # Make sure we have a device ID
        if not self.device_id:
            await self.fetch_device_list()
            if not self.device_id:
                _LOGGER.error("Cannot control device: No device ID available")
                return False
                
        url = "https://www.aroma-link.com/device/switch"
        
        data = {
            "deviceId": self.device_id,
            "onOff": 1 if state_to_set else 0
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.aroma-link.com",
            "Referer": f"https://www.aroma-link.com/device/command/{self.device_id}",
        }
        
        if self.jsessionid and not self.jsessionid.startswith("temp_"):
            headers["Cookie"] = f"languagecode={self.language_code}; JSESSIONID={self.jsessionid}"
        
        try:
            async with self.session.post(url, data=data, headers=headers, timeout=10) as response:
                if response.status == 200:
                    _LOGGER.info(f"Successfully commanded device {self.device_id} to {'on' if state_to_set else 'off'}")
                    await self.async_request_refresh()
                    return True
                elif response.status in [401, 403]:
                    _LOGGER.warning(f"Authentication error on turn_on_off ({response.status}). Forcing re-login.")
                    self.jsessionid = None
                    return False
                else:
                    _LOGGER.error(f"Failed to control device: {response.status}, Response: {await response.text()[:200]}")
                    return False
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout controlling device.")
            return False
        except Exception as e:
            _LOGGER.error(f"Control error: {e}", exc_info=True)
            return False

    async def set_scheduler(self, work_duration, week_days=None):
        """Set the scheduler for the diffuser."""
        await self._ensure_login()
        
        # Make sure we have a device ID
        if not self.device_id:
            await self.fetch_device_list()
            if not self.device_id:
                _LOGGER.error("Cannot set scheduler: No device ID available")
                return False
                
        url = "https://www.aroma-link.com/device/workSet"
        
        if week_days is None:
            week_days = [0, 1, 2, 3, 4, 5, 6]  # Default to all days
                
        payload = {
            "deviceId": self.device_id,
            "type": "workTime",
            "week": week_days,
            "workTimeList": [
                {
                    "startTime": "00:00",
                    "endTime": "23:59",
                    "enabled": 1,
                    "consistenceLevel": "1",
                    "workDuration": str(work_duration),
                    "pauseDuration": "900"
                },
                {
                    "startTime": "00:00",
                    "endTime": "24:00",
                    "enabled": 0,
                    "consistenceLevel": "1",
                    "workDuration": "10",
                    "pauseDuration": "900"
                },
                {
                    "startTime": "00:00",
                    "endTime": "24:00",
                    "enabled": 0,
                    "consistenceLevel": "1",
                    "workDuration": "10",
                    "pauseDuration": "900"
                },
                {
                    "startTime": "00:00",
                    "endTime": "24:00",
                    "enabled": 0,
                    "consistenceLevel": "1",
                    "workDuration": "10",
                    "pauseDuration": "900"
                },
                {
                    "startTime": "00:00",
                    "endTime": "24:00",
                    "enabled": 0,
                    "consistenceLevel": "1",
                    "workDuration": "10",
                    "pauseDuration": "900"
                }
            ]
        }
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.aroma-link.com",
            "Referer": f"https://www.aroma-link.com/device/command/{self.device_id}",
        }
        if self.jsessionid and not self.jsessionid.startswith("temp_"):
            headers["Cookie"] = f"languagecode={self.language_code}; JSESSIONID={self.jsessionid}"

        try:
            async with self.session.post(url, json=payload, headers=headers, timeout=10) as response:
                if response.status == 200:
                    _LOGGER.info(f"Successfully set scheduler for device {self.device_id}")
                    await self.async_request_refresh()
                    return True
                elif response.status in [401, 403]:
                    _LOGGER.warning(f"Authentication error on set_scheduler ({response.status}). Forcing re-login.")
                    self.jsessionid = None
                    return False
                else:
                    _LOGGER.error(f"Failed to set scheduler: {response.status}, Response: {await response.text()[:200]}")
                    return False
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout setting scheduler.")
            return False
        except Exception as e:
            _LOGGER.error(f"Scheduler error: {e}", exc_info=True)
            return False

    async def run_diffuser(self, work_duration=None, diffuse_time=None):
        """Run the diffuser for a specific time."""
        
        # Make sure we have a device ID
        if not self.device_id:
            await self.fetch_device_list()
            if not self.device_id:
                _LOGGER.error("Cannot run diffuser: No device ID available")
                return False
        
        # Use coordinator's default values if specific ones aren't provided
        current_work_duration = work_duration if work_duration is not None else self.work_duration
        current_diffuse_time = diffuse_time if diffuse_time is not None else self.diffuse_time

        _LOGGER.info(f"Setting up diffuser to run for {current_diffuse_time} seconds with {current_work_duration} second diffusion cycles")
        
        # Set scheduler
        if not await self.set_scheduler(current_work_duration):
            _LOGGER.error("Failed to set scheduler for run_diffuser sequence")
            return False
        
        await asyncio.sleep(1) # Allow time for scheduler settings to apply
        
        if not await self.turn_on_off(True):
            _LOGGER.error("Failed to turn on diffuser for run_diffuser sequence")
            return False
        
        _LOGGER.info(f"Diffuser turned on. Will turn off automatically after {current_diffuse_time} seconds.")

        # Schedule turn off after the specified time
        async def turn_off_later():
            await asyncio.sleep(current_diffuse_time)
            _LOGGER.info(f"Timer complete for run_diffuser. Attempting to turn off device {self.device_id}.")
            if not await self.turn_on_off(False):
                _LOGGER.error(f"Failed to automatically turn off device {self.device_id} after run_diffuser sequence.")
            else:
                _LOGGER.info(f"Device {self.device_id} turned off successfully after run_diffuser sequence.")
        
        self.hass.async_create_task(turn_off_later())
        
        return True
