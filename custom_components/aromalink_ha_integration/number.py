"""Number platform for Aroma-Link."""
import logging
from homeassistant.components.number import NumberEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DOMAIN,
    DEFAULT_DIFFUSE_TIME,
    DEFAULT_WORK_DURATION,
    DEFAULT_PAUSE_DURATION,
    CONF_POLL_INTERVAL_SECONDS,
    DEFAULT_POLL_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Aroma-Link number entities based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    device_coordinators = data["device_coordinators"]
    
    entities = [AromaLinkPollingIntervalNumber(hass, entry)]
    for device_id, coordinator in device_coordinators.items():
        device_info = coordinator.get_device_info()
        # Fetch current settings
        await coordinator.fetch_work_time_settings()
        entities.append(AromaLinkWorkDurationNumber(coordinator, entry, device_id, device_info["name"]))
        entities.append(AromaLinkPauseDurationNumber(coordinator, entry, device_id, device_info["name"]))
    
    async_add_entities(entities)


class AromaLinkPollingIntervalNumber(NumberEntity):
    """Representation of the integration polling interval."""

    def __init__(self, hass, entry):
        """Initialize the polling interval entity."""
        self.hass = hass
        self._entry = entry
        self._attr_name = "Polling Interval"
        self._attr_unique_id = f"{entry.entry_id}_poll_interval"
        self._attr_icon = "mdi:timer-cog-outline"
        self._attr_native_min_value = 10
        self._attr_native_max_value = 300
        self._attr_native_step = 10
        self._attr_native_unit_of_measurement = "seconds"
        self._attr_mode = "box"

    @property
    def device_info(self):
        """Return integration-level device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_controls")},
            name="Aromalink Integration Controls",
            manufacturer="Aromalink",
            model="Integration Settings",
        )

    @property
    def native_value(self):
        """Return the current polling interval."""
        return self._entry.options.get(
            CONF_POLL_INTERVAL_SECONDS,
            DEFAULT_POLL_INTERVAL_SECONDS,
        )

    async def async_set_native_value(self, value):
        """Persist a new polling interval."""
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={
                **self._entry.options,
                CONF_POLL_INTERVAL_SECONDS: int(value),
            },
        )
        self.async_write_ha_state()

class AromaLinkDiffuseTimeNumber(NumberEntity):
    """Representation of an Aroma-Link diffuse time setting."""

    def __init__(self, coordinator, entry, device_id, device_name):
        """Initialize the number entity."""
        self._coordinator = coordinator
        self._entry = entry
        self._device_id = device_id
        self._name = f"{device_name} Diffuse Time"
        self._unique_id = f"{entry.data['username']}_{device_id}_diffuse_time"
        self._attr_native_min_value = 10  # Minimum 10 seconds
        self._attr_native_max_value = 3600  # Maximum 1 hour
        self._attr_native_step = 10  # 10 second steps
        self._attr_native_unit_of_measurement = "seconds"

    @property
    def name(self):
        """Return the name of the number entity."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return self._unique_id

    @property
    def native_value(self):
        """Return the current value."""
        return self._coordinator.diffuse_time

    @property
    def device_info(self):
        """Return device information about this Aroma-Link device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.data['username']}_{self._device_id}")},
            name=self._coordinator.device_name,
            manufacturer="Aroma-Link",
            model="Diffuser",
        )

    async def async_set_native_value(self, value):
        """Set the diffuse time."""
        self._coordinator.diffuse_time = int(value)
        self.async_write_ha_state()

class AromaLinkWorkDurationNumber(NumberEntity):
    """Representation of an Aroma-Link work duration setting."""

    def __init__(self, coordinator, entry, device_id, device_name):
        """Initialize the number entity."""
        self._coordinator = coordinator
        self._entry = entry
        self._device_id = device_id
        self._name = f"{device_name} Work Duration"
        self._unique_id = f"{entry.data['username']}_{device_id}_work_duration"
        self._attr_native_min_value = 5  # Minimum 5 seconds
        self._attr_native_max_value = 900  # Maximum 900 seconds (15 minutes)
        self._attr_native_step = 1  # 1 second steps
        self._attr_native_unit_of_measurement = "seconds"
        self._attr_icon = "mdi:spray"
        self._attr_mode = "box"  # Make it a number input field instead of a slider

    @property
    def name(self):
        """Return the name of the number entity."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return self._unique_id

    @property
    def native_value(self):
        """Return the current value."""
        return self._coordinator.work_duration
        
    async def async_set_native_value(self, value):
        """Set the work duration."""
        self._coordinator.work_duration = int(value)
        self.async_write_ha_state()

    @property
    def device_info(self):
        """Return device information about this Aroma-Link device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.data['username']}_{self._device_id}")},
            name=self._coordinator.device_name,
            manufacturer="Aroma-Link",
            model="Diffuser",
        )

    async def async_set_native_value(self, value):
        """Set the work duration."""
        self._coordinator.work_duration = int(value)
        self.async_write_ha_state()

class AromaLinkPauseDurationNumber(NumberEntity):
    """Representation of an Aroma-Link pause duration setting."""

    def __init__(self, coordinator, entry, device_id, device_name):
        """Initialize the number entity."""
        self._coordinator = coordinator
        self._entry = entry
        self._device_id = device_id
        self._name = f"{device_name} Pause Duration"
        self._unique_id = f"{entry.data['username']}_{device_id}_pause_duration"
        self._attr_native_min_value = 5  # Minimum 5 seconds
        self._attr_native_max_value = 900  # Maximum 900 seconds (15 minutes)
        self._attr_native_step = 5  # 5 second steps
        self._attr_native_unit_of_measurement = "seconds"
        self._attr_icon = "mdi:timer-pause"
        self._attr_mode = "box"  # Make it a number input field instead of a slider

    @property
    def name(self):
        """Return the name of the number entity."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return self._unique_id

    @property
    def device_info(self):
        """Return device information about this Aroma-Link device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.data['username']}_{self._device_id}")},
            name=self._coordinator.device_name,
            manufacturer="Aroma-Link",
            model="Diffuser",
        )

    @property
    def native_value(self):
        """Return the current value."""
        return self._coordinator.pause_duration
        
    async def async_set_native_value(self, value):
        """Set the pause duration."""
        self._coordinator.pause_duration = int(value)
        self.async_write_ha_state()
