"""Select platform for H3C TV Control."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, TVS, WINDOW_PRESETS, TVConfig
from .coordinator import H3CTVCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up allowed-window select entities."""
    coordinator: H3CTVCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        H3CTVWindowPresetSelect(coordinator, entry, tv_key, tv_info)
        for tv_key, tv_info in TVS.items()
    )


class H3CTVWindowPresetSelect(
    CoordinatorEntity[H3CTVCoordinator], SelectEntity
):
    """Select a predefined allowed usage window."""

    _attr_has_entity_name = True
    _attr_translation_key = "allowed_window"
    _attr_icon = "mdi:clock-time-eight-outline"
    _attr_options = list(WINDOW_PRESETS)

    def __init__(
        self,
        coordinator: H3CTVCoordinator,
        entry: ConfigEntry,
        tv_key: str,
        tv_info: TVConfig,
    ) -> None:
        """Initialize the allowed-window selector."""
        super().__init__(coordinator)
        self.tv_key = tv_key
        self._attr_unique_id = f"{entry.entry_id}_{tv_key}_window_preset"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{tv_key}")},
            name=tv_info["name"],
            manufacturer="Sony",
            model="TV Internet Control",
            via_device=(DOMAIN, entry.entry_id),
        )

    @property
    def current_option(self) -> str:
        """Return the selected allowed-window preset."""
        return self.coordinator.child_policy.get_window_preset(self.tv_key)

    async def async_select_option(self, option: str) -> None:
        """Apply the selected allowed-window preset."""
        await self.coordinator.async_update_policy(
            lambda policy: policy.set_window_preset(self.tv_key, option)
        )
