"""Tests for the child policy state machine."""

from datetime import datetime

from custom_components.h3c_tv_control.child_policy import ChildPolicyManager

TV_KEY = "living_room"


def _prepare_policy() -> ChildPolicyManager:
    policy = ChildPolicyManager()
    policy.set_child_enabled(TV_KEY, True)
    policy.set_session_minutes(TV_KEY, 30)
    policy.set_daily_minutes(TV_KEY, 90)
    policy.set_window_preset(TV_KEY, "all_day")
    return policy


def test_cross_midnight_keeps_session_and_splits_daily_usage() -> None:
    """An active session keeps its session limit and restarts daily usage."""
    policy = _prepare_policy()
    start = datetime.fromisoformat("2026-07-15T23:50:00+08:00")
    now = datetime.fromisoformat("2026-07-16T00:10:00+08:00")

    policy.start_session(TV_KEY, start)

    assert policy.get_daily_used(TV_KEY, now) == 10.0
    assert policy.get_session_remaining(TV_KEY, now) == 10.0
    assert policy.get_state(TV_KEY).runtime.session_start == start.isoformat()


def test_disable_decision_has_no_session_side_effects() -> None:
    """A failed device command can safely retry the same decision."""
    policy = _prepare_policy()
    start = datetime.fromisoformat("2026-07-15T18:00:00+08:00")
    now = datetime.fromisoformat("2026-07-15T18:31:00+08:00")
    policy.start_session(TV_KEY, start)

    assert policy.should_disable(TV_KEY, True, now)[0] is True
    assert policy.should_disable(TV_KEY, True, now)[0] is True
    assert policy.get_state(TV_KEY).runtime.session_start == start.isoformat()


def test_repeated_start_does_not_reset_session() -> None:
    """Repeated turn-on requests cannot reset the single-session timer."""
    policy = _prepare_policy()
    start = datetime.fromisoformat("2026-07-15T18:00:00+08:00")
    later = datetime.fromisoformat("2026-07-15T18:20:00+08:00")

    assert policy.start_session(TV_KEY, start) is True
    assert policy.start_session(TV_KEY, later) is False
    assert policy.get_state(TV_KEY).runtime.session_start == start.isoformat()


def test_discard_session_does_not_add_usage() -> None:
    """Removing a TV binding discards stale ACL-based timing."""
    policy = _prepare_policy()
    start = datetime.fromisoformat("2026-07-15T18:00:00+08:00")
    later = datetime.fromisoformat("2026-07-15T18:20:00+08:00")
    policy.start_session(TV_KEY, start)

    assert policy.discard_session(TV_KEY) is True
    assert policy.get_daily_used(TV_KEY, later) == 0.0


def test_allowed_window_presets() -> None:
    """Preset windows enforce daytime, nighttime, and all-day access."""
    policy = _prepare_policy()
    noon = datetime.fromisoformat("2026-07-15T12:00:00+08:00")
    late = datetime.fromisoformat("2026-07-15T23:00:00+08:00")

    policy.set_window_preset(TV_KEY, "daytime")
    assert policy.can_enable(TV_KEY, noon)[0] is True
    assert policy.can_enable(TV_KEY, late)[0] is False

    policy.set_window_preset(TV_KEY, "nighttime")
    assert policy.can_enable(TV_KEY, noon)[0] is False
    assert policy.can_enable(TV_KEY, late)[0] is True

    policy.set_window_preset(TV_KEY, "all_day")
    assert policy.can_enable(TV_KEY, noon)[0] is True


def test_full_session_uses_configured_cooldown() -> None:
    """A full session blocks access for the configured cooldown."""
    policy = _prepare_policy()
    policy.set_cooldown_minutes(TV_KEY, 15)
    start = datetime.fromisoformat("2026-07-15T18:00:00+08:00")
    limit = datetime.fromisoformat("2026-07-15T18:30:00+08:00")
    before_ready = datetime.fromisoformat("2026-07-15T18:44:00+08:00")
    ready = datetime.fromisoformat("2026-07-15T18:45:00+08:00")

    policy.start_session(TV_KEY, start)
    should_disable, reason = policy.should_disable(TV_KEY, True, limit)
    assert should_disable is True
    assert reason == "单次上网时长已到"

    policy.end_session(TV_KEY, limit, start_cooldown=True)
    assert policy.get_daily_used(TV_KEY, limit) == 30.0
    assert policy.can_enable(TV_KEY, before_ready)[0] is False
    assert policy.can_enable(TV_KEY, ready)[0] is True


def test_daily_reset_clears_usage_and_cooldown() -> None:
    """Midnight restores daily usage and cancels a previous-day cooldown."""
    policy = _prepare_policy()
    start = datetime.fromisoformat("2026-07-15T23:20:00+08:00")
    limit = datetime.fromisoformat("2026-07-15T23:50:00+08:00")
    next_day = datetime.fromisoformat("2026-07-16T00:10:00+08:00")

    policy.start_session(TV_KEY, start)
    policy.end_session(TV_KEY, limit, start_cooldown=True)

    assert policy.can_enable(TV_KEY, next_day)[0] is True
    assert policy.get_daily_used(TV_KEY, next_day) == 0.0


def test_manual_daily_reset_clears_usage_and_cooldown() -> None:
    """The manual reset performs the same daily counter reset."""
    policy = _prepare_policy()
    start = datetime.fromisoformat("2026-07-15T18:00:00+08:00")
    limit = datetime.fromisoformat("2026-07-15T18:30:00+08:00")
    reset_at = datetime.fromisoformat("2026-07-15T18:40:00+08:00")

    policy.start_session(TV_KEY, start)
    policy.end_session(TV_KEY, limit, start_cooldown=True)
    policy.reset_daily(TV_KEY, reset_at)

    assert policy.get_daily_used(TV_KEY, reset_at) == 0.0
    assert policy.get_cooldown_remaining(TV_KEY, reset_at) == 0.0
    assert policy.can_enable(TV_KEY, reset_at)[0] is True
