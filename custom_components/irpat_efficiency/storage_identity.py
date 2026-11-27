"""Storage identity for isolated beta configuration resets.

Legacy entries keep their existing keys. Reset creates a new namespace; old
files are deliberately retained, never loaded into the new test session.
"""
from uuid import uuid4
from .const import DOMAIN

GENERATION_KEY = "beta_storage_generation"
STORE_KINDS = ("reports", "journal", "profiles", "history", "defrost", "energy", "fuel", "modes", "configuration_draft")


def generation(entry):
    value = getattr(entry, "options", {}).get(GENERATION_KEY)
    if value is not None and (not isinstance(value, str) or len(value) != 32
                              or any(c not in "0123456789abcdef" for c in value)):
        raise ValueError("invalid_storage_generation")
    return value


def storage_key(entry, kind):
    if kind not in STORE_KINDS:
        raise ValueError("invalid_store_kind")
    key = f"{DOMAIN}.{kind}.{entry.entry_id}"
    current = generation(entry)
    return f"{key}.{current}" if current is not None else key


def fresh_options():
    from .topology import empty_topology
    return {"topology": empty_topology(), GENERATION_KEY: uuid4().hex}
