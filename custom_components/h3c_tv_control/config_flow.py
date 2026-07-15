"""Config flow for H3C TV Control."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .const import (
    CONF_ACL_ID,
    DEFAULT_ACL_ID,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_USERNAME,
    DOMAIN,
    TV_MEDIA_PLAYER_OPTIONS,
)
from .h3c_client import H3CAuthenticationError, H3CConnectionError, H3CTVClient

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_ACL_ID, default=DEFAULT_ACL_ID): int,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate connection to H3C switch."""
    client = H3CTVClient(
        host=data[CONF_HOST],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        port=data.get(CONF_PORT, DEFAULT_PORT),
        acl_id=data.get(CONF_ACL_ID, DEFAULT_ACL_ID),
    )

    try:
        await hass.async_add_executor_job(client.get_statuses)
    except H3CAuthenticationError as err:
        _LOGGER.warning("Authentication failed: %s", err)
        raise InvalidAuth from err
    except H3CConnectionError as err:
        _LOGGER.error("Connection test failed: %s", err)
        raise CannotConnect from err
    except Exception as err:
        _LOGGER.error("Switch validation failed: %s", err)
        raise CannotConnect from err

    return {"title": f"H3C TV Control ({data[CONF_HOST]})"}


class H3CTVControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for H3C TV Control."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the TV entity mapping options flow."""
        return H3CTVControlOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial user configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )


class H3CTVControlOptionsFlow(OptionsFlow):
    """Configure media player entities used for viewing-time accounting."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the media player mapped to each TV."""
        errors: dict[str, str] = {}
        if user_input is not None:
            selected = [value for value in user_input.values() if value]
            if len(selected) != len(set(selected)):
                errors["base"] = "duplicate_tv_entities"
            else:
                return self.async_create_entry(title="", data=user_input)

        schema: dict[vol.Marker, selector.EntitySelector] = {}
        for option_key in TV_MEDIA_PLAYER_OPTIONS.values():
            current = self.config_entry.options.get(option_key)
            schema[
                vol.Optional(
                    option_key,
                    description={"suggested_value": current},
                )
            ] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain=Platform.MEDIA_PLAYER)
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
