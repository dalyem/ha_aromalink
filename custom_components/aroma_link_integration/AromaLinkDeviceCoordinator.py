import asyncio
import logging
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import (
    DOMAIN,
    DEFAULT_DIFFUSE_TIME,
    DEFAULT_WORK_DURATION,
    DEFAULT_PAUSE_DURATION,
)

_LOGGER = logging.getLogger(__name__)


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
            _LOGGER.debug(
                f"Fetching work time settings for device {self.device_id} day {week_day}")
            async with self.auth_coordinator.session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    response_json = await response.json()

                    if response_json.get("code") == 200 and "data" in response_json and response_json["data"]:
                        # Find the enabled setting (enabled: 1)
                        for setting in response_json["data"]:
                            if setting.get("enabled") == 1:
                                self._work_duration = setting.get(
                                    "workSec", self._work_duration)
                                self._pause_duration = setting.get(
                                    "pauseSec", self._pause_duration)
                                _LOGGER.debug(
                                    f"Found settings: work={self._work_duration}s, pause={self._pause_duration}s")
                                return {
                                    "work_duration": self._work_duration,
                                    "pause_duration": self._pause_duration,
                                    "week_day": week_day
                                }

                    _LOGGER.warning(
                        f"No enabled work time settings found for device {self.device_id}")
                    return None
                elif response.status in [401, 403]:
                    _LOGGER.warning(
                        f"Authentication error on fetch_work_time_settings ({response.status}).")
                    self.auth_coordinator.jsessionid = None
                    return None
                else:
                    _LOGGER.error(
                        f"Failed to fetch work time settings for device {self.device_id}: {response.status}")
                    return None
        except Exception as e:
            _LOGGER.error(
                f"Error fetching work time settings for device {self.device_id}: {e}")
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
            _LOGGER.debug(
                f"Fetching info for device {self.device_id} from: {url}")
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
                        _LOGGER.error(
                            f"API error for device {self.device_id}: {error_msg}")
                        raise UpdateFailed(f"API error: {error_msg}")
                elif response.status in [401, 403]:
                    _LOGGER.warning(
                        f"Authentication error ({response.status}) for device {self.device_id}. Forcing re-login.")
                    self.auth_coordinator.jsessionid = None
                    raise UpdateFailed(f"Authentication error")
                else:
                    _LOGGER.error(
                        f"Failed to fetch device {self.device_id} info, status: {response.status}")
                    raise UpdateFailed(
                        f"Error fetching device info: status {response.status}")
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
                    _LOGGER.info(
                        f"Successfully commanded device {self.device_id} to {'on' if state_to_set else 'off'}")
                    await self.async_request_refresh()
                    return True
                elif response.status in [401, 403]:
                    _LOGGER.warning(
                        f"Authentication error on turn_on_off ({response.status}).")
                    self.auth_coordinator.jsessionid = None
                    return False
                else:
                    _LOGGER.error(
                        f"Failed to control device {self.device_id}: {response.status}")
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
                    _LOGGER.info(
                        f"Successfully set scheduler for device {self.device_id}")
                    await self.async_request_refresh()
                    return True
                elif response.status in [401, 403]:
                    _LOGGER.warning(
                        f"Authentication error on set_scheduler ({response.status}).")
                    self.auth_coordinator.jsessionid = None
                    return False
                else:
                    _LOGGER.error(
                        f"Failed to set scheduler for device {self.device_id}: {response.status}")
                    return False
        except Exception as e:
            _LOGGER.error(f"Scheduler error for device {self.device_id}: {e}")
            return False

    async def run_diffuser(self, work_duration=None, pause_duration=None):
        """Run the diffuser for a specific time."""
        # Use default values if specific ones aren't provided
        current_work_duration = work_duration if work_duration is not None else self._work_duration
        current_pause_duration = pause_duration if pause_duration is not None else self._pause_duration
        buffertime = current_work_duration + 5  # Add buffer time

        _LOGGER.info(
            f"Setting up device {self.device_id} to run for {current_work_duration} seconds with {current_work_duration} second diffusion cycles and {current_pause_duration} second pauses")

        # Set scheduler
        if not await self.set_scheduler(current_work_duration, current_pause_duration):
            _LOGGER.error(
                f"Failed to set scheduler for device {self.device_id}")
            return False

        await asyncio.sleep(1)  # Allow time for scheduler settings to apply

        if not await self.turn_on_off(True):
            _LOGGER.error(f"Failed to turn on device {self.device_id}")
            return False

        _LOGGER.info(
            f"Device {self.device_id} turned on. Will turn off automatically after {buffertime} seconds.")

        # Schedule turn off after the specified time
        async def turn_off_later():
            await asyncio.sleep(buffertime)
            _LOGGER.info(
                f"Timer complete for device {self.device_id}. Attempting to turn off.")
            if not await self.turn_on_off(False):
                _LOGGER.error(
                    f"Failed to automatically turn off device {self.device_id}")
            else:
                _LOGGER.info(
                    f"Device {self.device_id} turned off successfully after timer")

        self.hass.async_create_task(turn_off_later())

        return True
