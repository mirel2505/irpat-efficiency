"""Explicit billing and energy conversions, never assumed fuel properties."""
from copy import deepcopy
from math import isfinite

FUEL_KINDS = ("natural_gas", "lpg", "pellets", "wood", "district_heat", "other")
UNITS = ("kWh", "MWh", "Gcal", "m3", "L", "kg", "t", "cylinder", "bag")
BASES = ("HHV", "LHV", "delivered_heat")
STRATEGIES = ("unknown", "alternate", "parallel", "cascade", "manual")
FIXED = {"kWh": 1.0, "MWh": 1000.0}
UNIT_ALIASES = {"m³": "m3", "m3": "m3", "l": "L", "L": "L", "kWh": "kWh", "MWh": "MWh",
                "Gcal": "Gcal", "kg": "kg", "t": "t", "cylinder": "cylinder", "bag": "bag"}


def finite(v, lo=0, hi=1e12):
    return type(v) in (int, float) and isfinite(v) and lo <= v <= hi


def factor(unit, value=None):
    if unit not in UNITS:
        raise ValueError("invalid_fuel_unit")
    if unit in FIXED:
        if value is not None and value != FIXED[unit]:
            raise ValueError("invalid_fuel_factor")
        return FIXED[unit]
    if not finite(value, 1e-6, 1e9):
        raise ValueError("invalid_fuel_factor")
    return float(value)


def currency(value):
    if not isinstance(value, str) or len(value.strip()) != 3 or not value.strip().isascii() or not value.strip().isalpha():
        raise ValueError("invalid_tariff")
    return value.strip().upper()


def configure_fuel(topology, source_id, *, kind, basis, billing_unit, tariff, fuel_currency,
                   billing_kwh_per_unit=None, meter_entity=None, meter_unit=None, meter_kwh_per_unit=None,
                   efficiency_percent=None, auxiliary_kwh_per_heat_kwh=None):
    data = deepcopy(topology)
    source = next((s for s in data["sources"] if s["id"] == source_id), None)
    if source is None or source["source_type"] not in ("gas", "biomass", "district", "other"):
        raise ValueError("invalid_source")
    if kind not in FUEL_KINDS or basis not in BASES or (kind == "district_heat") != (basis == "delivered_heat"):
        raise ValueError("invalid_fuel_basis")
    if not finite(tariff, 0, 1e6):
        raise ValueError("invalid_tariff")
    billing_factor = factor(billing_unit, billing_kwh_per_unit)
    if meter_entity:
        if not isinstance(meter_entity, str) or not meter_entity.startswith("sensor.") or len(meter_entity) <= 7:
            raise ValueError("invalid_entity")
        if meter_unit == billing_unit and meter_kwh_per_unit is None:
            meter_kwh_per_unit = billing_factor
        meter_factor = factor(meter_unit, meter_kwh_per_unit)
        if meter_unit == billing_unit and meter_factor != billing_factor:
            raise ValueError("invalid_fuel_factor")
    else:
        meter_entity = meter_unit = meter_factor = None
    if efficiency_percent is not None and not finite(efficiency_percent, 0.1, 120 if basis == "LHV" else 100):
        raise ValueError("invalid_fuel_efficiency")
    if auxiliary_kwh_per_heat_kwh is not None and not finite(auxiliary_kwh_per_heat_kwh, 0, 10):
        raise ValueError("invalid_number")
    source["fuel"] = dict(kind=kind, basis=basis, billing_unit=billing_unit, tariff=tariff,
                          currency=currency(fuel_currency), billing_kwh_per_unit=billing_factor,
                          meter_entity=meter_entity, meter_unit=meter_unit, meter_kwh_per_unit=meter_factor,
                          efficiency_percent=efficiency_percent, auxiliary_kwh_per_heat_kwh=auxiliary_kwh_per_heat_kwh)
    return data


def configure_electric_scenario(topology, source_id, cop):
    data = deepcopy(topology)
    s = next((s for s in data["sources"] if s["id"] == source_id), None)
    if s is None or s["source_type"] not in ("heat_pump", "electric"):
        raise ValueError("invalid_source")
    if cop is not None and not finite(cop, 0.1, 20):
        raise ValueError("invalid_number")
    s["scenario_cop"] = cop
    return data


def configure_strategy(topology, zone_id, strategy, threshold_c=None):
    data = deepcopy(topology)
    z = next((z for z in data["zones"] if z["id"] == zone_id), None)
    if z is None or strategy not in STRATEGIES:
        raise ValueError("invalid_mode")
    if threshold_c is not None and not finite(threshold_c, -60, 50):
        raise ValueError("invalid_number")
    z["source_strategy"] = strategy
    z["declared_switch_c"] = threshold_c
    return data


def fuel_cost(kwh, config):
    if not finite(kwh) or not finite(config.get("tariff")) or not finite(config.get("billing_kwh_per_unit"), 1e-6):
        return None
    quantity = kwh / config["billing_kwh_per_unit"]
    return {"quantity": quantity, "unit": config["billing_unit"], "amount": quantity * config["tariff"],
            "currency": config["currency"], "basis": "current_tariff_estimate"}


def modeled_cost(source):
    """Cost per useful kWh: explicit scenario, not actual system COP/efficiency."""
    tariff, cur = source.get("tariff"), source.get("currency")
    if source["source_type"] in ("heat_pump", "electric"):
        cop = source.get("scenario_cop")
        if finite(tariff) and cur and finite(cop, .1, 20):
            return {"amount": tariff/cop, "currency": cur, "complete": True, "cop": cop}
    f = source.get("fuel", {})
    eta = f.get("efficiency_percent")
    if not finite(eta, .1, 120):
        return None
    cost = fuel_cost(100/eta, f)
    if cost is None:
        return None
    aux = f.get("auxiliary_kwh_per_heat_kwh")
    complete = aux == 0 or (finite(aux) and finite(tariff) and cur == f["currency"])
    return {"amount": cost["amount"] + (aux*tariff if complete and aux else 0),
            "currency": f["currency"], "complete": complete, "efficiency_percent": eta}


def economic_overview(topology):
    sources = topology["sources"]
    costs = {s["id"]: modeled_cost(s) for s in sources}
    comparisons = []
    for hp in sources:
        if hp["source_type"] != "heat_pump" or not finite(hp.get("tariff")):
            continue
        for fuel in sources:
            shared = sorted(set(hp["zone_ids"]) & set(fuel["zone_ids"]))
            cost = costs[fuel["id"]]
            if (not shared or not fuel.get("fuel") or not cost or not cost["complete"]
                    or hp.get("currency") != cost["currency"] or cost["amount"] <= 0):
                continue
            comparisons.append({"heat_pump_id": hp["id"], "fuel_source_id": fuel["id"], "zone_ids": shared,
                                "break_even_cop": hp["tariff"]/cost["amount"],
                                "currency": cost["currency"], "advisory_only": True})
    return {"modeled": costs, "comparisons": comparisons}
