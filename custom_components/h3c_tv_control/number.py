"""Number platform for H3C TV Control."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MAX_COOLDOWN_MINUTES,
    MAX_DAILY_MINUTES,
    MAX_SESSION_MINUTES,
    MIN_COOLDOWN_MINUTES,
    MIN_DAILY_MINUTES,
    MIN_SESSION_MINUTES,
    TVS,
    TVConfig,
)
from .coordinator import H3CTVCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up child-control number entities."""
    coordinator: H3CTVCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[NumberEntity] = []
    for tv_key, tv_info in TVS.items():
        entities.append(
            H3CTVSessionMinutesNumber(coordinator, entry, tv_key, tv_info)
        )
        entities.append(
            H3CTVDailyMinutesNumber(coordinator, entry, tv_key, tv_info)
        )
        entities.append(
            H3CTVCooldownMinutesNumber(coordinator, entry, tv_key, tv_info)
        )
    async_add_entities(entities)


class H3CTVBaseNumber(CoordinatorEntity[H3CTVCoordinator], NumberEntity):
    """Base class for H3C TV number entities."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = "min"

    def __init__(
        self,
        coordinator: H3CTVCoordinator,
        entry: ConfigEntry,
        tv_key: str,
        tv_info: TVConfig,
    ) -> None:
        """Initialize a child-control number entity."""
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


class H3CTVSessionMinutesNumber(H3CTVBaseNumber):
    """Number entity for session time limit."""

    def __init__(
        self,
        coordinator: H3CTVCoordinator,
        entry: ConfigEntry,
        tv_key: str,
        tv_info: TVConfig,
    ) -> None:
        """Initialize the single-session limit entity."""
        super().__init__(coordinator, entry, tv_key, tv_info)
        self._attr_unique_id = f"{entry.entry_id}_{tv_key}_session_minutes"
        self._attr_name = "单次允许"
        self._attr_icon = "mdi:timer-outline"
        self._attr_native_min_value = MIN_SESSION_MINUTES
        self._attr_native_max_value = MAX_SESSION_MINUTES
        self._attr_native_step = 5

    @property
    def native_value(self) -> float:
        """Return the configured single-session limit."""
        return float(
            self.coordinator.child_policy.get_state(
                self.tv_key
            ).settings.session_minutes
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set the single-session limit."""
        await self.coordinator.async_update_policy(
            lambda policy: policy.set_session_minutes(
                self.tv_key, int(value)
            )
        )


class H3CTVDailyMinutesNumber(H3CTVBaseNumber):
    """Number entity for daily time limit."""

    def __init__(
        self,
        coordinator: H3CTVCoordinator,
        entry: ConfigEntry,
        tv_key: str,
        tv_info: TVConfig,
    ) -> None:
        """Initialize the daily usage limit entity."""
        super().__init__(coordinator, entry, tv_key, tv_info)
        self._attr_unique_id = f"{entry.entry_id}_{tv_key}_daily_minutes"
        self._attr_name = "每日允许"
        self._attr_icon = "mdi:calendar-clock"
        self._attr_native_min_value = MIN_DAILY_MINUTES
        self._attr_native_max_value = MAX_DAILY_MINUTES
        self._attr_native_step = 10

    @property
    def native_value(self) -> float:
        """Return the configured daily usage limit."""
        return float(
            self.coordinator.child_policy.get_state(
                self.tv_key
            ).settings.daily_minutes
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set the daily usage limit."""
        await self.coordinator.async_update_policy(
            lambda policy: policy.set_daily_minutes(
                self.tv_key, int(value)
            )
        )


class H3CTVCooldownMinutesNumber(H3CTVBaseNumber):
    """Number entity for the post-session cooldown."""

    def __init__(
        self,
        coordinator: H3CTVCoordinator,
        entry: ConfigEntry,
        tv_key: str,
        tv_info: TVConfig,
    ) -> None:
        """Initialize the cooldown duration entity."""
        super().__init__(coordinator, entry, tv_key, tv_info)
        self._attr_unique_id = f"{entry.entry_id}_{tv_key}_cooldown_minutes"
        self._attr_name = "冷却时间"
        self._attr_icon = "mdi:snowflake"
        self._attr_native_min_value = MIN_COOLDOWN_MINUTES
        self._attr_native_max_value = MAX_COOLDOWN_MINUTES
        self._attr_native_step = 5

    @property
    def native_value(self) -> float:
        """Return the configured cooldown duration."""
        return float(
            self.coordinator.child_policy.get_state(
                self.tv_key
            ).settings.cooldown_minutes
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set the cooldown duration."""
        await self.coordinator.async_update_policy(
            lambda policy: policy.set_cooldown_minutes(
                self.tv_key, int(value)
            )
        )
