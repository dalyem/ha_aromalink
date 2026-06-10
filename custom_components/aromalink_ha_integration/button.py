"""Button platform for Aroma-Link."""
import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Aroma-Link button based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    device_coordinators = data["device_coordinators"]
    
    entities = []
    for device_id, coordinator in device_coordinators.items():
        device_info = coordinator.get_device_info()
        entities.append(AromaLinkRunOnceButton(coordinator, entry, device_id, device_info["name"]))
        entities.append(AromaLinkSaveSettingsButton(coordinator, entry, device_id, device_info["name"]))
    
    async_add_entities(entities)

class AromaLinkRunOnceButton(ButtonEntity):
    """Representation of an Aroma-Link run once button."""

    def __init__(self, coordinator, entry, device_id, device_name):
        """Initialize the button."""
        self._coordinator = coordinator
        self._entry = entry
        self._device_id = device_id
        self._name = f"{device_name} Run Once"
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
        work_duration = self._coordinator.work_duration or 0
        pause_duration = self._coordinator.pause_duration or 0

        if work_duration <= 0 or pause_duration <= 0:
            _LOGGER.warning(
                "Cannot run %s: work_duration=%d, pause_duration=%d (both must be > 0)",
                self._device_id, work_duration, pause_duration
            )
            return

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
        self._attr_entity_category = EntityCategory.CONFIG  # Settings card, below main controls

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
        work_duration = self._coordinator.work_duration or 0
        pause_duration = self._coordinator.pause_duration or 0

        if work_duration <= 0 or pause_duration <= 0:
            _LOGGER.warning(
                "Cannot save settings for %s: work_duration=%d, pause_duration=%d (both must be > 0)",
                self._device_id, work_duration, pause_duration
            )
            return

        result = await self._coordinator.set_scheduler(work_duration, pause_duration)
        if result:
            _LOGGER.info(f"Settings saved successfully for {self._coordinator.device_name}")
        else:
            _LOGGER.error(f"Failed to save settings for {self._coordinator.device_name}")
