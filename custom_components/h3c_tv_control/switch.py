"""Switch platform for H3C TV Control."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, TVS, TVConfig
from .coordinator import ChildPolicyDenied, H3CTVCoordinator
from .h3c_client import H3CClientError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TV internet and child-control switches."""
    coordinator: H3CTVCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = []
    for tv_key, tv_info in TVS.items():
        entities.append(H3CTVInternetSwitch(coordinator, entry, tv_key, tv_info))
        entities.append(H3CTVChildSwitch(coordinator, entry, tv_key, tv_info))
    async_add_entities(entities)


class H3CTVBaseSwitch(CoordinatorEntity[H3CTVCoordinator], SwitchEntity):
    """Base class for H3C TV switches."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: H3CTVCoordinator,
        entry: ConfigEntry,
        tv_key: str,
        tv_info: TVConfig,
    ) -> None:
        """Initialize a TV switch entity."""
        super().__init__(coordinator)
        self.tv_key = tv_key
        self.tv_info = tv_info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{tv_key}")},
            name=tv_info["name"],
            manufacturer="Sony",
            model="TV Internet Control",
            via_device=(DOMAIN, entry.entry_id),
        )

    @property
    def available(self) -> bool:
        """Return whether coordinator data is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.get("available", False)
        )


class H3CTVInternetSwitch(H3CTVBaseSwitch):
    """Switch to enable/disable TV internet access."""

    def __init__(
        self,
        coordinator: H3CTVCoordinator,
        entry: ConfigEntry,
        tv_key: str,
        tv_info: TVConfig,
    ) -> None:
        """Initialize the internet access switch."""
        super().__init__(coordinator, entry, tv_key, tv_info)
        self._attr_unique_id = f"{entry.entry_id}_{tv_key}_internet"
        self._attr_name = None
        self._attr_translation_key = "internet"
        self._attr_icon = "mdi:television"

    @property
    def is_on(self) -> bool | None:
        """Return whether internet access is enabled."""
        if not self.coordinator.data:
            return None
        statuses = self.coordinator.data.get("statuses", {})
        if self.tv_key not in statuses:
            return None
        return bool(statuses[self.tv_key].get("internet_enabled", False))

    @property
    def icon(self) -> str:
        """Return an icon matching the internet access state."""
        if self.is_on:
            return "mdi:television"
        return "mdi:television-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the most recent automatic-control result."""
        if not self.coordinator.data:
            return {}
        status = self.coordinator.data.get("statuses", {}).get(
            self.tv_key, {}
        )
        return {
            "auto_enabled": status.get("auto_enabled", False),
            "auto_disabled": status.get("auto_disabled", False),
            "disable_reason": status.get("disable_reason"),
            "disable_error": status.get("disable_error"),
            "enable_error": status.get("enable_error"),
            "media_player_entity_id": status.get("media_player_entity_id"),
            "tv_active": status.get("tv_active"),
            "cooldown_remaining_minutes": round(
                self.coordinator.child_policy.get_cooldown_remaining(
                    self.tv_key, dt_util.now()
                ),
                1,
            ),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable internet access for the TV."""
        try:
            await self.coordinator.async_enable_tv(self.tv_key)
        except ChildPolicyDenied as err:
            _LOGGER.warning("无法开启 %s: %s", self.tv_info["name"], err)
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="child_policy_denied",
                translation_placeholders={"reason": str(err)},
            ) from err
        except H3CClientError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": str(err)},
            ) from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable internet access for the TV."""
        try:
            await self.coordinator.async_disable_tv(self.tv_key)
        except H3CClientError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": str(err)},
            ) from err


class H3CTVChildSwitch(H3CTVBaseSwitch):
    """Switch to enable/disable child control for a TV."""

    def __init__(
        self,
        coordinator: H3CTVCoordinator,
        entry: ConfigEntry,
        tv_key: str,
        tv_info: TVConfig,
    ) -> None:
        """Initialize the child-control switch."""
        super().__init__(coordinator, entry, tv_key, tv_info)
        self._attr_unique_id = f"{entry.entry_id}_{tv_key}_child"
        self._attr_name = "儿童控制"
        self._attr_icon = "mdi:account-child"

    @property
    def is_on(self) -> bool:
        """Return whether child control is enabled."""
        return self.coordinator.child_policy.get_state(
            self.tv_key
        ).settings.child_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable child control."""
        await self.coordinator.async_set_child_enabled(self.tv_key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable child control."""
        await self.coordinator.async_set_child_enabled(self.tv_key, False)
