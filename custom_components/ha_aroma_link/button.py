"""Button platform for Aroma-Link."""
import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Aroma-Link button based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    device_coordinators = data["device_coordinators"]
    
    entities = []
    for device_id, coordinator in device_coordinators.items():
        device_info = coordinator.get_device_info()
        entities.append(AromaLinkRunButton(coordinator, entry, device_id, device_info["name"]))
        entities.append(AromaLinkSaveSettingsButton(coordinator, entry, device_id, device_info["name"]))
    
    async_add_entities(entities)

class AromaLinkRunButton(ButtonEntity):
    """Representation of an Aroma-Link run button."""

    def __init__(self, coordinator, entry, device_id, device_name):
        """Initialize the button."""
        self._coordinator = coordinator
        self._entry = entry
        self._device_id = device_id
        self._name = f"{device_name} Run"
        self._unique_id = f"{entry.data['username']}_{device_id}_run"

    @property
    def name(self):
        """Return the name of the button."""
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

    async def async_press(self):
        """Run the diffuser for a fixed time."""
        work_duration = self._coordinator.work_duration
        pause_duration = self._coordinator.pause_duration
        
        _LOGGER.info(f"Button pressed. Running diffuser with {work_duration}s work and {pause_duration}s pause settings")
        
        await self._coordinator.run_diffuser(work_duration, pause_duration=pause_duration)

class AromaLinkSaveSettingsButton(ButtonEntity):
    """Representation of an Aroma-Link save settings button."""

    def __init__(self, coordinator, entry, device_id, device_name):
        """Initialize the button."""
        self._coordinator = coordinator
        self._entry = entry
        self._device_id = device_id
        self._name = f"{device_name} Save Settings"
        self._unique_id = f"{entry.data['username']}_{device_id}_save_settings"
        self._attr_icon = "mdi:content-save"

    @property
    def name(self):
        """Return the name of the button."""
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

    async def async_press(self):
        """Save the current work duration and pause duration settings."""
        work_duration = self._coordinator.work_duration
        pause_duration = self._coordinator.pause_duration
        
        _LOGGER.info(f"Saving settings: work_duration={work_duration}s, pause_duration={pause_duration}s")
        
        result = await self._coordinator.set_scheduler(work_duration, pause_duration)
        if result:
            _LOGGER.info(f"Settings saved successfully for {self._coordinator.device_name}")
        else:
            _LOGGER.error(f"Failed to save settings for {self._coordinator.device_name}")
