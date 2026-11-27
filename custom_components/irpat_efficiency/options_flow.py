"""Native Home Assistant options forms for initial topology editing."""
from __future__ import annotations

from copy import deepcopy
import asyncio
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.helpers.storage import Store

from .const import DOMAIN, OPERATING_MODES, CIRCUIT_CONTROLS
from .topology import SOURCE_TYPES, TopologyError, add_item, empty_topology
from .topology_edit import EDIT_FIELDS, OPTIONAL_FIELDS, edit_item
from .topology_remove import remove_item
from .telemetry import ROLE_GROUPS, set_binding
from .source_settings import FLUID_TYPES, set_source_settings
from .fuel_economics import (FUEL_KINDS, UNITS, BASES, STRATEGIES, configure_fuel,
                            configure_electric_scenario, configure_strategy)
from .operation_mode import MODES, configure_mode
from .ha_registry_reader import read_structure, read_entities
from .registry_import import import_floor, import_room, import_all, sensor_candidates, confirm_sensors


_LOGGER = logging.getLogger(__name__)


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
            self._base = deepcopy(self.config_entry.options.get("topology", empty_topology()))
            self._topology = deepcopy(self._base)
            self._draft_store = Store(self.hass, 1, f"{DOMAIN}.configuration_draft.{self.config_entry.entry_id}", private=True, atomic_writes=True)
            locks = self.hass.data.setdefault(DOMAIN, {}).setdefault("draft_locks", {})
            self._draft_lock = locks.setdefault(self.config_entry.entry_id, asyncio.Lock())
            async with self._draft_lock:
                try:
                    self._last_draft = await self._draft_store.async_load()
                except Exception:
                    _LOGGER.exception("Could not read configuration draft")
                    return self.async_abort(reason="draft_read_failed")
                draft = self._last_draft
                if isinstance(draft, dict) and draft.get("base") == self._base:
                    candidate = draft.get("topology")
                    if (isinstance(candidate, dict) and candidate.get("schema_version") == self._base.get("schema_version")
                            and all(isinstance(candidate.get(k), list) for k in EDIT_FIELDS)):
                        self._topology = deepcopy(candidate)
        if not await self._checkpoint():
            return self.async_abort(reason=self._draft_error)
        self._editing = None
        t = self._topology
        menu = ["floor", "zone", "outdoor"]
        native_floors, native_areas = read_structure(self.hass)
        if native_floors or native_areas:
            menu.append("import_structure")
        if t["floors"] or native_areas:
            menu.append("room")
        if any(r.get("ha_area_id") in native_areas for r in t["rooms"]):
            menu.append("discover_sensors")
        if t["zones"]:
            menu.append("source")
        if t["sources"]:
            menu.append("source_settings")
            menu.append("mode_source")
            menu.append("economic_source")
        if any(sum(z["id"] in src["zone_ids"] for src in t["sources"]) > 1 for z in t["zones"]):
            menu.append("hybrid_zone")
        if t["floors"] and t["zones"]:
            menu.append("manifold")
        if t["manifolds"]:
            menu.append("circuit")
        if t["rooms"]:
            menu.append("binding")
        for group in ROLE_GROUPS:
            if t[group]:
                menu.append(f"telemetry_{group}")
        if any(t[group] for group in EDIT_FIELDS):
            menu.append("edit")
            menu.append("remove")
        if self._topology != self._base:
            menu.append("discard_draft")
        menu.append("save")
        return self.async_show_menu(step_id="init", menu_options=menu,
                                    )

    async def _checkpoint(self):
        """Persist completed steps before showing the next page; no live options writes."""
        async with self._draft_lock:
            current = self.config_entry.options.get("topology", empty_topology())
            if current != self._base:
                self._draft_error = "draft_conflict"
                return False
            try:
                latest = await self._draft_store.async_load()
                if latest != self._last_draft:
                    self._draft_error = "draft_conflict"
                    return False
                desired = {"base": deepcopy(self._base), "topology": deepcopy(self._topology)}
                if desired != latest and (self._topology != self._base or isinstance(latest, dict) and latest.get("base") == self._base):
                    await self._draft_store.async_save(desired)
                    self._last_draft = desired
                return True
            except Exception:
                _LOGGER.exception("Could not checkpoint configuration draft")
                self._draft_error = "draft_write_failed"
                return False

    async def async_step_discard_draft(self, user_input=None):
        errors = {}
        if user_input is not None:
            if user_input.get("confirmed") is True:
                async with self._draft_lock:
                    try:
                        if (self.config_entry.options.get("topology", empty_topology()) != self._base
                                or await self._draft_store.async_load() != self._last_draft):
                            return self.async_abort(reason="draft_conflict")
                        # A durable base checkpoint avoids stale Store caches on older Core.
                        cleared = {"base": deepcopy(self._base), "topology": deepcopy(self._base)}
                        await self._draft_store.async_save(cleared)
                        self._last_draft = cleared
                    except Exception:
                        _LOGGER.exception("Could not discard configuration draft")
                        return self.async_abort(reason="draft_write_failed")
                    self._topology = deepcopy(self._base)
                return await self.async_step_init()
            errors["base"] = "registry_confirmation_required"
        return self.async_show_form(step_id="discard_draft", data_schema=vol.Schema({
            vol.Required("confirmed", default=False): selector.BooleanSelector(),
        }), errors=errors)

    def _reference(self, collection, multiple=False):
        return selector.SelectSelector(selector.SelectSelectorConfig(
            options=[{"value": item["id"], "label": item["name"]}
                     for item in self._topology[collection]],
            multiple=multiple, mode=selector.SelectSelectorMode.DROPDOWN,
        ))

    async def async_step_remove(self, user_input=None):
        collections = [key for key in EDIT_FIELDS if self._topology[key]]
        if user_input is not None and user_input.get("collection") in collections:
            self._remove_collection = user_input["collection"]
            return await self.async_step_remove_item()
        return self.async_show_form(step_id="remove", data_schema=vol.Schema({
            vol.Required("collection"): _choices(collections, "edit_collection"),
        }), errors={"base": "invalid_reference"} if user_input is not None else {})

    async def async_step_remove_item(self, user_input=None):
        collection = getattr(self, "_remove_collection", None)
        if collection not in EDIT_FIELDS or not self._topology[collection]:
            return await self.async_step_init()
        errors = {}
        if user_input is not None:
            try:
                self._topology = remove_item(self._topology, collection, user_input["item_id"],
                                             confirmed=user_input.get("confirmed", False))
                return await self.async_step_init()
            except TopologyError as exc:
                errors["base"] = str(exc)
        return self.async_show_form(step_id="remove_item", data_schema=vol.Schema({
            vol.Required("item_id"): self._reference(collection),
            vol.Required("confirmed", default=False): selector.BooleanSelector(),
        }), errors=errors)

    async def async_step_edit(self, user_input=None):
        """Choose which kind of existing item to edit."""
        collections = [key for key in EDIT_FIELDS if self._topology[key]]
        if user_input is not None and user_input.get("collection") in collections:
            self._edit_collection = user_input["collection"]
            return await self.async_step_edit_select()
        return self.async_show_form(step_id="edit", data_schema=vol.Schema({
            vol.Required("collection"): _choices(collections, "edit_collection"),
        }), errors={"base": "invalid_reference"} if user_input is not None else {})

    async def async_step_edit_select(self, user_input=None):
        collection = getattr(self, "_edit_collection", None)
        if collection not in EDIT_FIELDS or not self._topology[collection]:
            return await self.async_step_edit()
        if user_input is not None:
            identifier = user_input.get("item_id")
            if any(item["id"] == identifier for item in self._topology[collection]):
                self._editing = (collection, identifier)
                return await self.async_step_edit_item()
        return self.async_show_form(step_id="edit_select", data_schema=vol.Schema({
            vol.Required("item_id"): self._reference(collection),
        }), errors={"base": "invalid_reference"} if user_input is not None else {})

    async def async_step_edit_item(self, user_input=None):
        editing = getattr(self, "_editing", None)
        if not editing:
            return await self.async_step_init()
        steps = {"floors": self.async_step_floor, "zones": self.async_step_zone,
                 "sources": self.async_step_source, "rooms": self.async_step_room,
                 "manifolds": self.async_step_manifold, "circuits": self.async_step_circuit,
                 "bindings": self.async_step_binding}
        return await steps[editing[0]](user_input)

    async def _add(self, step, collection, fields, user_input):
        errors = {}
        editing = getattr(self, "_editing", None)
        original = None
        if editing:
            if editing[0] != collection:
                return await self.async_step_init()
            original = next((i for i in self._topology[collection] if i["id"] == editing[1]), None)
            if original is None:
                return await self.async_step_init()
            fields = {marker: value for marker, value in fields.items()
                      if marker.schema in EDIT_FIELDS[collection]}
            step = "edit_item"
        if user_input is not None:
            try:
                values = dict(user_input)
                name = values.pop("name")
                if collection == "circuits":
                    position = values["position"]
                    if isinstance(position, bool) or int(position) != position:
                        raise TopologyError("invalid_position")
                    values["position"] = int(position)
                if original is not None:
                    for key in EDIT_FIELDS[collection]:
                        if key in OPTIONAL_FIELDS and key not in values:
                            values[key] = None
                    self._topology = edit_item(self._topology, collection, original["id"], name, **values)
                else:
                    self._topology, _ = add_item(self._topology, collection, name, **values)
                return await self.async_step_init()
            except TopologyError as exc:
                errors["base"] = str(exc)
        schema = vol.Schema({vol.Required("name"): selector.TextSelector(), **fields})
        if original is not None:
            suggested = {key: original[key] for key in ("name", *EDIT_FIELDS[collection])
                         if original.get(key) is not None}
            if user_input is not None:
                suggested.update(user_input)
            schema = self.add_suggested_values_to_schema(schema, suggested)
        return self.async_show_form(step_id=step, data_schema=schema, errors=errors)

    def _native_selector(self, choices, multiple=False):
        return selector.SelectSelector(selector.SelectSelectorConfig(
            options=[{"value": k, "label": v} for k, v in choices.items()],
            multiple=multiple, mode=selector.SelectSelectorMode.DROPDOWN,
        ))

    async def async_step_floor(self, user_input=None):
        if self._editing:
            return await self.async_step_floor_custom(user_input)
        floors, _ = read_structure(self.hass)
        if not floors:
            return await self.async_step_floor_custom()
        return self.async_show_menu(step_id="floor", menu_options=["floor_existing", "floor_custom"])

    async def async_step_floor_custom(self, user_input=None):
        return await self._add("floor_custom", "floors", {}, user_input)

    async def async_step_floor_existing(self, user_input=None):
        floors, _ = read_structure(self.hass)
        if not floors:
            return await self.async_step_init()
        errors = {}
        if user_input is not None:
            try:
                self._topology, _ = import_floor(self._topology, floors, user_input["ha_floor_id"])
                return await self.async_step_init()
            except TopologyError as exc:
                errors["base"] = str(exc)
        return self.async_show_form(step_id="floor_existing", data_schema=vol.Schema({
            vol.Required("ha_floor_id"): self._native_selector(floors),
        }), errors=errors)

    async def async_step_import_structure(self, user_input=None):
        floors, areas = read_structure(self.hass)
        if not floors and not areas:
            return await self.async_step_init()
        errors = {}
        if user_input is not None:
            try:
                if user_input.get("confirmed") is not True:
                    raise TopologyError("registry_confirmation_required")
                self._topology = import_all(self._topology, floors, areas, user_input.get("fallback_floor"))
                return await self.async_step_init()
            except TopologyError as exc:
                errors["base"] = str(exc)
        fields = {vol.Required("confirmed", default=False): selector.BooleanSelector()}
        if self._topology["floors"]:
            fields[vol.Optional("fallback_floor")] = self._reference("floors")
        return self.async_show_form(step_id="import_structure", data_schema=vol.Schema(fields),
                                    description_placeholders={"floors": str(len(floors)), "rooms": str(len(areas)),
                                        "unassigned": str(sum(a.get("floor_id") not in floors for a in areas.values()))},
                                    errors=errors)

    async def async_step_discover_sensors(self, user_input=None):
        _, areas = read_structure(self.hass)
        rooms = {r["id"]: r["name"] for r in self._topology["rooms"] if r.get("ha_area_id") in areas}
        if not rooms:
            return await self.async_step_init()
        if user_input is not None and user_input.get("room_id") in rooms:
            self._sensor_room = user_input["room_id"]
            return await self.async_step_confirm_sensors()
        return self.async_show_form(step_id="discover_sensors", data_schema=vol.Schema({
            vol.Required("room_id"): self._native_selector(rooms),
        }), errors={"base": "invalid_reference"} if user_input is not None else {})

    async def async_step_confirm_sensors(self, user_input=None):
        room_id = self._sensor_room
        entities = read_entities(self.hass)
        candidates = sensor_candidates(self._topology, room_id, entities)
        errors = {}
        if user_input is not None:
            try:
                self._topology = confirm_sensors(self._topology, room_id, entities,
                                                user_input.get("temperatures", []), user_input.get("humidity"))
                return await self.async_step_init()
            except TopologyError as exc:
                errors["base"] = str(exc)
        fields = {}
        if candidates["temperature"]:
            fields[vol.Optional("temperatures")] = self._native_selector(
                {k: f"{v} ({k})" for k,v in candidates["temperature"].items()}, multiple=True)
        if candidates["humidity"]:
            fields[vol.Optional("humidity")] = self._native_selector(
                {k: f"{v} ({k})" for k,v in candidates["humidity"].items()})
        return self.async_show_form(step_id="confirm_sensors", data_schema=vol.Schema(fields),
                                    description_placeholders={"count": str(sum(map(len, candidates.values())))},
                                    errors=errors)

    async def async_step_zone(self, user_input=None):
        return await self._add("zone", "zones", {
            vol.Required("operating_mode", default=self.config_entry.data.get("operating_mode", "unknown")):
                _choices(OPERATING_MODES, "operating_mode"),
            vol.Required("circuit_control", default=self.config_entry.data.get("circuit_control", "unknown")):
                _choices(CIRCUIT_CONTROLS, "circuit_control"),
        }, user_input)

    async def async_step_room(self, user_input=None):
        if self._editing:
            return await self.async_step_room_custom(user_input)
        _, areas = read_structure(self.hass)
        if not areas:
            return await self.async_step_room_custom()
        menu = ["room_existing"]
        if self._topology["floors"]:
            menu += ["room_custom"]
        return self.async_show_menu(step_id="room", menu_options=menu)

    async def async_step_room_existing(self, user_input=None):
        floors, areas = read_structure(self.hass)
        if not areas:
            return await self.async_step_init()
        errors = {}
        if user_input is not None:
            try:
                updated, room_id = import_room(
                    self._topology, floors, areas, user_input["ha_area_id"], user_input.get("fallback_floor"))
                room = next(r for r in updated["rooms"] if r["id"] == room_id)
                changes = {k: user_input[k] for k in ("area_m2", "heating_target_c", "cooling_target_c")
                           if user_input.get(k) is not None}
                self._topology = edit_item(updated, "rooms", room_id, room["name"], **changes)
                self._sensor_room = room_id
                if not await self._checkpoint():
                    return self.async_abort(reason=self._draft_error)
                return await self.async_step_confirm_sensors()
            except TopologyError as exc:
                errors["base"] = str(exc)
        choices = {k: v["name"] + " (" + floors[v["floor_id"]] + ")" if v.get("floor_id") in floors else v["name"]
                   for k,v in areas.items()}
        fields = {
            vol.Required("ha_area_id"): self._native_selector(choices),
            vol.Optional("area_m2"): selector.NumberSelector(selector.NumberSelectorConfig(
                min=0.1, max=10000, step=0.01, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="m²")),
            vol.Optional("heating_target_c"): selector.NumberSelector(selector.NumberSelectorConfig(
                min=5, max=40, step=0.1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="°C")),
            vol.Optional("cooling_target_c"): selector.NumberSelector(selector.NumberSelectorConfig(
                min=5, max=40, step=0.1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="°C")),
        }
        if self._topology["floors"]:
            fields[vol.Optional("fallback_floor")] = self._reference("floors")
        return self.async_show_form(step_id="room_existing", data_schema=vol.Schema(fields), errors=errors)

    async def async_step_room_custom(self, user_input=None):
        return await self._add("room_custom", "rooms", {
            vol.Required("floor_id"): self._reference("floors"),
            vol.Optional("area_m2"): selector.NumberSelector(selector.NumberSelectorConfig(
                min=0.1, max=10000, step=0.01, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="m²")),
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

    async def async_step_economic_source(self, user_input=None):
        sources = {s["id"]: s["name"] for s in self._topology["sources"]
                   if s["source_type"] in ("heat_pump", "electric", "gas", "biomass", "district", "other")}
        if not sources:
            return await self.async_step_init()
        if user_input is not None and user_input.get("source_id") in sources:
            self._economic_source = user_input["source_id"]
            s = next(s for s in self._topology["sources"] if s["id"] == self._economic_source)
            if s["source_type"] in ("heat_pump", "electric"):
                return await self.async_step_electric_scenario()
            return await self.async_step_fuel_properties()
        return self.async_show_form(step_id="economic_source", data_schema=vol.Schema({
            vol.Required("source_id"): self._native_selector(sources),
        }), errors={"base": "invalid_reference"} if user_input is not None else {})

    async def async_step_electric_scenario(self, user_input=None):
        source = next(s for s in self._topology["sources"] if s["id"] == self._economic_source)
        errors = {}
        if user_input is not None:
            try:
                self._topology = configure_electric_scenario(self._topology, source["id"], user_input.get("cop"))
                return await self.async_step_init()
            except ValueError as exc:
                errors["base"] = str(exc)
        fields = {vol.Optional("cop"): selector.NumberSelector(selector.NumberSelectorConfig(
            min=0.1, max=20, step=0.01, mode=selector.NumberSelectorMode.BOX))}
        suggested = {"cop": source["scenario_cop"]} if source.get("scenario_cop") is not None else {}
        return self.async_show_form(step_id="electric_scenario",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(fields), suggested), errors=errors)

    async def async_step_fuel_properties(self, user_input=None):
        source = next(s for s in self._topology["sources"] if s["id"] == self._economic_source)
        fuel = source.get("fuel", {})
        errors = {}
        if user_input is not None:
            try:
                self._topology = configure_fuel(self._topology, source["id"], **user_input)
                return await self.async_step_init()
            except ValueError as exc:
                errors["base"] = str(exc)
        defaults = {"gas": "natural_gas", "biomass": "pellets", "district": "district_heat"}
        kind = fuel.get("kind", defaults.get(source["source_type"], "other"))
        fields = {
            vol.Required("kind", default=kind): _choices(FUEL_KINDS, "fuel_kind"),
            vol.Required("basis", default=fuel.get("basis", "delivered_heat" if kind == "district_heat" else "HHV")):
                _choices(BASES, "fuel_basis"),
            vol.Required("billing_unit", default=fuel.get("billing_unit", "kWh")): _choices(UNITS, "fuel_unit"),
            vol.Required("tariff"): selector.NumberSelector(selector.NumberSelectorConfig(
                min=0, max=1000000, step=0.001, mode=selector.NumberSelectorMode.BOX)),
            vol.Required("fuel_currency", default=fuel.get("currency", source.get("currency") or "RON")): selector.TextSelector(),
            vol.Optional("meter_entity"): selector.EntitySelector(selector.EntitySelectorConfig(filter=[{"domain": "sensor"}])),
            vol.Optional("meter_unit"): _choices(UNITS, "fuel_unit"),
        }
        for key, minimum, maximum, step, unit in (
            ("billing_kwh_per_unit", .001, 1e9, .001, "kWh/unit"),
            ("meter_kwh_per_unit", .001, 1e9, .001, "kWh/unit"),
            ("efficiency_percent", .1, 120, .1, "%"),
            ("auxiliary_kwh_per_heat_kwh", 0, 10, .001, "kWh/kWh"),
        ):
            fields[vol.Optional(key)] = selector.NumberSelector(selector.NumberSelectorConfig(
                min=minimum, max=maximum, step=step, mode=selector.NumberSelectorMode.BOX, unit_of_measurement=unit))
        suggested = {k: v for k,v in fuel.items() if v is not None}
        return self.async_show_form(step_id="fuel_properties",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(fields), suggested), errors=errors)

    async def async_step_hybrid_zone(self, user_input=None):
        zones = {z["id"]: z["name"] for z in self._topology["zones"]
                 if sum(z["id"] in s["zone_ids"] for s in self._topology["sources"]) > 1}
        if not zones:
            return await self.async_step_init()
        if user_input is not None and user_input.get("zone_id") in zones:
            self._hybrid_zone = user_input["zone_id"]
            return await self.async_step_hybrid_policy()
        return self.async_show_form(step_id="hybrid_zone", data_schema=vol.Schema({
            vol.Required("zone_id"): self._native_selector(zones),
        }), errors={"base": "invalid_reference"} if user_input is not None else {})

    async def async_step_hybrid_policy(self, user_input=None):
        zone = next(z for z in self._topology["zones"] if z["id"] == self._hybrid_zone)
        errors = {}
        if user_input is not None:
            try:
                self._topology = configure_strategy(self._topology, zone["id"], user_input["strategy"], user_input.get("threshold_c"))
                return await self.async_step_init()
            except ValueError as exc:
                errors["base"] = str(exc)
        fields = {
            vol.Required("strategy", default=zone.get("source_strategy", "unknown")): _choices(STRATEGIES, "source_strategy"),
            vol.Optional("threshold_c"): selector.NumberSelector(selector.NumberSelectorConfig(
                min=-60, max=50, step=.1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="°C")),
        }
        suggested = {"threshold_c": zone["declared_switch_c"]} if zone.get("declared_switch_c") is not None else {}
        return self.async_show_form(step_id="hybrid_policy",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(fields), suggested), errors=errors)

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
            config = dict(min=minimum, max=maximum, step=step, mode=selector.NumberSelectorMode.BOX)
            if unit is not None:
                config["unit_of_measurement"] = unit
            fields[vol.Optional(key)] = selector.NumberSelector(selector.NumberSelectorConfig(**config))
        fields[vol.Optional("currency")] = selector.TextSelector()
        suggested = {key: value for key, value in source.items() if value is not None}
        schema = self.add_suggested_values_to_schema(vol.Schema(fields), suggested)
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
        if not await self._checkpoint():
            return self.async_abort(reason=self._draft_error)
        # Keep the durable draft until Core commits the options; on the next
        # session a draft whose base differs from saved options is ignored.
        return self.async_create_entry(title="", data={
            **self.config_entry.options, "topology": self._topology,
        })
