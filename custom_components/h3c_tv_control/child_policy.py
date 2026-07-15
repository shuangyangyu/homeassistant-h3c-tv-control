"""Child internet control policy engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

from .const import (
    DEFAULT_COOLDOWN_MINUTES,
    DEFAULT_DAILY_MINUTES,
    DEFAULT_SESSION_MINUTES,
    DEFAULT_WINDOW_PRESET,
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    TVS,
    WINDOW_PRESETS,
)

SESSION_LIMIT_REASON = "单次上网时长已到"


def _local_now() -> datetime:
    """Return a timezone-aware local datetime for non-HA callers."""
    return datetime.now().astimezone()


@dataclass
class TvChildSettings:
    """Per-TV child control settings."""

    child_enabled: bool = False
    session_minutes: int = DEFAULT_SESSION_MINUTES
    daily_minutes: int = DEFAULT_DAILY_MINUTES
    cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES
    window_start: str = DEFAULT_WINDOW_START
    window_end: str = DEFAULT_WINDOW_END


@dataclass
class TvChildRuntime:
    """Per-TV runtime state for child control."""

    daily_used_minutes: float = 0.0
    usage_date: str = ""
    # Original start of the uninterrupted session, used for the session limit.
    session_start: str | None = None
    # Start of the active segment counted toward the current calendar day.
    usage_start: str | None = None
    # Earliest time a new session may start after using a full session.
    cooldown_until: str | None = None


@dataclass
class TvChildState:
    """Combined settings and runtime for one TV."""

    settings: TvChildSettings = field(default_factory=TvChildSettings)
    runtime: TvChildRuntime = field(default_factory=TvChildRuntime)


class ChildPolicyManager:
    """Manage child internet time limits for all TVs."""

    def __init__(self) -> None:
        """Initialize policy state for all configured televisions."""
        self._states = {key: TvChildState() for key in TVS}
        self._dirty = False

    @property
    def dirty(self) -> bool:
        """Return whether persistent state changed."""
        return self._dirty

    def mark_clean(self) -> None:
        """Mark current state as persisted."""
        self._dirty = False

    def load_from_dict(self, data: dict[str, Any]) -> None:
        """Restore state from persistent storage."""
        for key in TVS:
            if key not in data:
                continue
            entry = data[key]
            settings = entry.get("settings", {})
            runtime = entry.get("runtime", {})
            session_start = runtime.get("session_start")
            self._states[key] = TvChildState(
                settings=TvChildSettings(
                    child_enabled=settings.get("child_enabled", False),
                    session_minutes=settings.get(
                        "session_minutes", DEFAULT_SESSION_MINUTES
                    ),
                    daily_minutes=settings.get(
                        "daily_minutes", DEFAULT_DAILY_MINUTES
                    ),
                    cooldown_minutes=settings.get(
                        "cooldown_minutes", DEFAULT_COOLDOWN_MINUTES
                    ),
                    window_start=settings.get(
                        "window_start", DEFAULT_WINDOW_START
                    ),
                    window_end=settings.get("window_end", DEFAULT_WINDOW_END),
                ),
                runtime=TvChildRuntime(
                    daily_used_minutes=runtime.get("daily_used_minutes", 0.0),
                    usage_date=runtime.get("usage_date", ""),
                    session_start=session_start,
                    # Backward compatibility with version 1 storage.
                    usage_start=runtime.get("usage_start", session_start),
                    cooldown_until=runtime.get("cooldown_until"),
                ),
            )
        self._dirty = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize state for persistent storage."""
        return {
            key: {
                "settings": {
                    "child_enabled": state.settings.child_enabled,
                    "session_minutes": state.settings.session_minutes,
                    "daily_minutes": state.settings.daily_minutes,
                    "cooldown_minutes": state.settings.cooldown_minutes,
                    "window_start": state.settings.window_start,
                    "window_end": state.settings.window_end,
                },
                "runtime": {
                    "daily_used_minutes": state.runtime.daily_used_minutes,
                    "usage_date": state.runtime.usage_date,
                    "session_start": state.runtime.session_start,
                    "usage_start": state.runtime.usage_start,
                    "cooldown_until": state.runtime.cooldown_until,
                },
            }
            for key, state in self._states.items()
        }

    def get_state(self, tv_key: str) -> TvChildState:
        """Return policy state for one TV."""
        return self._states[tv_key]

    def set_child_enabled(self, tv_key: str, enabled: bool) -> None:
        """Set whether child control is enabled for one TV."""
        self._states[tv_key].settings.child_enabled = enabled
        self._dirty = True

    def set_session_minutes(self, tv_key: str, minutes: int) -> None:
        """Set the single-session limit for one TV."""
        self._states[tv_key].settings.session_minutes = minutes
        self._dirty = True

    def set_daily_minutes(self, tv_key: str, minutes: int) -> None:
        """Set the daily usage limit for one TV."""
        self._states[tv_key].settings.daily_minutes = minutes
        self._dirty = True

    def set_cooldown_minutes(self, tv_key: str, minutes: int) -> None:
        """Set the cooldown after a full session for one TV."""
        self._states[tv_key].settings.cooldown_minutes = minutes
        self._dirty = True

    def set_window_start(self, tv_key: str, time_str: str) -> None:
        """Set the beginning of the allowed usage window."""
        self._parse_time(time_str)
        self._states[tv_key].settings.window_start = time_str
        self._dirty = True

    def set_window_end(self, tv_key: str, time_str: str) -> None:
        """Set the end of the allowed usage window."""
        self._parse_time(time_str)
        self._states[tv_key].settings.window_end = time_str
        self._dirty = True

    def set_window_preset(self, tv_key: str, preset: str) -> None:
        """Apply a predefined allowed usage window."""
        if preset not in WINDOW_PRESETS:
            raise ValueError(f"Unknown window preset: {preset}")
        start, end = WINDOW_PRESETS[preset]
        settings = self._states[tv_key].settings
        settings.window_start = start
        settings.window_end = end
        self._dirty = True

    def get_window_preset(self, tv_key: str) -> str:
        """Return the preset matching the configured usage window."""
        settings = self._states[tv_key].settings
        current = (settings.window_start, settings.window_end)
        for preset, window in WINDOW_PRESETS.items():
            if window == current:
                return preset
        return DEFAULT_WINDOW_PRESET

    def ensure_current_date(
        self, tv_key: str, now: datetime | None = None
    ) -> None:
        """Roll daily usage to a new local calendar day.

        An active session keeps its original session start for the single-session
        limit, while daily accounting restarts at local midnight.
        """
        now = now or _local_now()
        runtime = self._states[tv_key].runtime
        today = now.date().isoformat()
        if runtime.usage_date == today:
            return

        runtime.daily_used_minutes = 0.0
        runtime.usage_date = today
        runtime.cooldown_until = None
        if runtime.session_start:
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            runtime.usage_start = midnight.isoformat()
        else:
            runtime.usage_start = None
        self._dirty = True

    def reset_daily(self, tv_key: str, now: datetime | None = None) -> None:
        """Reset today's usage and cooldown while preserving an active session."""
        now = now or _local_now()
        runtime = self._states[tv_key].runtime
        runtime.daily_used_minutes = 0.0
        runtime.usage_date = now.date().isoformat()
        runtime.cooldown_until = None
        runtime.usage_start = now.isoformat() if runtime.session_start else None
        self._dirty = True

    @staticmethod
    def _parse_time(time_str: str) -> time:
        parts = time_str.split(":")
        if not 2 <= len(parts) <= 3:
            raise ValueError(f"无效时间: {time_str}")
        return time(
            int(parts[0]),
            int(parts[1]),
            int(parts[2]) if len(parts) == 3 else 0,
        )

    def _in_time_window(self, tv_key: str, now: datetime) -> bool:
        settings = self._states[tv_key].settings
        start = self._parse_time(settings.window_start)
        end = self._parse_time(settings.window_end)
        current = now.time().replace(tzinfo=None)
        if start == end:
            return True
        if start <= end:
            return start <= current <= end
        return current >= start or current <= end

    @staticmethod
    def _parse_datetime(value: str, now: datetime) -> datetime:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=now.tzinfo)
        return parsed

    def can_enable(
        self, tv_key: str, now: datetime | None = None
    ) -> tuple[bool, str]:
        """Check whether internet can be enabled under child policy."""
        now = now or _local_now()
        state = self._states[tv_key]
        if not state.settings.child_enabled:
            return True, ""

        self.ensure_current_date(tv_key, now)
        if not self._in_time_window(tv_key, now):
            return False, "不在允许上网时间段"
        if self.get_daily_used(tv_key, now) >= state.settings.daily_minutes:
            return False, "今日上网时长已用完"
        cooldown_remaining = self.get_cooldown_remaining(tv_key, now)
        if cooldown_remaining > 0:
            return False, f"单次用满后冷却中，还需 {cooldown_remaining:.0f} 分钟"
        return True, ""

    def start_session(
        self, tv_key: str, now: datetime | None = None
    ) -> bool:
        """Start a session unless one is already active."""
        now = now or _local_now()
        self.ensure_current_date(tv_key, now)
        runtime = self._states[tv_key].runtime
        if runtime.session_start:
            return False
        runtime.session_start = now.isoformat()
        runtime.usage_start = now.isoformat()
        runtime.cooldown_until = None
        self._dirty = True
        return True

    def discard_session(self, tv_key: str) -> bool:
        """Discard a stale session without adding usage."""
        runtime = self._states[tv_key].runtime
        if not runtime.session_start and not runtime.usage_start:
            return False
        runtime.session_start = None
        runtime.usage_start = None
        self._dirty = True
        return True

    def end_session(
        self,
        tv_key: str,
        now: datetime | None = None,
        *,
        start_cooldown: bool = False,
    ) -> bool:
        """End a session and account usage for the current day."""
        now = now or _local_now()
        self.ensure_current_date(tv_key, now)
        runtime = self._states[tv_key].runtime
        if not runtime.session_start:
            return False

        usage_start_value = runtime.usage_start or runtime.session_start
        usage_start = self._parse_datetime(usage_start_value, now)
        elapsed = max(0.0, (now - usage_start).total_seconds() / 60)
        runtime.daily_used_minutes += elapsed
        runtime.session_start = None
        runtime.usage_start = None
        if start_cooldown:
            cooldown_minutes = self._states[tv_key].settings.cooldown_minutes
            runtime.cooldown_until = (
                now + timedelta(minutes=cooldown_minutes)
            ).isoformat()
        self._dirty = True
        return True

    def should_disable(
        self, tv_key: str, internet_enabled: bool, now: datetime | None = None
    ) -> tuple[bool, str]:
        """Return whether internet should be disabled without mutating session."""
        if not internet_enabled:
            return False, ""

        now = now or _local_now()
        state = self._states[tv_key]
        if not state.settings.child_enabled:
            return False, ""

        self.ensure_current_date(tv_key, now)
        if not self._in_time_window(tv_key, now):
            return True, "已超出允许上网时间段"
        if self.get_daily_used(tv_key, now) >= state.settings.daily_minutes:
            return True, "今日上网时长已用完"
        if self.get_cooldown_remaining(tv_key, now) > 0:
            return True, "单次用满后仍在冷却"

        runtime = state.runtime
        if runtime.session_start:
            start = self._parse_datetime(runtime.session_start, now)
            elapsed = max(0.0, (now - start).total_seconds() / 60)
            if elapsed >= state.settings.session_minutes:
                return True, SESSION_LIMIT_REASON
        return False, ""

    def get_cooldown_remaining(
        self, tv_key: str, now: datetime | None = None
    ) -> float:
        """Return remaining cooldown minutes before another session."""
        now = now or _local_now()
        self.ensure_current_date(tv_key, now)
        cooldown_until = self._states[tv_key].runtime.cooldown_until
        if not cooldown_until:
            return 0.0
        until = self._parse_datetime(cooldown_until, now)
        return max(0.0, (until - now).total_seconds() / 60)

    def get_session_remaining(
        self, tv_key: str, now: datetime | None = None
    ) -> float:
        """Return remaining minutes in the current session."""
        now = now or _local_now()
        self.ensure_current_date(tv_key, now)
        state = self._states[tv_key]
        runtime = state.runtime
        if not runtime.session_start or not state.settings.child_enabled:
            return 0.0

        start = self._parse_datetime(runtime.session_start, now)
        elapsed = max(0.0, (now - start).total_seconds() / 60)
        remaining_session = state.settings.session_minutes - elapsed
        remaining_daily = state.settings.daily_minutes - self.get_daily_used(
            tv_key, now
        )
        return max(0.0, min(remaining_session, remaining_daily))

    def get_daily_used(
        self, tv_key: str, now: datetime | None = None
    ) -> float:
        """Return minutes used today, including the active segment."""
        now = now or _local_now()
        self.ensure_current_date(tv_key, now)
        runtime = self._states[tv_key].runtime
        used = runtime.daily_used_minutes
        if runtime.session_start:
            usage_start_value = runtime.usage_start or runtime.session_start
            usage_start = self._parse_datetime(usage_start_value, now)
            used += max(0.0, (now - usage_start).total_seconds() / 60)
        return round(used, 1)

    def get_daily_remaining(
        self, tv_key: str, now: datetime | None = None
    ) -> float:
        """Return remaining daily minutes."""
        now = now or _local_now()
        settings = self._states[tv_key].settings
        return max(
            0.0, settings.daily_minutes - self.get_daily_used(tv_key, now)
        )
