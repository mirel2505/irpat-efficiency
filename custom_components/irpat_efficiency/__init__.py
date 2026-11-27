"""Local, advisory-only radiant floor system integration."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .const import DOMAIN
from .storage_identity import storage_key

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
# Registration keys are also consumed by the administrator overview API.
_COMPONENTS = (
    ("report_stores", "async_load", "async_close"),
    ("journals", "async_load", "async_close"),
    ("profiles", "async_load", "async_close"),
    ("histories", "async_start", "async_stop"),
    ("defrost_monitors", "async_start", "async_stop"),
    ("energy_monitors", "async_start", "async_stop"),
    ("mode_monitors", "async_start", "async_stop"),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Start components in order and unwind partially initialized resources."""
    from . import panel
    from .history_store import RoomHistory
    from .journal_store import HydraulicJournal
    from .profile_store import ProfileStore
    from .defrost_monitor import DefrostMonitor
    from .energy_monitor import EnergyMonitor
    from .mode_monitor import ModeMonitor
    from .report_store import ReportStore
    from homeassistant.helpers.storage import Store

    runtime = hass.data.setdefault(DOMAIN, {})
    active = runtime.setdefault("active_entries", set())
    starting = runtime.setdefault("starting_entries", set())
    eid = entry.entry_id
    for key, _, _ in _COMPONENTS:
        runtime.setdefault(key, {})
    if eid in active or eid in starting or any(eid in runtime[k] for k, _, _ in _COMPONENTS):
        _LOGGER.warning("Entry already initialized or awaiting cleanup: %s", eid)
        return False
    factories = (
        lambda: ReportStore(Store(hass, 1, storage_key(entry, "reports"))),
        lambda: HydraulicJournal(Store(hass, 1, storage_key(entry, "journal"))),
        lambda: ProfileStore(Store(hass, 1, storage_key(entry, "profiles"))),
        lambda: RoomHistory(hass, entry),
        lambda: DefrostMonitor(hass, entry),
        lambda: EnergyMonitor(hass, entry),
        lambda: ModeMonitor(hass, entry),
    )
    created = []
    starting.add(eid)
    try:
        for (key, start, stop), factory in zip(_COMPONENTS, factories, strict=True):
            component = factory()
            created.append((key, stop, component))
            await getattr(component, start)()
        await panel.async_register(hass)
        for key, _, component in created:
            runtime[key][eid] = component
        active.add(eid)
        return True
    except BaseException:
        for key, stop, component in reversed(created):
            try:
                await getattr(component, stop)()
            except Exception:
                # Keep a failed resource reachable for a subsequent unload attempt.
                runtime[key][eid] = component
                _LOGGER.exception("Could not roll back %s", key)
        raise
    finally:
        starting.discard(eid)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Stop every component; retain failed resources for retry."""
    from . import panel

    runtime = hass.data.get(DOMAIN)
    if not runtime:
        return True
    eid = entry.entry_id
    if eid in runtime.get("starting_entries", set()):
        return False
    failed = False
    for key, _, stop in reversed(_COMPONENTS):
        resources = runtime.get(key, {})
        component = resources.get(eid)
        if component is None:
            continue
        try:
            await getattr(component, stop)()
        except Exception:
            failed = True
            _LOGGER.exception("Could not stop %s", key)
        else:
            resources.pop(eid, None)
    if failed:
        return False
    active = runtime.get("active_entries", set())
    active.discard(eid)
    if not active:
        try:
            panel.async_remove(hass)
        except Exception:
            _LOGGER.exception("Could not remove THERMELYVO panel")
            return False
    return True
