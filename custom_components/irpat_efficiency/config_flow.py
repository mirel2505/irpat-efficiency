"""Initial configuration without hardcoded devices or names."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CIRCUIT_CONTROLS, DOMAIN, OPERATING_MODES
from .options_flow import IrpatOptionsFlow


class IrpatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create a local installation."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return IrpatOptionsFlow()

    async def async_step_user(self, user_input=None):
        """Configure the home and operating assumptions."""
        self._async_abort_entries_match({})
        errors = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name or len(name) > 120:
                errors[CONF_NAME] = "invalid_name"
            else:
                return self.async_create_entry(
                    title=name,
                    data={**user_input, CONF_NAME: name},
                )
        schema = vol.Schema({
            vol.Required(CONF_NAME): selector.TextSelector(),
            vol.Required("operating_mode", default="unknown"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=list(OPERATING_MODES),
                                               translation_key="operating_mode",
                                               mode=selector.SelectSelectorMode.DROPDOWN)
            ),
            vol.Required("circuit_control", default="unknown"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=list(CIRCUIT_CONTROLS),
                                               translation_key="circuit_control",
                                               mode=selector.SelectSelectorMode.DROPDOWN)
            ),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
