"""Pure calculation primitives. SI units unless documented otherwise."""
from __future__ import annotations

import math


def _finite(*values: float | None) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) for v in values)


def balancing_capability(mode: str, circuit_control: str) -> str:
    """Eligibility only; actual recommendations require further evidence."""
    if circuit_control not in ("manual", "open"):
        return "monitor_only"
    if mode == "weather":
        return "weather_compensation"
    if mode == "fixed":
        return "fixed_supply"
    return "monitor_only"


def normalize_flow(circuit_lmin: float | None, total_lmin: float | None,
                   reference_lmin: float | None) -> float | None:
    """Approximate relative flow at a comparable reference total.

    Callers must validate topology, simultaneous readings and operating state.
    """
    if not _finite(circuit_lmin, total_lmin, reference_lmin):
        return None
    if total_lmin <= 0 or reference_lmin <= 0 or not 0 <= circuit_lmin <= total_lmin:
        return None
    return circuit_lmin / total_lmin * reference_lmin


def thermal_power_w(flow_m3h: float | None, supply_c: float | None,
                    return_c: float | None, density_kg_m3: float | None,
                    cp_j_kgk: float | None) -> float | None:
    """Signed sensible heat transfer; fluid properties must be supplied."""
    if not _finite(flow_m3h, supply_c, return_c, density_kg_m3, cp_j_kgk):
        return None
    if flow_m3h < 0 or density_kg_m3 <= 0 or cp_j_kgk <= 0:
        return None
    return density_kg_m3 * cp_j_kgk * (flow_m3h / 3600) * (supply_c - return_c)


def period_cop(thermal_kwh: float | None, electric_kwh: float | None) -> float | None:
    """Ratio of synchronized energies for a heating boundary."""
    if not _finite(thermal_kwh, electric_kwh):
        return None
    if electric_kwh <= 0:
        return None
    return thermal_kwh / electric_kwh


def dew_point_c(temperature_c: float | None, humidity_pct: float | None) -> float | None:
    """Magnus approximation for typical indoor conditions; not a safety guarantee."""
    if not _finite(temperature_c, humidity_pct):
        return None
    if not 0 <= temperature_c <= 50 or not 0 < humidity_pct <= 100:
        return None
    alpha = math.log(humidity_pct / 100) + 17.62 * temperature_c / (243.12 + temperature_c)
    return 243.12 * alpha / (17.62 - alpha)
