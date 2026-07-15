"""Data update coordinator for H3C TV Control."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.media_player.const import MediaPlayerState
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .child_policy import ChildPolicyManager, SESSION_LIMIT_REASON
from .const import (
    CONF_ACL_ID,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    DEFAULT_ACL_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    TV_MEDIA_PLAYER_OPTIONS,
    TVS,
    WINDOW_PRESETS,
)
from .h3c_client import H3CClientError, H3CTVClient

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 2
ACTIVE_TV_STATES = {
    MediaPlayerState.ON,
    MediaPlayerState.IDLE,
    MediaPlayerState.PLAYING,
    MediaPlayerState.PAUSED,
    MediaPlayerState.BUFFERING,
}
INACTIVE_TV_STATES = {MediaPlayerState.OFF, MediaPlayerState.STANDBY}
TV_UNAVAILABLE_GRACE = timedelta(minutes=2)


def storage_key(entry_id: str) -> str:
    """Return the per-config-entry storage key."""
    return f"{DOMAIN}.{entry_id}.child_policy"


class H3CTVCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the H3C switch and coordinate child policy changes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the H3C coordinator."""
        self.entry = entry
        self.client = H3CTVClient(
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            port=entry.data.get(CONF_PORT, DEFAULT_PORT),
            acl_id=entry.data.get(CONF_ACL_ID, DEFAULT_ACL_ID),
        )
        self.child_policy = ChildPolicyManager()
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            storage_key(entry.entry_id),
        )
        self._policy_loaded = False
        self._operation_lock = asyncio.Lock()
        self._tv_entity_ids = {
            tv_key: entry.options.get(option_key)
            for tv_key, option_key in TV_MEDIA_PLAYER_OPTIONS.items()
        }

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(
                seconds=entry.options.get(
                    "scan_interval", DEFAULT_SCAN_INTERVAL
                )
            ),
        )

    def _tv_activity(self, tv_key: str, now: datetime) -> bool | None:
        """Return whether the bound TV is active, inactive, or indeterminate."""
        entity_id = self._tv_entity_ids[tv_key]
        if not entity_id or (state := self.hass.states.get(entity_id)) is None:
            return None
        if state.state in ACTIVE_TV_STATES:
            return True
        if state.state in INACTIVE_TV_STATES:
            return False
        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            if now - state.last_changed >= TV_UNAVAILABLE_GRACE:
                return False
        return None

    def async_setup_tv_listeners(self) -> Callable[[], None]:
        """Listen for bound TV state changes and request immediate refreshes."""
        entity_to_tv = {
            entity_id: tv_key
            for tv_key, entity_id in self._tv_entity_ids.items()
            if entity_id
        }
        if not entity_to_tv:
            return lambda: None

        async def _async_tv_state_changed(
            event: Event[EventStateChangedData],
        ) -> None:
            await self.async_request_refresh()

        return async_track_state_change_event(
            self.hass,
            list(entity_to_tv),
            _async_tv_state_changed,
        )

    async def async_load_policy(self) -> None:
        """Load child policy state from storage."""
        data = await self._store.async_load()
        if data:
            self.child_policy.load_from_dict(data)
        for tv_key in TVS:
            state = self.child_policy.get_state(tv_key)
            preset = self.child_policy.get_window_preset(tv_key)
            if (
                state.settings.window_start,
                state.settings.window_end,
            ) != WINDOW_PRESETS[preset]:
                self.child_policy.set_window_preset(tv_key, preset)
        await self._async_save_policy_locked()
        self._policy_loaded = True

    async def _async_save_policy_locked(self, force: bool = False) -> None:
        """Persist policy while caller owns the operation lock."""
        if not force and not self.child_policy.dirty:
            return
        await self._store.async_save(self.child_policy.to_dict())
        self.child_policy.mark_clean()

    async def async_save_policy(self, force: bool = False) -> None:
        """Persist child policy safely."""
        async with self._operation_lock:
            await self._async_save_policy_locked(force)

    async def async_remove_storage(self) -> None:
        """Remove policy storage when the config entry is deleted."""
        await self._store.async_remove()

    async def _async_update_data(self) -> dict[str, Any]:
        if not self._policy_loaded:
            await self.async_load_policy()

        async with self._operation_lock:
            try:
                statuses = await self.hass.async_add_executor_job(
                    self.client.get_statuses
                )
            except Exception as err:
                raise UpdateFailed(
                    f"无法连接 H3C 交换机: {err}"
                ) from err

            now = dt_util.now()
            for tv_key in TVS:
                enabled = statuses[tv_key]["internet_enabled"]
                entity_id = self._tv_entity_ids[tv_key]
                tv_active = self._tv_activity(tv_key, now)
                statuses[tv_key]["media_player_entity_id"] = entity_id
                statuses[tv_key]["tv_active"] = tv_active

                state = self.child_policy.get_state(tv_key)
                if not entity_id:
                    self.child_policy.discard_session(tv_key)
                elif tv_active is False and state.runtime.session_start:
                    _, stop_reason = self.child_policy.should_disable(
                        tv_key, enabled, now
                    )
                    self.child_policy.end_session(
                        tv_key,
                        now,
                        start_cooldown=stop_reason == SESSION_LIMIT_REASON,
                    )

                if not state.settings.child_enabled:
                    self.child_policy.end_session(tv_key, now)
                    continue

                if not enabled and state.runtime.session_start:
                    _, stop_reason = self.child_policy.should_disable(
                        tv_key, True, now
                    )
                    self.child_policy.end_session(
                        tv_key,
                        now,
                        start_cooldown=stop_reason == SESSION_LIMIT_REASON,
                    )

                state = self.child_policy.get_state(tv_key)
                if state.runtime.session_start:
                    should_off, reason = self.child_policy.should_disable(
                        tv_key, enabled, now
                    )
                    if not should_off:
                        continue

                    _LOGGER.info(
                        "儿童控制自动断网: %s, 原因: %s",
                        TVS[tv_key]["name"],
                        reason,
                    )
                    try:
                        await self.hass.async_add_executor_job(
                            self.client.disable_internet, tv_key
                        )
                    except H3CClientError as err:
                        # Keep the session active so the next update retries.
                        statuses[tv_key]["disable_error"] = str(err)
                        statuses[tv_key]["disable_reason"] = reason
                        _LOGGER.error("自动断网失败 %s: %s", tv_key, err)
                        continue

                    self.child_policy.end_session(
                        tv_key,
                        now,
                        start_cooldown=reason == SESSION_LIMIT_REASON,
                    )
                    statuses[tv_key]["internet_enabled"] = False
                    statuses[tv_key]["auto_disabled"] = True
                    statuses[tv_key]["disable_reason"] = reason
                    continue

                can_enable, deny_reason = self.child_policy.can_enable(
                    tv_key, now
                )
                if not can_enable:
                    statuses[tv_key]["disable_reason"] = deny_reason
                    if enabled:
                        try:
                            await self.hass.async_add_executor_job(
                                self.client.disable_internet, tv_key
                            )
                        except H3CClientError as err:
                            statuses[tv_key]["disable_error"] = str(err)
                            _LOGGER.error("策略断网失败 %s: %s", tv_key, err)
                        else:
                            statuses[tv_key]["internet_enabled"] = False
                            statuses[tv_key]["auto_disabled"] = True
                    continue

                if not enabled:
                    try:
                        await self.hass.async_add_executor_job(
                            self.client.enable_internet, tv_key
                        )
                    except H3CClientError as err:
                        statuses[tv_key]["enable_error"] = str(err)
                        _LOGGER.error("自动开网失败 %s: %s", tv_key, err)
                        continue
                    enabled = True
                    statuses[tv_key]["internet_enabled"] = True
                    statuses[tv_key]["auto_enabled"] = True

                if entity_id and tv_active is True:
                    self.child_policy.start_session(tv_key, now)

            await self._async_save_policy_locked()
            return {"statuses": statuses, "available": True}

    async def async_enable_tv(self, tv_key: str) -> None:
        """Enable internet after checking child policy."""
        async with self._operation_lock:
            now = dt_util.now()
            can_enable, reason = self.child_policy.can_enable(tv_key, now)
            if not can_enable:
                raise ChildPolicyDenied(reason)

            currently_enabled = bool(
                self.data
                and self.data.get("statuses", {})
                .get(tv_key, {})
                .get("internet_enabled", False)
            )
            if not currently_enabled:
                await self.hass.async_add_executor_job(
                    self.client.enable_internet, tv_key
                )
            if self.child_policy.get_state(
                tv_key
            ).settings.child_enabled and self._tv_activity(tv_key, now) is True:
                self.child_policy.start_session(tv_key, now)
            await self._async_save_policy_locked()

        await self.async_request_refresh()

    async def async_disable_tv(self, tv_key: str) -> None:
        """Disable internet and only then settle the active session."""
        async with self._operation_lock:
            now = dt_util.now()
            _, stop_reason = self.child_policy.should_disable(
                tv_key, True, now
            )
            await self.hass.async_add_executor_job(
                self.client.disable_internet, tv_key
            )
            self.child_policy.end_session(
                tv_key,
                now,
                start_cooldown=stop_reason == SESSION_LIMIT_REASON,
            )
            await self._async_save_policy_locked()

        await self.async_request_refresh()

    async def async_update_policy(
        self, update: Callable[[ChildPolicyManager], None]
    ) -> None:
        """Apply and persist a policy setting atomically."""
        async with self._operation_lock:
            update(self.child_policy)
            await self._async_save_policy_locked()
        self.async_update_listeners()

    async def async_reset_daily(self, tv_key: str) -> None:
        """Reset today's child-policy counters for one TV."""
        async with self._operation_lock:
            self.child_policy.reset_daily(tv_key, dt_util.now())
            await self._async_save_policy_locked()
        self.async_update_listeners()

    async def async_set_child_enabled(
        self, tv_key: str, enabled: bool
    ) -> None:
        """Enable or disable child control and reconcile current state."""
        async with self._operation_lock:
            now = dt_util.now()
            self.child_policy.set_child_enabled(tv_key, enabled)
            currently_enabled = bool(
                self.data
                and self.data.get("statuses", {})
                .get(tv_key, {})
                .get("internet_enabled", False)
            )
            if (
                enabled
                and currently_enabled
                and self._tv_activity(tv_key, now) is True
            ):
                self.child_policy.start_session(tv_key, now)
            elif not enabled:
                self.child_policy.end_session(tv_key, now)
            await self._async_save_policy_locked()
        await self.async_request_refresh()


class ChildPolicyDenied(Exception):
    """Raised when child policy rejects an enable request."""
