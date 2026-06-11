"""Switch platform for Aroma-Link."""
import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, CONF_DEVICE_ID

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Aroma-Link switches based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    device_coordinators = data["device_coordinators"]

    entities = []
    for device_id, coordinator in device_coordinators.items():
        device_info = coordinator.get_device_info()
        entities.append(AromaLinkPowerSwitch(coordinator, entry, device_id, device_info["name"]))
        entities.append(AromaLinkFanSwitch(coordinator, entry, device_id, device_info["name"]))

    async_add_entities(entities)

class AromaLinkPowerSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of an Aroma-Link power switch (oil pumping)."""

    def __init__(self, coordinator, entry, device_id, device_name):
        """Initialize the switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._device_id = device_id
        self._name = f"{device_name} Active"
        self._unique_id = f"{entry.data['username']}_{device_id}_power"

    @property
    def name(self):
        """Return the name of the switch."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return self._unique_id

    @property
    def is_on(self):
        """Return true if the device is powered on and pumping."""
        return self.coordinator.data.get("state", False)

    @property
    def available(self):
        """Return true when the coordinator reports this device reachable."""
        return super().available

    @property
    def device_info(self):
        """Return device information about this Aroma-Link device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.data['username']}_{self._device_id}")},
            name=self.coordinator.device_name,
            manufacturer="Aroma-Link",
            model="Diffuser",
        )

    async def async_turn_on(self, **kwargs):
        """Turn the device on when work/pause durations are configured."""
        work = self.coordinator.work_duration or 0
        pause = self.coordinator.pause_duration or 0
        if work <= 0 or pause <= 0:
            _LOGGER.warning(
                "Cannot turn on %s: work_duration=%d, pause_duration=%d (both must be > 0)",
                self._device_id, work, pause
            )
            return
        await self.coordinator.turn_on_off(True)

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        await self.coordinator.turn_on_off(False)


class AromaLinkFanSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of an Aroma-Link exhaust fan switch."""

    def __init__(self, coordinator, entry, device_id, device_name):
        """Initialize the fan switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._device_id = device_id
        self._name = f"{device_name} Fan"
        self._unique_id = f"{entry.data['username']}_{device_id}_fan"
        self._attr_icon = "mdi:fan"

    @property
    def name(self):
        """Return the name of the switch."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return self._unique_id

    @property
    def is_on(self):
        """Return true if the exhaust fan is on."""
        return self.coordinator.data.get("fan", False)

    @property
    def device_info(self):
        """Return device information about this Aroma-Link device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.data['username']}_{self._device_id}")},
            name=self.coordinator.device_name,
            manufacturer="Aroma-Link",
            model="Diffuser",
        )

    async def async_turn_on(self, **kwargs):
        """Turn the exhaust fan on."""
        await self.coordinator.set_fan(True)

    async def async_turn_off(self, **kwargs):
        """Turn the exhaust fan off."""
        await self.coordinator.set_fan(False)
