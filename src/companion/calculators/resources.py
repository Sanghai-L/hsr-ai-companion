"""Check all costs before committing any part of a local action."""
from companion.contracts import CompanionError, ErrorCode


def transact(actor, shared, action):
    sp_cost, sp_gain = action["sp_cost"], action["sp_gain"]
    energy_cost = action.get("energy_cost", 0)
    deficits = {}
    if shared["sp"] < sp_cost:
        deficits["sp"] = sp_cost - shared["sp"]
    if actor["energy"] + 1e-10 < energy_cost:
        deficits["energy"] = energy_cost - actor["energy"]
    if deficits:
        return {"executed": False, "deficits": deficits, "sp": shared["sp"], "energy": actor["energy"]}
    energy_gain = action["energy_gain"] * (1 + actor["energy_regen"] if action["regen_applies"] else 1)
    sp = min(shared["sp_cap"], shared["sp"] - sp_cost + sp_gain)
    energy = min(actor["energy_cap"], actor["energy"] - energy_cost + energy_gain)
    overflow = {"sp": max(0, shared["sp"] - sp_cost + sp_gain - shared["sp_cap"]),
                "energy": max(0, actor["energy"] - energy_cost + energy_gain - actor["energy_cap"])}
    shared["sp"], actor["energy"] = sp, energy
    return {"executed": True, "deficits": {}, "sp": sp, "energy": energy, "overflow": overflow}
