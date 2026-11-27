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
from .report_inputs import prepare_capture
from .profile_review import review_profile
from .data_export import CSV_SECTIONS, capture as capture_export, serialize as serialize_export

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
        reports = hass.data[DOMAIN]["report_stores"].get(entry.entry_id)
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
                         "building_reports": reports.overview() if reports else {},
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


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/report_capture",
    vol.Required("entry_id"): str,
    vol.Required("name"): vol.All(str, vol.Length(min=1, max=120)),
    vol.Required("start"): int,
    vol.Required("end"): int,
    vol.Required("boundary_id"): vol.All(str, vol.Length(min=1, max=120)),
    vol.Required("thermal_kwh"): vol.Any(int, float),
    vol.Optional("electric_kwh"): vol.Any(int, float),
    vol.Required("reviewed"): bool,
    vol.Optional("note", default=""): vol.All(str, vol.Length(max=2000)),
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_report_capture(hass, connection, msg):
    """Capture retained temperatures and explicitly reviewed manual net heat."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    runtime = hass.data.get(DOMAIN, {})
    reports = runtime.get("report_stores", {}).get(msg["entry_id"])
    history = runtime.get("histories", {}).get(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN or reports is None or history is None:
        connection.send_error(msg["id"], "not_found", "No active report history")
        return
    topology = entry.options.get("topology", empty_topology())
    try:
        if history.save_failed or history.configuration_hash != history.fingerprint(topology):
            raise ValueError("configuration_changed")
        inputs = prepare_capture(topology, history.data, msg["start"], msg["end"],
                                 now=dt_util.utcnow().timestamp(),
                                 configuration_since=history.configuration_since)
        result = await reports.async_capture(
            msg["name"], inputs["indoor"], inputs["outdoor"], msg["start"], msg["end"],
            measurement_signature=inputs["measurement_signature"], room_ids=inputs["room_ids"],
            boundary_id=msg["boundary_id"], thermal_kwh=msg["thermal_kwh"],
            electric_kwh=msg.get("electric_kwh"), reviewed=msg["reviewed"], note=msg["note"])
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_observation", str(exc))
        return
    except Exception:
        _LOGGER.exception("Could not save building observation")
        connection.send_error(msg["id"], "save_failed", "Report save failed")
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/report_compare",
    vol.Required("entry_id"): str,
    vol.Required("name"): vol.All(str, vol.Length(min=1, max=120)),
    vol.Required("before_id"): str,
    vol.Required("after_id"): str,
    vol.Required("intervention_at"): vol.Any(int, float),
    vol.Required("comparable"): bool,
    vol.Optional("note", default=""): vol.All(str, vol.Length(max=2000)),
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_report_compare(hass, connection, msg):
    """Compare saved server-side observations; never accept client-computed values."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    reports = hass.data.get(DOMAIN, {}).get("report_stores", {}).get(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN or reports is None:
        connection.send_error(msg["id"], "not_found", "No active report store")
        return
    try:
        result = await reports.async_compare(
            msg["before_id"], msg["after_id"], name=msg["name"],
            intervention_at=msg["intervention_at"], comparable=msg["comparable"], note=msg["note"])
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_comparison", str(exc))
        return
    except Exception:
        _LOGGER.exception("Could not save building comparison")
        connection.send_error(msg["id"], "save_failed", "Report save failed")
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/export_data",
    vol.Required("entry_id"): str,
    vol.Required("format"): vol.In(("json", "csv")),
    vol.Optional("section"): vol.In(CSV_SECTIONS),
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_export_data(hass, connection, msg):
    """Return a read-only export on explicit request, for administrators only."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    runtime = hass.data.get(DOMAIN, {})
    if (entry is None or entry.domain != DOMAIN
            or entry.entry_id not in runtime.get("active_entries", set())):
        connection.send_error(msg["id"], "not_found", "No active installation")
        return
    try:
        snapshot = capture_export(entry.entry_id, entry.title,
                                  entry.options.get("topology", empty_topology()),
                                  runtime, dt_util.utcnow().timestamp())
        result = await hass.async_add_executor_job(
            serialize_export, snapshot, msg["format"], msg.get("section"))
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_export", str(exc))
        return
    except Exception:
        _LOGGER.exception("Could not prepare irPaT export")
        connection.send_error(msg["id"], "export_failed", "Export preparation failed")
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/profile_review",
    vol.Required("entry_id"): str,
    vol.Required("profile_id"): str,
    vol.Required("snapshot_id"): str,
})
@websocket_api.require_admin
@callback
def ws_profile_review(hass, connection, msg):
    """Compare stored references with observations; never adjust equipment."""
    runtime = hass.data.get(DOMAIN, {})
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if (entry is None or entry.domain != DOMAIN
            or entry.entry_id not in runtime.get("active_entries", set())):
        connection.send_error(msg["id"], "not_found", "No active installation")
        return
    profiles = runtime.get("profiles", {}).get(entry.entry_id)
    journal = runtime.get("journals", {}).get(entry.entry_id)
    if profiles is None or journal is None:
        connection.send_error(msg["id"], "not_found", "No active profile or journal")
        return
    profile = next((p for p in profiles.profiles if p["id"] == msg["profile_id"]), None)
    snapshot = next((s for s in journal.entries if s["id"] == msg["snapshot_id"]), None)
    if profile is None or snapshot is None:
        connection.send_error(msg["id"], "not_found", "No stored reference or observation")
        return
    try:
        result = review_profile(entry.options.get("topology", empty_topology()), profile, snapshot)
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_comparison", str(exc))
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
        websocket_api.async_register_command(hass, ws_profile_review)
        websocket_api.async_register_command(hass, ws_report_capture)
        websocket_api.async_register_command(hass, ws_report_compare)
        websocket_api.async_register_command(hass, ws_export_data)
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
