"""Register the local, administrator-only overview panel."""
from pathlib import Path
import logging

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import callback
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import DOMAIN
from .topology import empty_topology
from .temperature_reader import read_rooms
from .telemetry_reader import read_telemetry
from .live_diagnostics import live_diagnostics
from .operation_mode import classify_mode

_LOGGER = logging.getLogger(__name__)

PANEL_PATH = "irpat-efficiency"
ASSET_URL = "/irpat_efficiency_assets/panel.js"


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/overview"})
@websocket_api.require_admin
@callback
def ws_overview(hass, connection, msg):
    """Return configuration only to an authenticated administrator."""
    entries = [entry for entry in hass.config_entries.async_entries(DOMAIN)
               if entry.entry_id in hass.data.get(DOMAIN, {}).get("active_entries", set())]
    overview = []
    for entry in entries:
        topology = entry.options.get("topology", empty_topology())
        history = hass.data[DOMAIN]["histories"].get(entry.entry_id)
        journal = hass.data[DOMAIN]["journals"].get(entry.entry_id)
        profiles = hass.data[DOMAIN]["profiles"].get(entry.entry_id)
        monitor = hass.data[DOMAIN]["defrost_monitors"].get(entry.entry_id)
        energy = hass.data[DOMAIN]["energy_monitors"].get(entry.entry_id)
        mode_monitor = hass.data[DOMAIN]["mode_monitors"].get(entry.entry_id)
        rooms = read_rooms(hass, topology)
        telemetry = read_telemetry(hass, topology)
        modes = {}
        for source in topology["sources"]:
            binding = source.get("mode_binding")
            if not binding:
                continue
            state = hass.states.get(binding["entity_id"])
            reported = (getattr(state, "last_reported", None) or state.last_updated) if state else None
            modes[source["id"]] = classify_mode(
                binding, state.state if state else None,
                reported.timestamp() if reported else None, dt_util.utcnow().timestamp())
        overview.append({"entry_id": entry.entry_id, "name": entry.title, "topology": topology,
                         "profiles": profiles.list_profiles() if profiles else [],
                         "defrost": monitor.overview(topology) if monitor else {},
                         "journal": journal.recent() if journal else [],
                         "room_temperatures": rooms,
                         "telemetry": telemetry,
                         "reported_modes": modes,
                         "mode_history": mode_monitor.overview(topology) if mode_monitor else {},
                         "energy_history": energy.overview(topology, telemetry) if energy else {},
                         "energy_save_failed": energy.save_failed if energy else False,
                         "live_diagnostics": live_diagnostics(topology, telemetry, rooms, dt_util.utcnow().timestamp()),
                         "history": history.overview(topology) if history else {},
                         "history_save_failed": history.save_failed if history else False,
                         "thermal_diagnostics": history.diagnostics(topology, journal.entries) if history and journal else {},
                         "weather_observations": history.weather_observations(topology) if history else {}})
    connection.send_result(msg["id"], overview)


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/journal_append",
    vol.Required("entry_id"): str,
    vol.Required("manifold_id"): str,
    vol.Required("readings"): {str: vol.Any(int, float, None)},
    vol.Required("phase"): vol.In(("observation", "before", "after")),
    vol.Optional("previous_id"): str,
    vol.Optional("manifold_total_lmin"): vol.Any(int, float),
    vol.Optional("source_total_m3h"): vol.Any(int, float),
    vol.Optional("note", default=""): vol.All(str, vol.Length(max=2000)),
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_journal_append(hass, connection, msg):
    """Save a manual observation, never control hardware."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    journal = hass.data.get(DOMAIN, {}).get("journals", {}).get(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN or journal is None:
        connection.send_error(msg["id"], "not_found", "No active journal")
        return
    topology = entry.options.get("topology", empty_topology())
    rooms = read_rooms(hass, topology)
    manifold = next((m for m in topology["manifolds"] if m["id"] == msg["manifold_id"]), None)
    zone = next((z for z in topology["zones"] if manifold and z["id"] == manifold["zone_id"]), None)
    context = {"room_temperatures": rooms, "zone": zone,
               "telemetry": read_telemetry(hass, topology)}
    try:
        result = await journal.async_append(
            topology, msg["manifold_id"], msg["readings"],
            phase=msg["phase"], previous_id=msg.get("previous_id"),
            manifold_total_lmin=msg.get("manifold_total_lmin"),
            source_total_m3h=msg.get("source_total_m3h"),
            note=msg["note"], context=context,
        )
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_observation", str(exc))
        return
    except Exception:
        _LOGGER.exception("Could not save hydraulic observation")
        connection.send_error(msg["id"], "save_failed", "Journal save failed")
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/profile_create",
    vol.Required("entry_id"): str,
    vol.Required("zone_id"): str,
    vol.Required("name"): vol.All(str, vol.Length(min=1, max=120)),
    vol.Required("mode"): vol.In(("heating", "cooling")),
    vol.Required("snapshot_ids"): [str],
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_profile_create(hass, connection, msg):
    """Persist a manual profile from existing journal observations."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    runtime = hass.data.get(DOMAIN, {})
    profiles = runtime.get("profiles", {}).get(msg["entry_id"])
    journal = runtime.get("journals", {}).get(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN or profiles is None or journal is None:
        connection.send_error(msg["id"], "not_found", "No active profile store")
        return
    try:
        result = await profiles.async_create(
            entry.options.get("topology", empty_topology()), msg["zone_id"], msg["name"],
            msg["mode"], msg["snapshot_ids"], journal.entries,
        )
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_profile", str(exc))
        return
    except Exception:
        _LOGGER.exception("Could not save reference profile")
        connection.send_error(msg["id"], "save_failed", "Profile save failed")
        return
    connection.send_result(msg["id"], result)


async def async_register(hass):
    """Register the API and static asset once per HA runtime."""
    runtime = hass.data[DOMAIN]
    if not runtime.get("static_registered"):
        await hass.http.async_register_static_paths([
            StaticPathConfig(ASSET_URL, str(Path(__file__).parent / "frontend" / "panel.js"), False)
        ])
        runtime["static_registered"] = True
    if not runtime.get("api_registered"):
        websocket_api.async_register_command(hass, ws_overview)
        websocket_api.async_register_command(hass, ws_journal_append)
        websocket_api.async_register_command(hass, ws_profile_create)
        runtime["api_registered"] = True
    if not runtime.get("panel_registered"):
        await panel_custom.async_register_panel(
            hass, frontend_url_path=PANEL_PATH,
            webcomponent_name="irpat-efficiency-panel", module_url=ASSET_URL,
            sidebar_title="irPaT & Eficiență", sidebar_icon="mdi:heating-coil",
            require_admin=True, embed_iframe=False,
        )
        runtime["panel_registered"] = True


@callback
def async_remove(hass):
    """Remove the visible panel when the last entry unloads."""
    runtime = hass.data[DOMAIN]
    if runtime.get("panel_registered"):
        frontend.async_remove_panel(hass, PANEL_PATH)
        runtime["panel_registered"] = False
