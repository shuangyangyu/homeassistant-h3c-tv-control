"""Button platform for H3C TV Control."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, TVS, TVConfig
from .coordinator import H3CTVCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up daily reset buttons."""
    coordinator: H3CTVCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        H3CTVDailyResetButton(coordinator, entry, tv_key, tv_info)
        for tv_key, tv_info in TVS.items()
    )


class H3CTVDailyResetButton(
    CoordinatorEntity[H3CTVCoordinator], ButtonEntity
):
    """Reset today's child-control usage and cooldown."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-refresh"

    def __init__(
        self,
        coordinator: H3CTVCoordinator,
        entry: ConfigEntry,
        tv_key: str,
        tv_info: TVConfig,
    ) -> None:
        """Initialize the daily reset button."""
        super().__init__(coordinator)
        self.tv_key = tv_key
        self._attr_unique_id = f"{entry.entry_id}_{tv_key}_daily_reset"
        self._attr_name = "今日初始化"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{tv_key}")},
            name=tv_info["name"],
            manufacturer="Sony",
            model="TV Internet Control",
            via_device=(DOMAIN, entry.entry_id),
        )

    async def async_press(self) -> None:
        """Reset today's usage and cooldown."""
        await self.coordinator.async_reset_daily(self.tv_key)
