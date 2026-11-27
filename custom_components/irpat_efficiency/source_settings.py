"""Explicit source properties and measurement declarations; no inferred mode."""
from copy import deepcopy
from math import isfinite

FLUID_TYPES = ('unknown', 'water', 'propylene_glycol', 'ethylene_glycol', 'other')


def _number(value, minimum, maximum):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and isfinite(value) and minimum <= value <= maximum)


def set_source_settings(topology, source_id, *, fluid_type='unknown', density_kg_m3=None,
                        cp_j_kgk=None, tariff=None, currency=None,
                        power_boundary_confirmed=False, energy_boundary_confirmed=False):
    """Replace optional declarations. Fluid properties must be supplied as a pair."""
    data = deepcopy(topology)
    source = next((s for s in data.get('sources', []) if s['id'] == source_id), None)
    if source is None:
        raise ValueError('invalid_reference')
    if fluid_type not in FLUID_TYPES:
        raise ValueError('invalid_fluid')
    if (density_kg_m3 is None) != (cp_j_kgk is None):
        raise ValueError('invalid_fluid_properties')
    if density_kg_m3 is not None and (fluid_type == 'unknown'
            or not _number(density_kg_m3, 1, 3000) or not _number(cp_j_kgk, 1, 10000)):
        raise ValueError('invalid_fluid_properties')
    if tariff is None:
        currency = None
    elif (not _number(tariff, 0, 100000) or not isinstance(currency, str)
          or len(currency.strip()) != 3 or not currency.strip().isascii() or not currency.strip().isalpha()):
        raise ValueError('invalid_tariff')
    if type(power_boundary_confirmed) is not bool or type(energy_boundary_confirmed) is not bool:
        raise ValueError('invalid_boundary')
    source.update(fluid_type=fluid_type, density_kg_m3=density_kg_m3, cp_j_kgk=cp_j_kgk,
                  tariff=tariff, currency=currency.strip().upper() if currency else None,
                  power_boundary_confirmed=power_boundary_confirmed,
                  energy_boundary_confirmed=energy_boundary_confirmed)
    return data


def estimate_cost(electric_kwh, source):
    """Scenario cost at current configured tariff, not historical billing."""
    tariff, currency = source.get('tariff'), source.get('currency')
    if (not _number(tariff, 0, 100000) or not isinstance(currency, str)
            or not isinstance(electric_kwh, (int, float)) or isinstance(electric_kwh, bool)
            or not isfinite(electric_kwh) or electric_kwh < 0):
        return None
    return {'amount': electric_kwh * tariff, 'currency': currency,
            'tariff_per_kwh': tariff, 'basis': 'current_tariff_estimate'}
