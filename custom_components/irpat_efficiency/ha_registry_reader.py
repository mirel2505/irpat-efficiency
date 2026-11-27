"""Read native Home Assistant registries, without writing to them."""
from homeassistant.helpers import area_registry as ar, floor_registry as fr
from homeassistant.helpers import entity_registry as er, device_registry as dr


def read_structure(hass):
    floors = {f.floor_id: f.name for f in fr.async_get(hass).async_list_floors()}
    areas = {a.id: {"name": a.name, "floor_id": a.floor_id}
             for a in ar.async_get(hass).async_list_areas()}
    return floors, areas


def read_entities(hass):
    devices = dr.async_get(hass)
    result = []
    for entry in er.async_get(hass).entities.values():
        device = devices.async_get(entry.device_id) if entry.device_id else None
        state = hass.states.get(entry.entity_id)
        result.append({"entity_id": entry.entity_id,
                       "name": entry.name or entry.original_name or entry.entity_id,
                       "area_id": entry.area_id or (device.area_id if device else None),
                       "device_class": entry.device_class or entry.original_device_class
                           or (state.attributes.get("device_class") if state else None),
                       "disabled": entry.disabled_by is not None})
    return result
