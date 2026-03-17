"""Switch platform for Aroma-Link."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, CONF_DEVICE_ID

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Aroma-Link switch based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    device_coordinators = data["device_coordinators"]
    
    entities = []
    for device_id, coordinator in device_coordinators.items():
        device_info = coordinator.get_device_info()
        entities.append(AromaLinkSwitch(coordinator, entry, device_id, device_info["name"]))
    
    async_add_entities(entities)

class AromaLinkSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of an Aroma-Link switch."""

    def __init__(self, coordinator, entry, device_id, device_name):
        """Initialize the switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._device_id = device_id
        self._name = f"{device_name} Power"
        self._unique_id = f"{entry.data['username']}_{device_id}_switch"

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
        """Return true if the switch is on."""
        return self.coordinator.data.get("state", False)

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
        """Turn the switch on."""
        await self.coordinator.turn_on_off(True)

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self.coordinator.turn_on_off(False)
