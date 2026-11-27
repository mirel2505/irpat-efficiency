"""Local, advisory-only radiant floor system integration."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialize the local overview; no equipment calls."""
    from . import panel

    runtime = hass.data.setdefault(DOMAIN, {"active_entries": set()})
    await panel.async_register(hass)
    runtime["active_entries"].add(entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the overview when the last entry is unloaded."""
    from . import panel

    runtime = hass.data.get(DOMAIN)
    if runtime:
        runtime["active_entries"].discard(entry.entry_id)
        if not runtime["active_entries"]:
            panel.async_remove(hass)
    return True
