"""Register the local, administrator-only overview panel."""
from pathlib import Path

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import callback
import voluptuous as vol

from .const import DOMAIN
from .topology import empty_topology
from .temperature_reader import read_rooms

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
        overview.append({"name": entry.title, "topology": topology,
                         "room_temperatures": read_rooms(hass, topology),
                         "history": history.overview(topology) if history else {},
                         "history_save_failed": history.save_failed if history else False})
    connection.send_result(msg["id"], overview)


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
