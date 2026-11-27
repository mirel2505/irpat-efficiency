"""Native Home Assistant options forms for initial topology editing."""
from __future__ import annotations

from copy import deepcopy

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import OPERATING_MODES, CIRCUIT_CONTROLS
from .topology import SOURCE_TYPES, TopologyError, add_item, empty_topology


def _choices(values, translation_key):
    return selector.SelectSelector(selector.SelectSelectorConfig(
        options=list(values), translation_key=translation_key,
        mode=selector.SelectSelectorMode.DROPDOWN,
    ))


class IrpatOptionsFlow(config_entries.OptionsFlow):
    """Add named topology items using native selectors; save explicitly."""

    async def async_step_init(self, user_input=None):
        """Open the configuration menu."""
        if not hasattr(self, "_topology"):
            self._topology = deepcopy(self.config_entry.options.get("topology", empty_topology()))
        t = self._topology
        menu = ["floor", "zone"]
        if t["floors"]:
            menu.append("room")
        if t["zones"]:
            menu.append("source")
        if t["floors"] and t["zones"]:
            menu.append("manifold")
        if t["manifolds"]:
            menu.append("circuit")
        if t["rooms"]:
            menu.append("binding")
        menu.append("save")
        return self.async_show_menu(step_id="init", menu_options=menu)

    def _reference(self, collection, multiple=False):
        return selector.SelectSelector(selector.SelectSelectorConfig(
            options=[{"value": item["id"], "label": item["name"]}
                     for item in self._topology[collection]],
            multiple=multiple, mode=selector.SelectSelectorMode.DROPDOWN,
        ))

    async def _add(self, step, collection, fields, user_input):
        errors = {}
        if user_input is not None:
            try:
                values = dict(user_input)
                name = values.pop("name")
                if collection == "circuits":
                    position = values["position"]
                    if isinstance(position, bool) or int(position) != position:
                        raise TopologyError("invalid_position")
                    values["position"] = int(position)
                self._topology, _ = add_item(self._topology, collection, name, **values)
                return await self.async_step_init()
            except TopologyError as exc:
                errors["base"] = str(exc)
        schema = vol.Schema({vol.Required("name"): selector.TextSelector(), **fields})
        return self.async_show_form(step_id=step, data_schema=schema, errors=errors)

    async def async_step_floor(self, user_input=None):
        return await self._add("floor", "floors", {}, user_input)

    async def async_step_zone(self, user_input=None):
        return await self._add("zone", "zones", {
            vol.Required("operating_mode", default=self.config_entry.data.get("operating_mode", "unknown")):
                _choices(OPERATING_MODES, "operating_mode"),
            vol.Required("circuit_control", default=self.config_entry.data.get("circuit_control", "unknown")):
                _choices(CIRCUIT_CONTROLS, "circuit_control"),
        }, user_input)

    async def async_step_room(self, user_input=None):
        return await self._add("room", "rooms", {
            vol.Required("floor_id"): self._reference("floors"),
            vol.Optional("area_m2"): selector.NumberSelector(selector.NumberSelectorConfig(
                min=0.1, max=10000, step=0.1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="m²")),
            vol.Optional("heating_target_c"): selector.NumberSelector(selector.NumberSelectorConfig(
                min=5, max=40, step=0.1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="°C")),
            vol.Optional("cooling_target_c"): selector.NumberSelector(selector.NumberSelectorConfig(
                min=5, max=40, step=0.1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="°C")),
        }, user_input)

    async def async_step_source(self, user_input=None):
        return await self._add("source", "sources", {
            vol.Required("source_type", default="unintegrated"): _choices(SOURCE_TYPES, "source_type"),
            vol.Optional("zone_ids"): self._reference("zones", multiple=True),
        }, user_input)

    async def async_step_manifold(self, user_input=None):
        return await self._add("manifold", "manifolds", {
            vol.Required("floor_id"): self._reference("floors"),
            vol.Required("zone_id"): self._reference("zones"),
        }, user_input)

    async def async_step_circuit(self, user_input=None):
        fields = {
            vol.Required("manifold_id"): self._reference("manifolds"),
            vol.Required("position"): selector.NumberSelector(selector.NumberSelectorConfig(
                min=1, step=1, mode=selector.NumberSelectorMode.BOX)),
            vol.Optional("length_m"): selector.NumberSelector(selector.NumberSelectorConfig(
                min=0.1, step=0.1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="m")),
        }
        if self._topology["rooms"]:
            fields[vol.Optional("room_id")] = self._reference("rooms")
        return await self._add("circuit", "circuits", fields, user_input)

    async def async_step_binding(self, user_input=None):
        return await self._add("binding", "bindings", {
            vol.Required("room_id"): self._reference("rooms"),
            vol.Required("entity_id"): selector.EntitySelector(selector.EntitySelectorConfig(
                filter=[{"domain": "sensor", "device_class": "temperature"}, {"domain": "climate"}])),
        }, user_input)

    async def async_step_save(self, user_input=None):
        return self.async_create_entry(title="", data={
            **self.config_entry.options, "topology": self._topology,
        })
