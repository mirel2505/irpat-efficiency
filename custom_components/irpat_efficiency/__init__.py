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
    from .profile_store import ProfileStore
    from .defrost_monitor import DefrostMonitor
    from .energy_monitor import EnergyMonitor
    from homeassistant.helpers.storage import Store

    runtime = hass.data.setdefault(DOMAIN, {"active_entries": set(), "histories": {}, "journals": {}, "profiles": {}, "defrost_monitors": {}, "energy_monitors": {}})
    journal = HydraulicJournal(Store(hass, 1, f"{DOMAIN}.journal.{entry.entry_id}"))
    await journal.async_load()
    profiles = ProfileStore(Store(hass, 1, f"{DOMAIN}.profiles.{entry.entry_id}"))
    await profiles.async_load()
    history = RoomHistory(hass, entry)
    await history.async_start()
    monitor = DefrostMonitor(hass, entry)
    energy = EnergyMonitor(hass, entry)
    try:
        await monitor.async_start()
        await energy.async_start()
        await panel.async_register(hass)
    except Exception:
        await energy.async_stop()
        await monitor.async_stop()
        await history.async_stop()
        raise
    runtime["energy_monitors"][entry.entry_id] = energy
    runtime["defrost_monitors"][entry.entry_id] = monitor
    runtime["profiles"][entry.entry_id] = profiles
    runtime["journals"][entry.entry_id] = journal
    runtime["histories"][entry.entry_id] = history
    runtime["active_entries"].add(entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the overview when the last entry is unloaded."""
    from . import panel

    runtime = hass.data.get(DOMAIN)
    if runtime:
        energy = runtime["energy_monitors"].pop(entry.entry_id, None)
        if energy is not None:
            await energy.async_stop()
        monitor = runtime["defrost_monitors"].pop(entry.entry_id, None)
        if monitor is not None:
            await monitor.async_stop()
        profiles = runtime["profiles"].pop(entry.entry_id, None)
        if profiles is not None:
            await profiles.async_close()
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
