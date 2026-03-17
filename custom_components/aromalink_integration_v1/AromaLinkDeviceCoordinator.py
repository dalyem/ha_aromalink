import asyncio
import logging
import time
from datetime import timedelta
import aiohttp
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import (
    AROMA_LINK_SSL,
    AROMA_LINK_TRACE_REQUESTS,
    DOMAIN,
    DEFAULT_DIFFUSE_TIME,
    DEFAULT_WORK_DURATION,
    DEFAULT_PAUSE_DURATION,
)

_LOGGER = logging.getLogger(__name__)
AROMA_LINK_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/91.0.4472.124 Safari/537.36"
)


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
        self._primed_jsessionid = None
        self._last_switch_command_at = 0.0
        self._last_switch_state = None
        self.data = self._default_device_data()

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{device_id}",
            update_interval=timedelta(minutes=1),
        )

    def _default_device_data(self):
        """Return the fallback state used before the first successful refresh."""
        return {
            "state": False,
            "onOff": None,
            "workStatus": None,
            "workRemainTime": None,
            "pauseRemainTime": None,
            "raw_device_data": {},
            "device_id": self.device_id,
            "device_name": self.device_name,
        }

    def _log_request(self, method, url, extra=None):
        """Temporarily log outgoing Aroma-Link requests."""
        if not AROMA_LINK_TRACE_REQUESTS:
            return

        suffix = f" | device_id={self.device_id}" if extra is None else f" | device_id={self.device_id} | {extra}"
        _LOGGER.warning("Aroma-Link request: %s %s%s", method, url, suffix)

    def _log_response(self, method, url, status):
        """Temporarily log Aroma-Link responses."""
        if not AROMA_LINK_TRACE_REQUESTS:
            return

        _LOGGER.warning(
            "Aroma-Link response: %s %s -> %s | device_id=%s",
            method,
            url,
            status,
            self.device_id,
        )

    def _log_response_body(self, label, body):
        """Temporarily log truncated response bodies while reverse engineering."""
        if not AROMA_LINK_TRACE_REQUESTS:
            return

        preview = body if len(body) <= 1200 else f"{body[:1200]}...<truncated>"
        _LOGGER.warning(
            "Aroma-Link response body [%s] | device_id=%s | %s",
            label,
            self.device_id,
            preview,
        )

    def _build_headers(self, referer, jsessionid=None, content_type=None):
        """Build request headers for Aroma-Link device requests."""
        headers = {
            "User-Agent": AROMA_LINK_USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.aroma-link.com",
            "Referer": referer,
        }

        if content_type:
            headers["Content-Type"] = content_type

        if jsessionid and not jsessionid.startswith("temp_"):
            headers["Cookie"] = (
                f"languagecode={self.auth_coordinator.language_code}; "
                f"JSESSIONID={jsessionid}"
            )

        return headers

    def _build_app_headers(self):
        """Build headers for the mobile app endpoints."""
        return self.auth_coordinator._app_auth_headers()

    def _payload_has_app_auth_error(self, payload):
        """Return True when the app API says the token is invalid or expired."""
        if not isinstance(payload, dict):
            return False

        code = payload.get("code")
        message = str(payload.get("msg", "")).lower()
        return code == 13002 or "token has expired" in message or "unauthorized" in message

    def _normalize_device_payload(self, payload):
        """Normalize app or web payloads into the coordinator data shape."""
        device_data = self._find_candidate_device_data(payload)
        if not isinstance(device_data, dict):
            return None

        on_off = self._coerce_on_off(
            device_data.get("onOff")
            if "onOff" in device_data
            else device_data.get("state")
        )

        if on_off is None:
            on_off = self._coerce_on_off(device_data.get("switchStatus"))
        if on_off is None:
            on_off = self._coerce_on_off(device_data.get("isOpen"))
        if on_off is None:
            on_off = self._coerce_on_off(device_data.get("isOn"))

        work_status = self._coerce_int(
            device_data.get("workStatus")
            if "workStatus" in device_data
            else device_data.get("work_status")
        )
        if work_status is None:
            work_status = self._coerce_int(device_data.get("runStatus"))

        if on_off is None and work_status is not None:
            on_off = 0 if work_status == 0 else 1

        work_remain_time = self._coerce_int(
            device_data.get("workRemainTime")
            if "workRemainTime" in device_data
            else device_data.get("workRemainSeconds")
        )
        pause_remain_time = self._coerce_int(
            device_data.get("pauseRemainTime")
            if "pauseRemainTime" in device_data
            else device_data.get("pauseRemainSeconds")
        )

        has_live_state = any(
            value is not None
            for value in (
                on_off,
                work_status,
                work_remain_time,
                pause_remain_time,
                device_data.get("onCount"),
                device_data.get("pumpCount"),
            )
        )
        if not has_live_state:
            return None

        return {
            "state": on_off == 1 if on_off is not None else None,
            "onOff": on_off,
            "workStatus": work_status,
            "workRemainTime": work_remain_time,
            "pauseRemainTime": pause_remain_time,
            "raw_device_data": device_data,
            "device_id": self.device_id,
            "device_name": self.device_name,
        }

    def _merge_device_data(self, *sources):
        """Merge normalized device payloads without wiping known state with nulls."""
        merged = self._default_device_data()

        for source in sources:
            if not isinstance(source, dict):
                continue

            for key, value in source.items():
                if key == "raw_device_data":
                    if isinstance(value, dict) and value:
                        merged[key] = {**merged.get(key, {}), **value}
                    continue

                if value is not None:
                    merged[key] = value

        merged["state"] = bool(merged.get("onOff")) if merged.get("onOff") is not None else bool(merged.get("state"))
        merged.setdefault("device_id", self.device_id)
        merged.setdefault("device_name", self.device_name)
        return merged

    def _normalize_web_list_row(self, row):
        """Normalize rows returned by /device/list or /device/list/v2."""
        if not isinstance(row, dict):
            return None

        work_status = self._coerce_int(row.get("workStatus"))
        on_off = self._coerce_on_off(row.get("onOff"))
        if on_off is None and work_status is not None:
            on_off = 0 if work_status == 0 else 1

        raw_device_data = dict(row)
        if raw_device_data.get("onCount") is None and raw_device_data.get("runCount") is not None:
            raw_device_data["onCount"] = raw_device_data.get("runCount")
        if raw_device_data.get("pumpCount") is None and raw_device_data.get("airPumpCount") is not None:
            raw_device_data["pumpCount"] = raw_device_data.get("airPumpCount")

        return {
            "state": on_off == 1 if on_off is not None else None,
            "onOff": on_off,
            "workStatus": work_status,
            "workRemainTime": None,
            "pauseRemainTime": None,
            "raw_device_data": raw_device_data,
            "device_id": self.device_id,
            "device_name": row.get("deviceName", self.device_name),
        }

    async def _fetch_web_list_state(self, jsessionid):
        """Fetch device state from the device list endpoints as a fallback."""
        endpoints = (
            "https://www.aroma-link.com/device/list/v2?limit=10&offset=0&selectUserId=&groupId=&deviceName=&imei=&deviceNo=&workStatus=&continentId=&countryId=&areaId=&sort=&order=",
            "https://www.aroma-link.com/device/list",
        )

        headers = self._build_headers(
            referer="https://www.aroma-link.com/device/list",
            jsessionid=jsessionid,
        )

        for url in endpoints:
            try:
                self._log_request("GET", url, extra="web_list_fallback=true")
                async with self.auth_coordinator.session.get(
                    url,
                    headers=headers,
                    timeout=15,
                    ssl=AROMA_LINK_SSL,
                ) as response:
                    self._log_response("GET", url, response.status)
                    if response.status != 200:
                        continue

                    response_text = await response.text()
                    self._log_response_body("web_list_state", response_text)
                    payload = await response.json()
                    rows = payload.get("rows")
                    if not isinstance(rows, list):
                        continue

                    for row in rows:
                        row_device_id = row.get("deviceId") or row.get("id")
                        if str(row_device_id) != str(self.device_id):
                            continue

                        normalized = self._normalize_web_list_row(row)
                        if normalized is not None:
                            return normalized
            except Exception as err:
                _LOGGER.debug(
                    "Web list fallback request failed for %s via %s: %s",
                    self.device_id,
                    url,
                    err,
                )

        return None

    def _apply_recent_switch_state(self, data):
        """Preserve recent switch commands if the next poll lacks live-state fields."""
        if not isinstance(data, dict):
            return data

        if time.monotonic() - self._last_switch_command_at > 15:
            return data

        if data.get("onOff") is not None:
            return data

        optimistic = dict(data)
        optimistic["onOff"] = 1 if self._last_switch_state else 0
        optimistic["state"] = bool(self._last_switch_state)
        if optimistic.get("workStatus") is None:
            optimistic["workStatus"] = 1 if self._last_switch_state else 0

        if AROMA_LINK_TRACE_REQUESTS:
            _LOGGER.warning(
                "Aroma-Link retained recent switch state | device_id=%s | onOff=%s | workStatus=%s",
                self.device_id,
                optimistic["onOff"],
                optimistic.get("workStatus"),
            )
        return optimistic

    async def _delayed_refresh(self, delay_seconds=3):
        """Refresh later so optimistic state is not immediately wiped by stale data."""
        await asyncio.sleep(delay_seconds)
        await self.async_request_refresh()

    def _find_candidate_device_data(self, payload):
        """Find the nested object most likely to contain device state."""
        interesting_keys = {
            "onOff",
            "state",
            "switchStatus",
            "isOpen",
            "isOn",
            "workStatus",
            "work_status",
            "runStatus",
            "workRemainTime",
            "pauseRemainTime",
            "workRemainSeconds",
            "pauseRemainSeconds",
            "onCount",
            "pumpCount",
        }

        if isinstance(payload, dict):
            if interesting_keys.intersection(payload.keys()):
                return payload

            for value in payload.values():
                candidate = self._find_candidate_device_data(value)
                if candidate is not None:
                    return candidate

        if isinstance(payload, list):
            for item in payload:
                candidate = self._find_candidate_device_data(item)
                if candidate is not None:
                    return candidate

        return payload if isinstance(payload, dict) else None

    def _coerce_on_off(self, value):
        """Convert various truthy device values into Aroma-Link on/off flags."""
        if value is None:
            return None
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, (int, float)):
            if value in (0, 1):
                return int(value)
        value_str = str(value).strip().lower()
        if value_str in {"1", "true", "on", "open", "opened"}:
            return 1
        if value_str in {"0", "false", "off", "close", "closed"}:
            return 0
        return None

    def _coerce_int(self, value):
        """Convert known numeric-like payload values to ints."""
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    async def _fetch_app_device_info(self, retried=False, is_open_page=0):
        """Fetch device state from the mobile app endpoint when token auth is available."""
        user_id = self.auth_coordinator.user_id
        headers = self._build_app_headers()
        if not user_id or headers is None:
            return None

        url = (
            f"http://www.aroma-link.com/v1/app/device/newWork/{self.device_id}"
            f"?isOpenPage={is_open_page}&userId={user_id}"
        )

        try:
            self._log_request(
                "GET",
                url,
                extra=f"app_endpoint=true user_id={user_id} isOpenPage={is_open_page}",
            )
            async with self.auth_coordinator.session.get(
                url,
                headers=headers,
                timeout=15,
            ) as response:
                self._log_response("GET", url, response.status)
                if response.status != 200:
                    _LOGGER.debug(
                        "App device info request for %s returned status %s",
                        self.device_id,
                        response.status,
                    )
                    return None

                response_text = await response.text()
                self._log_response_body("app_device_info", response_text)
                payload = await response.json(content_type=None)
                if AROMA_LINK_TRACE_REQUESTS:
                    _LOGGER.warning(
                        "Aroma-Link parsed app device payload | device_id=%s | %r",
                        self.device_id,
                        payload,
                    )
                if self._payload_has_app_auth_error(payload):
                    _LOGGER.warning(
                        "Aroma-Link app token rejected for device %s; refreshing app auth.",
                        self.device_id,
                    )
                    if retried:
                        if is_open_page == 0:
                            _LOGGER.warning(
                                "Aroma-Link retrying newWork with isOpenPage=1 for device %s.",
                                self.device_id,
                            )
                            return await self._fetch_app_device_info(retried=True, is_open_page=1)
                        return None
                    if await self.auth_coordinator.async_refresh_app_auth():
                        return await self._fetch_app_device_info(retried=True, is_open_page=is_open_page)
                    return None
                normalized = self._normalize_device_payload(payload)
                if normalized is None and is_open_page == 0:
                    _LOGGER.warning(
                        "Aroma-Link newWork returned no live state for device %s with isOpenPage=0; retrying with isOpenPage=1.",
                        self.device_id,
                    )
                    return await self._fetch_app_device_info(retried=retried, is_open_page=1)
                if normalized is not None:
                    _LOGGER.warning(
                        "Aroma-Link normalized app device payload | device_id=%s | keys=%s | onOff=%s | workStatus=%s",
                        self.device_id,
                        sorted(normalized["raw_device_data"].keys()),
                        normalized.get("onOff"),
                        normalized.get("workStatus"),
                    )
                    if AROMA_LINK_TRACE_REQUESTS:
                        _LOGGER.warning(
                            "Aroma-Link app coordinator data | device_id=%s | %r",
                            self.device_id,
                            normalized,
                        )
                elif AROMA_LINK_TRACE_REQUESTS:
                    _LOGGER.warning(
                        "Aroma-Link app payload did not normalize | device_id=%s",
                        self.device_id,
                    )
                if normalized is None:
                    _LOGGER.debug(
                        "App device info response for %s did not contain recognizable data.",
                        self.device_id,
                    )
                return normalized
        except Exception as err:
            _LOGGER.debug(
                "App device info request failed for %s: %s",
                self.device_id,
                err,
            )
            return None

    async def _app_switch(self, state_to_set, retried=False):
        """Send on/off commands to the mobile app endpoint when token auth is available."""
        user_id = self.auth_coordinator.user_id
        headers = self._build_app_headers()
        if not user_id or headers is None:
            return False

        data = aiohttp.FormData()
        data.add_field("deviceId", str(self.device_id))
        data.add_field("onOff", "1" if state_to_set else "0")
        data.add_field("userId", str(user_id))

        try:
            self._log_request(
                "POST",
                "http://www.aroma-link.com/v1/app/data/newSwitch",
                extra=f"app_endpoint=true onOff={'1' if state_to_set else '0'} user_id={user_id}",
            )
            async with self.auth_coordinator.session.post(
                "http://www.aroma-link.com/v1/app/data/newSwitch",
                headers=headers,
                data=data,
                timeout=15,
            ) as response:
                self._log_response("POST", "http://www.aroma-link.com/v1/app/data/newSwitch", response.status)
                response_text = await response.text()
                self._log_response_body("app_switch", response_text)
                payload = None
                try:
                    payload = await response.json(content_type=None)
                except Exception:
                    payload = None

                if self._payload_has_app_auth_error(payload):
                    _LOGGER.warning(
                        "Aroma-Link app switch token rejected for device %s; refreshing app auth.",
                        self.device_id,
                    )
                    if retried:
                        return False
                    if await self.auth_coordinator.async_refresh_app_auth():
                        return await self._app_switch(state_to_set, retried=True)
                    return False

                return response.status == 200
        except Exception as err:
            _LOGGER.debug(
                "App switch request failed for %s: %s",
                self.device_id,
                err,
            )
            return False

    async def _prime_device_session(self, jsessionid, force=False):
        """Load the device command page before calling AJAX endpoints."""
        if not jsessionid or jsessionid.startswith("temp_"):
            return

        if not force and self._primed_jsessionid == jsessionid:
            return

        url = f"https://www.aroma-link.com/device/command/{self.device_id}"
        headers = {
            "User-Agent": AROMA_LINK_USER_AGENT,
            "Referer": "https://www.aroma-link.com/device/list",
            "Cookie": (
                f"languagecode={self.auth_coordinator.language_code}; "
                f"JSESSIONID={jsessionid}"
            ),
        }

        try:
            self._log_request("GET", url, extra="prime_device_session=true")
            async with self.auth_coordinator.session.get(
                url,
                headers=headers,
                timeout=15,
                ssl=AROMA_LINK_SSL,
            ) as response:
                self._log_response("GET", url, response.status)
                if response.status == 200:
                    self._primed_jsessionid = jsessionid
                else:
                    _LOGGER.debug(
                        "Device command page prime for %s returned status %s",
                        self.device_id,
                        response.status,
                    )
        except Exception as err:
            _LOGGER.debug(
                "Device command page prime failed for %s: %s",
                self.device_id,
                err,
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
        await self._prime_device_session(jsessionid)
        headers = self._build_headers(
            referer=f"https://www.aroma-link.com/device/command/{self.device_id}",
            jsessionid=jsessionid,
        )

        try:
            _LOGGER.debug(
                f"Fetching work time settings for device {self.device_id} day {week_day}")
            self._log_request("GET", url, extra=f"week_day={week_day}")
            async with self.auth_coordinator.session.get(
                url,
                headers=headers,
                timeout=15,
                ssl=AROMA_LINK_SSL,
            ) as response:
                self._log_response("GET", url, response.status)
                if response.status == 200:
                    response_text = await response.text()
                    self._log_response_body("web_work_time", response_text)
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

                    _LOGGER.debug(
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
        await self.auth_coordinator._ensure_login()
        jsessionid = self.auth_coordinator.jsessionid
        previous_data = self.data if isinstance(self.data, dict) else self._default_device_data()

        try:
            web_list_data = await self._fetch_web_list_state(jsessionid)
            if web_list_data is not None:
                return self._apply_recent_switch_state(
                    self._merge_device_data(previous_data, web_list_data)
                )

            app_data = await self._fetch_app_device_info()
            if app_data is not None:
                return self._apply_recent_switch_state(
                    self._merge_device_data(previous_data, app_data)
                )

            _LOGGER.warning(
                "Failed to fetch runtime state for device %s from web list and app newWork endpoints.",
                self.device_id,
            )
            raise UpdateFailed("Failed to fetch device runtime state")
        except UpdateFailed:
            raise
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

        await self._prime_device_session(jsessionid)
        headers = self._build_headers(
            referer=f"https://www.aroma-link.com/device/command/{self.device_id}",
            jsessionid=jsessionid,
            content_type="application/x-www-form-urlencoded; charset=UTF-8",
        )

        try:
            if await self._app_switch(state_to_set):
                optimistic_data = dict(self.data or self._default_device_data())
                optimistic_data["state"] = state_to_set
                optimistic_data["onOff"] = 1 if state_to_set else 0
                if not state_to_set:
                    optimistic_data["workStatus"] = 0
                elif optimistic_data.get("workStatus") is None:
                    optimistic_data["workStatus"] = 1
                self._last_switch_command_at = time.monotonic()
                self._last_switch_state = state_to_set
                self.async_set_updated_data(optimistic_data)
                if AROMA_LINK_TRACE_REQUESTS:
                    _LOGGER.warning(
                        "Aroma-Link optimistic switch state | device_id=%s | %r",
                        self.device_id,
                        optimistic_data,
                    )

                _LOGGER.info(
                    "Successfully commanded device %s to %s via app endpoint",
                    self.device_id,
                    "on" if state_to_set else "off",
                )
                self.hass.async_create_task(self._delayed_refresh())
                return True

            self._log_request("POST", url, extra=f"onOff={'1' if state_to_set else '0'}")
            async with self.auth_coordinator.session.post(
                url,
                data=data,
                headers=headers,
                timeout=10,
                ssl=AROMA_LINK_SSL,
            ) as response:
                self._log_response("POST", url, response.status)
                if response.status == 200:
                    _LOGGER.info(
                        f"Successfully commanded device {self.device_id} to {'on' if state_to_set else 'off'}")
                    self._last_switch_command_at = time.monotonic()
                    self._last_switch_state = state_to_set
                    optimistic_data = self._merge_device_data(
                        self.data,
                        {
                            "state": state_to_set,
                            "onOff": 1 if state_to_set else 0,
                            "workStatus": 1 if state_to_set else 0,
                        },
                    )
                    self.async_set_updated_data(optimistic_data)
                    self.hass.async_create_task(self._delayed_refresh())
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

        await self._prime_device_session(jsessionid)
        headers = self._build_headers(
            referer=f"https://www.aroma-link.com/device/command/{self.device_id}",
            jsessionid=jsessionid,
            content_type="application/json;charset=UTF-8",
        )

        try:
            self._log_request("POST", url, extra=f"week_days={week_days}")
            async with self.auth_coordinator.session.post(
                url,
                json=payload,
                headers=headers,
                timeout=10,
                ssl=AROMA_LINK_SSL,
            ) as response:
                self._log_response("POST", url, response.status)
                response_text = await response.text()
                self._log_response_body("web_work_set", response_text)
                if response.status == 200:
                    self._work_duration = work_duration
                    self._pause_duration = pause_duration
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
