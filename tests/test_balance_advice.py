"""Directional advice is conservative and weather-aware."""
from custom_components.irpat_efficiency.balance_advice import recommendations
from custom_components.irpat_efficiency.topology import add_item, empty_topology


def setup():
    t, f = add_item(empty_topology(), "floors", "Floor")
    t, z = add_item(t, "zones", "Heating", operating_mode="weather", circuit_control="manual")
    t, m = add_item(t, "manifolds", "Distributor", floor_id=f, zone_id=z)
    ids = []
    for i in range(2):
        t, r = add_item(t, "rooms", str(i), floor_id=f, heating_target_c=22)
        t, _ = add_item(t, "bindings", str(i), room_id=r, entity_id=f"sensor.temp_{i}")
        t, _ = add_item(t, "circuits", str(i), manifold_id=m, room_id=r, position=i+1)
        ids.append(r)
    t["outdoor_entity_id"] = "sensor.outdoor"
    return t, z, ids


def test_persistent_opposite_errors():
    t,z,(a,b)=setup()
    slots=[str(s) for s in range(0,172800,300)]
    data={a:dict.fromkeys(slots,23),b:dict.fromkeys(slots,21),"__outdoor__":dict.fromkeys(slots,5)}
    result=recommendations(t,data,172800,[],0)[z]
    assert result["status"]=="review_conditions"
    assert result["review_required"]
    assert result["rooms"][a]["direction"]=="decrease"
    assert result["rooms"][b]["direction"]=="increase"
    assert recommendations(t,data,172800,[],1)[z]["status"]=="collecting"
    data["__outdoor__"]={k: (5 if int(k)<86400 else 10) for k in slots}
    assert recommendations(t,data,172800,[],0)[z]["status"]=="weather_not_comparable"
    data["__outdoor__"]={}
    assert recommendations(t,data,172800,[],0)[z]["status"]=="insufficient_data"


def test_common_error_is_not_local_adjustment():
    t,z,(a,b)=setup()
    slots=[str(s) for s in range(0,172800,300)]
    data={a:dict.fromkeys(slots,23),b:dict.fromkeys(slots,23),"__outdoor__":dict.fromkeys(slots,5)}
    result=recommendations(t,data,172800,[],0)[z]
    assert result["common_direction"]=="review_supply"
    assert {r["direction"] for r in result["rooms"].values()}=={"observe"}
    t["zones"][0]["circuit_control"]="automatic"
    assert recommendations(t,data,172800,[],0)[z]["status"]=="configure_operation"
