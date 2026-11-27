"""Native Home Assistant options forms for initial topology editing."""
from __future__ import annotations

from copy import deepcopy

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import OPERATING_MODES, CIRCUIT_CONTROLS
from .topology import SOURCE_TYPES, TopologyError, add_item, empty_topology
from .telemetry import ROLE_GROUPS, set_binding
from .source_settings import FLUID_TYPES, set_source_settings
from .operation_mode import MODES, configure_mode


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
        menu = ["floor", "zone", "outdoor"]
        if t["floors"]:
            menu.append("room")
        if t["zones"]:
            menu.append("source")
        if t["sources"]:
            menu.append("source_settings")
            menu.append("mode_source")
        if t["floors"] and t["zones"]:
            menu.append("manifold")
        if t["manifolds"]:
            menu.append("circuit")
        if t["rooms"]:
            menu.append("binding")
        for group in ROLE_GROUPS:
            if t[group]:
                menu.append(f"telemetry_{group}")
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

    async def async_step_outdoor(self, user_input=None):
        """Select or remove the optional outdoor temperature sensor."""
        errors = {}
        if user_input is not None:
            entity = user_input.get("entity_id")
            if entity and (not isinstance(entity, str) or not entity.startswith("sensor.")):
                errors["base"] = "invalid_entity"
            elif entity and any(b["entity_id"] == entity for b in self._topology["bindings"]):
                errors["base"] = "duplicate_entity"
            else:
                if entity:
                    self._topology["outdoor_entity_id"] = entity
                else:
                    self._topology.pop("outdoor_entity_id", None)
                return await self.async_step_init()
        return self.async_show_form(step_id="outdoor", data_schema=vol.Schema({
            vol.Optional("entity_id"): selector.EntitySelector(selector.EntitySelectorConfig(
                filter=[{"domain": "sensor", "device_class": "temperature"}])),
        }), errors=errors)

    async def _telemetry(self, group, user_input):
        errors = {}
        if user_input is not None:
            try:
                self._topology = set_binding(
                    self._topology, group, user_input["owner_id"],
                    user_input["role"], user_input.get("entity_id") or None,
                    user_input.get("name") or None,
                )
                return await self.async_step_init()
            except ValueError as exc:
                errors["base"] = str(exc)
        return self.async_show_form(step_id=f"telemetry_{group}", data_schema=vol.Schema({
            vol.Required("owner_id"): self._reference(group),
            vol.Required("role"): _choices(ROLE_GROUPS[group], "telemetry_role"),
            vol.Optional("name"): selector.TextSelector(),
            vol.Optional("entity_id"): selector.EntitySelector(selector.EntitySelectorConfig(
                filter=[{"domain": "sensor"}, {"domain": "binary_sensor"}])),
        }), errors=errors)

    async def async_step_telemetry_rooms(self, user_input=None):
        return await self._telemetry("rooms", user_input)

    async def async_step_telemetry_sources(self, user_input=None):
        return await self._telemetry("sources", user_input)

    async def async_step_telemetry_manifolds(self, user_input=None):
        return await self._telemetry("manifolds", user_input)

    async def async_step_source_settings(self, user_input=None):
        if user_input is not None:
            self._settings_source = user_input["source_id"]
            return await self.async_step_source_properties()
        return self.async_show_form(step_id="source_settings", data_schema=vol.Schema({
            vol.Required("source_id"): self._reference("sources"),
        }))

    async def async_step_source_properties(self, user_input=None):
        source = next((s for s in self._topology["sources"] if s["id"] == self._settings_source), None)
        if source is None:
            return await self.async_step_source_settings()
        errors = {}
        if user_input is not None:
            try:
                self._topology = set_source_settings(self._topology, source["id"], **user_input)
                return await self.async_step_init()
            except ValueError as exc:
                errors["base"] = str(exc)
        fields = {
            vol.Required("fluid_type", default=source.get("fluid_type", "unknown")):
                _choices(FLUID_TYPES, "fluid_type"),
            vol.Required("power_boundary_confirmed", default=source.get("power_boundary_confirmed", False)): selector.BooleanSelector(),
            vol.Required("energy_boundary_confirmed", default=source.get("energy_boundary_confirmed", False)): selector.BooleanSelector(),
        }
        for key, minimum, maximum, step, unit in (
            ("density_kg_m3", 1, 3000, 0.1, "kg/m³"),
            ("cp_j_kgk", 1, 10000, 1, "J/(kg·K)"),
            ("tariff", 0, 100000, 0.001, None),
        ):
            fields[vol.Optional(key)] = selector.NumberSelector(selector.NumberSelectorConfig(
                min=minimum, max=maximum, step=step, mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=unit))
        fields[vol.Optional("currency")] = selector.TextSelector()
        schema = self.add_suggested_values_to_schema(vol.Schema(fields), source)
        return self.async_show_form(step_id="source_properties", data_schema=schema, errors=errors)

    async def async_step_mode_source(self, user_input=None):
        if user_input is not None:
            self._mode_source = user_input["source_id"]
            return await self.async_step_mode_mapping()
        return self.async_show_form(step_id="mode_source", data_schema=vol.Schema({
            vol.Required("source_id"): self._reference("sources"),
        }))

    async def async_step_mode_mapping(self, user_input=None):
        source = next((s for s in self._topology["sources"] if s["id"] == self._mode_source), None)
        if source is None:
            return await self.async_step_mode_source()
        errors = {}
        if user_input is not None:
            try:
                values = dict(user_input)
                entity = values.pop("entity_id", None) or None
                self._topology = configure_mode(self._topology, source["id"], entity, **values)
                return await self.async_step_init()
            except ValueError as exc:
                errors["base"] = str(exc)
        binding = source.get("mode_binding", {})
        suggested = {mode: raw for raw, mode in binding.get("mapping", {}).items()}
        if binding.get("entity_id"):
            suggested["entity_id"] = binding["entity_id"]
        fields = {vol.Optional("entity_id"): selector.EntitySelector(
            selector.EntitySelectorConfig(filter=[{"domain": "sensor"}]))}
        for mode in MODES:
            fields[vol.Optional(mode)] = selector.TextSelector()
        schema = self.add_suggested_values_to_schema(vol.Schema(fields), suggested)
        return self.async_show_form(step_id="mode_mapping", data_schema=schema, errors=errors)

    async def async_step_save(self, user_input=None):
        return self.async_create_entry(title="", data={
            **self.config_entry.options, "topology": self._topology,
        })
