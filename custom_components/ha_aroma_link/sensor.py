"""Sensor platform for Aroma-Link."""
import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import UnitOfTime

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Aroma-Link sensor based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    device_coordinators = data["device_coordinators"]
    
    entities = []
    for device_id, coordinator in device_coordinators.items():
        device_info = coordinator.get_device_info()
        
        # Add all the requested sensors
        entities.append(AromaLinkWorkStatusSensor(coordinator, entry, device_id, device_info["name"]))
        entities.append(AromaLinkWorkRemainingTimeSensor(coordinator, entry, device_id, device_info["name"]))
        entities.append(AromaLinkPauseRemainingTimeSensor(coordinator, entry, device_id, device_info["name"]))
        entities.append(AromaLinkOnCountSensor(coordinator, entry, device_id, device_info["name"]))
        entities.append(AromaLinkPumpCountSensor(coordinator, entry, device_id, device_info["name"]))
    
    async_add_entities(entities)

class AromaLinkSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Aroma-Link sensors."""

    def __init__(self, coordinator, entry, device_id, device_name, sensor_type, icon=None, unit=None):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._device_id = device_id
        self._sensor_type = sensor_type
        self._name = f"{device_name} {sensor_type}"
        self._unique_id = f"{entry.data['username']}_{device_id}_{sensor_type.lower().replace(' ', '_')}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit

    @property
    def name(self):
        """Return the name of the sensor."""
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
            name=self.coordinator.device_name,
            manufacturer="Aroma-Link",
            model="Diffuser",
        )

class AromaLinkWorkStatusSensor(AromaLinkSensorBase):
    """Sensor showing the current work status."""

    def __init__(self, coordinator, entry, device_id, device_name):
        """Initialize the work status sensor."""
        super().__init__(
            coordinator, 
            entry, 
            device_id, 
            device_name, 
            "Work Status", 
            icon="mdi:state-machine"
        )

    @property
    def native_value(self):
        """Return the current work status."""
        work_status = self.coordinator.data.get("workStatus")
        if work_status == 0:
            return "Off"
        elif work_status == 1:
            return "Diffusing"
        elif work_status == 2:
            return "Paused"
        else:
            return "Unknown"

class AromaLinkWorkRemainingTimeSensor(AromaLinkSensorBase):
    """Sensor showing the remaining time in the current work cycle."""

    def __init__(self, coordinator, entry, device_id, device_name):
        """Initialize the work remaining time sensor."""
        super().__init__(
            coordinator, 
            entry, 
            device_id, 
            device_name, 
            "Work Remaining Time", 
            icon="mdi:timer-outline",
            unit=UnitOfTime.SECONDS
        )

    @property
    def native_value(self):
        """Return the remaining time in work cycle."""
        return self.coordinator.data.get("workRemainTime")

class AromaLinkPauseRemainingTimeSensor(AromaLinkSensorBase):
    """Sensor showing the remaining time in the current pause cycle."""

    def __init__(self, coordinator, entry, device_id, device_name):
        """Initialize the pause remaining time sensor."""
        super().__init__(
            coordinator, 
            entry, 
            device_id, 
            device_name, 
            "Pause Remaining Time", 
            icon="mdi:timer-pause-outline",
            unit=UnitOfTime.SECONDS
        )

    @property
    def native_value(self):
        """Return the remaining time in pause cycle."""
        return self.coordinator.data.get("pauseRemainTime")

class AromaLinkOnCountSensor(AromaLinkSensorBase):
    """Sensor showing how many times the device has been turned on."""

    def __init__(self, coordinator, entry, device_id, device_name):
        """Initialize the on count sensor."""
        super().__init__(
            coordinator, 
            entry, 
            device_id, 
            device_name, 
            "On Count", 
            icon="mdi:counter",
            unit="activations"
        )

    @property
    def native_value(self):
        """Return the on count value."""
        raw_data = self.coordinator.data.get("raw_device_data", {})
        return raw_data.get("onCount")

class AromaLinkPumpCountSensor(AromaLinkSensorBase):
    """Sensor showing the number of times the pump has operated (diffusions)."""

    def __init__(self, coordinator, entry, device_id, device_name):
        """Initialize the pump count sensor."""
        super().__init__(
            coordinator, 
            entry, 
            device_id, 
            device_name, 
            "Pump Count", 
            icon="mdi:shimmer",
            unit="diffusions"
        )

    @property
    def native_value(self):
        """Return the pump count value."""
        raw_data = self.coordinator.data.get("raw_device_data", {})
        return raw_data.get("pumpCount")