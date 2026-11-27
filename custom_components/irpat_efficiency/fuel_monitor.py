"""Separate fuel ledger using the proven cumulative-meter interval engine."""
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .energy_store import EnergyStore
from .fuel_economics import UNIT_ALIASES, finite, fuel_cost


class FuelMonitor:
    def __init__(self, hass, entry):
        self.hass = hass
        self.history = EnergyStore(Store(hass, 1, f"{DOMAIN}.fuel.{entry.entry_id}", atomic_writes=True))

    def samples(self, topology, now):
        """A selected counter must be cumulative and have the declared unit."""
        electric = {b["entity_id"] for b in topology.get("telemetry", [])
                    if b["group"] == "sources" and b["role"] == "electrical_energy"}
        result = {}
        for source in topology["sources"]:
            f = source.get("fuel", {})
            eid = f.get("meter_entity")
            if not eid:
                continue
            state = self.hass.states.get(eid)
            status, value, stamp = "unavailable", None, None
            if state is not None:
                attributes = state.attributes
                unit = UNIT_ALIASES.get(attributes.get("unit_of_measurement"))
                reported = getattr(state, "last_reported", None) or state.last_updated
                stamp = reported.timestamp()
                try:
                    raw = float(state.state)
                except (TypeError, ValueError, OverflowError):
                    raw = None
                if (unit == f.get("meter_unit") and attributes.get("state_class") in ("total", "total_increasing")
                        and finite(raw) and finite(f.get("meter_kwh_per_unit"), 1e-6)
                        and 0 <= now-stamp <= 60):
                    value = raw*f["meter_kwh_per_unit"]
                    status = "reported" if finite(value) else "unavailable"
            result[source["id"]] = {"entity_id": eid, "status": status, "value": value, "timestamp": stamp,
                "blocked": eid in electric, "signature_extra": [f["kind"], f["basis"], f["meter_unit"], f["meter_kwh_per_unit"]]}
        return result

    def overview(self, topology, now, tz):
        samples = self.samples(topology, now)
        try:
            result = self.history.overview(samples, now, tz)
        except ValueError:
            return {}
        for source in topology["sources"]:
            f = source.get("fuel", {})
            for row in result.get(source["id"], {}).values():
                # EnergyStore's generic counter internals retain legacy names;
                # only this separate fuel ledger uses them for input energy.
                row["fuel_kwh"] = row.pop("electric_kwh")
                row.pop("modes", None)
                row.pop("estimated_cost", None)
                row["energy_basis"] = f.get("basis")
                row["current_tariff_cost"] = fuel_cost(row["fuel_kwh"], f)
        return result

    def export(self):
        """Translate the counter ledger into explicitly fuel-labeled records."""
        rows = []
        for sid, segments in self.history.data.items():
            for i, seg in enumerate(segments):
                for day, row in sorted(seg["ledger"].get("days", {}).items()):
                    rows.append({"source_id": sid, "meter_segment": i, "meter_signature": seg["signature"],
                                 "local_date": day, "fuel_kwh": row["electric_kwh"] if row["electric_seconds"] else None,
                                 "observed_seconds": row["electric_seconds"]})
        return rows
