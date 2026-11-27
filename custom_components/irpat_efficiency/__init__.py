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
    from .history_store import RoomHistory
    from .journal_store import HydraulicJournal
    from homeassistant.helpers.storage import Store

    runtime = hass.data.setdefault(DOMAIN, {"active_entries": set(), "histories": {}, "journals": {}})
    journal = HydraulicJournal(Store(hass, 1, f"{DOMAIN}.journal.{entry.entry_id}"))
    await journal.async_load()
    history = RoomHistory(hass, entry)
    await history.async_start()
    try:
        await panel.async_register(hass)
    except Exception:
        await history.async_stop()
        raise
    runtime["journals"][entry.entry_id] = journal
    runtime["histories"][entry.entry_id] = history
    runtime["active_entries"].add(entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the overview when the last entry is unloaded."""
    from . import panel

    runtime = hass.data.get(DOMAIN)
    if runtime:
        journal = runtime["journals"].pop(entry.entry_id, None)
        if journal is not None:
            await journal.async_close()
        history = runtime["histories"].pop(entry.entry_id, None)
        if history is not None:
            await history.async_stop()
        runtime["active_entries"].discard(entry.entry_id)
        if not runtime["active_entries"]:
            panel.async_remove(hass)
    return True
