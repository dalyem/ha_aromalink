"""The Aroma-Link integration."""
import logging
from datetime import timedelta

from .AromaLinkDeviceCoordinator import AromaLinkDeviceCoordinator
from .AromaLinkAuthCoordinator import AromaLinkAuthCoordinator

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import (
    DOMAIN,
    CONF_DEVICE_ID,
    SERVICE_SET_SCHEDULER,
    SERVICE_RUN_DIFFUSER,
    ATTR_WORK_DURATION,
    ATTR_PAUSE_DURATION,
    ATTR_WEEK_DAYS,
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

    _LOGGER.info(
        f"Setting up Aroma-Link integration with {len(devices)} devices")

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

        _LOGGER.info(
            f"Initializing device coordinator for {device_name} ({device_id})")

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
