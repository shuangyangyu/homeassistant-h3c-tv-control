"""Constants for H3C TV Control integration."""

from typing import TypedDict


class TVConfig(TypedDict):
    """Configuration for one controlled television."""

    name: str
    ip: str
    mac: str
    permit_rule: int
    deny_rule: int


DOMAIN = "h3c_tv_control"

DEFAULT_HOST = "192.168.1.254"
DEFAULT_USERNAME = "hass_robot"
DEFAULT_PORT = 23
DEFAULT_ACL_ID = 3000
DEFAULT_SCAN_INTERVAL = 60

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_PORT = "port"
CONF_ACL_ID = "acl_id"
TV_MEDIA_PLAYER_OPTIONS: dict[str, str] = {
    "master_bedroom": "master_bedroom_media_player",
    "living_room": "living_room_media_player",
    "elder_room": "elder_room_media_player",
    "study_room": "study_room_media_player",
}

ATTR_INTERNET_ENABLED = "internet_enabled"
ATTR_SESSION_REMAINING = "session_remaining_minutes"
ATTR_DAILY_USED = "daily_used_minutes"
ATTR_CHILD_ENABLED = "child_control_enabled"
ATTR_DENY_REASON = "deny_reason"

# Child control defaults per TV
DEFAULT_SESSION_MINUTES = 30
DEFAULT_DAILY_MINUTES = 90
DEFAULT_COOLDOWN_MINUTES = 60
DEFAULT_WINDOW_PRESET = "daytime"
WINDOW_PRESETS: dict[str, tuple[str, str]] = {
    "all_day": ("00:00:00", "00:00:00"),
    "daytime": ("08:00:00", "20:00:00"),
    "nighttime": ("20:00:00", "08:00:00"),
}
DEFAULT_WINDOW_START, DEFAULT_WINDOW_END = WINDOW_PRESETS[DEFAULT_WINDOW_PRESET]

MIN_SESSION_MINUTES = 5
MAX_SESSION_MINUTES = 180
MIN_DAILY_MINUTES = 10
MAX_DAILY_MINUTES = 480
MIN_COOLDOWN_MINUTES = 5
MAX_COOLDOWN_MINUTES = 180

TVS: dict[str, TVConfig] = {
    "master_bedroom": {
        "name": "主卧电视上网",
        "ip": "192.168.1.24",
        "mac": "cc98-8b23-abaa",
        "permit_rule": 10,
        "deny_rule": 15,
    },
    "living_room": {
        "name": "客厅电视上网",
        "ip": "192.168.1.25",
        "mac": "88c9-e8d1-bcb0",
        "permit_rule": 20,
        "deny_rule": 25,
    },
    "elder_room": {
        "name": "老人房电视上网",
        "ip": "192.168.1.26",
        "mac": "cc98-8b36-afc7",
        "permit_rule": 30,
        "deny_rule": 35,
    },
    "study_room": {
        "name": "书房电视上网",
        "ip": "192.168.1.27",
        "mac": "7026-05e6-0afd",
        "permit_rule": 40,
        "deny_rule": 45,
    },
}
