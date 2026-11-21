"""System support: turns the advisor's measures into numbers and checks them.

The LLM describes each measure as «effects» on a scope:
    {scope: "res:dp-dev", cost_share: 0.8, energy_share: 0.8, relocate_to: "CH"}
meaning «this measure removes 80 % of the cost and energy of dp-dev and moves
the rest to Zurich». Code then:
  1. computes the savings (CHF, kWh, CO2, low/mid/high) from the recurring
     baseline of that scope: one-off events never count as savings;
  2. checks the shares (0..1, no double counting across measures);
  3. applies the safety gate: a measure touching a blocked resource is
     blocked, one touching a protection window or a human decision that it does
     not address goes to a human. The gate can only make a status stricter;
  4. checks the package against target (−40 % CO2, −25 % cost) and budget.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..energy.engine import load_factors
from ..export.frontend import SUMS, metrics
from ..harmonize.context import Context
from ..insights.regions import provider_key

PERSON_DAY_CHF = 1100
STRICTNESS = {"ok": 0, "human": 1, "blocked": 2}


class Calculator:
    def __init__(self, ctx: Context, facts: dict, constraints: list[dict]):
        self.ctx = ctx
        fc = ctx.tables["fact_cost"]
        self.base_all = fc[fc["in_baseline"]]
        self.rec = self.base_all[~self.base_all["is_one_off"].fillna(False)]
        self.tot = self.base_all[SUMS].sum()
        # Swiss factor of the run's scenario (consumption / production mix), as the energy engine uses it
        scenario = ctx.config.get("scenario", "ch_consumption")
        self.grid = {k: (v["variants"][scenario] if "variants" in v else v) for k, v in load_factors()["grid"].items()}
        srv = pd.DataFrame(facts["servers"]).set_index("id")
        self.srv_res = srv["resource"].to_dict()
        self.srv_share = {s: facts["facts"].get(f"{s}.share_of_resource", {}).get("value", 0) for s in srv.index}
        ai = self.ctx.tables["stg_ai_usage"][["source_row", "task_type", "model_class"]]
        self.gw = self.rec[self.rec["source_file"] == "ai_usage.csv"].merge(ai, on="source_row")
        self.lic_active = {l["id"]: facts["facts"].get(f"{l['id']}.active_share", {}).get("value", 1.0) for l in facts["licences"]}
        # windows that ended before the data date no longer restrict future measures
        asof = str(ctx.config["advisor"]["data_as_of"])
        self.constraints = [c for c in constraints
                            if not (c["type"] == "window" and c["schedule"].get("kind") == "date_range"
                                    and (c["schedule"].get("end_date") or "9999") < asof)]
        self.scopes = self._scopes(facts)
        # relocation rule (data_center_locations.csv): only to a location the scope's provider offers
        self.offered = {p: set(locs) for p, locs in facts.get("regions_offered", {}).items()}
        self.res_provider = {r["id"]: r.get("provider") for r in facts.get("resources", [])}

    # ------------------------------------------------------------ scopes
    def _scopes(self, facts: dict) -> list[str]:
        return (sorted(f"res:{r['id']}" for r in facts["resources"]) + sorted(s["id"] for s in facts["servers"])
                + sorted(l["id"] for l in facts["licences"]) + sorted(a["id"] for a in facts["ai_tasks"]))

    def resource_of(self, scope: str) -> str:
        kind, _, rest = scope.partition(":")
        if kind == "res":
            return rest
        if kind == "srv":
            return self.srv_res.get(scope)
        if kind == "ai":
            return rest.split(":")[0]
        return scope                      # lic:<tool> is its own budget line

    def base(self, scope: str) -> pd.Series:
        kind, _, rest = scope.partition(":")
        if kind == "res":
            return self.rec[self.rec["resource_id"] == rest][SUMS].sum()
        if kind == "srv":
            return self.rec[self.rec["resource_id"] == self.srv_res[scope]][SUMS].sum() * self.srv_share.get(scope, 0)
        if kind == "lic":
            return self.rec[self.rec["source_file"].isin(["ai_subscriptions.csv", "saas_contracts.csv"])
                            & (self.rec["tool"] == rest)][SUMS].sum()
        if kind == "ai":
            rid, task, mc = rest.split(":")
            return self.gw[(self.gw["resource_id"] == rid) & (self.gw["task_type"] == task)
                           & (self.gw["model_class"] == mc)][SUMS].sum()
        return pd.Series(0.0, index=SUMS)

    def location(self, scope: str) -> str | None:
        rid = self.resource_of(scope)
        rows = self.rec[self.rec["resource_id"] == rid]
        return rows["location"].mode().iat[0] if not rows.empty and rows["location"].notna().any() else None

    def share_of_resource(self, scope: str) -> float:
        """How much of its resource budget line a scope represents (for overlap checks)."""
        kind = scope.split(":")[0]
        if kind == "srv":
            return self.srv_share.get(scope, 0)
        if kind == "ai":
            res = self.rec[self.rec["resource_id"] == self.resource_of(scope)]["cost_chf"].sum()
            return self.base(scope)["cost_chf"] / res if res else 0
        return 1.0

    # ----------------------------------------------------------- savings
    def savings(self, effects: list[dict]) -> tuple[pd.Series, list[str], list[dict]]:
        tot = pd.Series(0.0, index=SUMS)
        problems, lines = [], []
        for e in effects:
            sc = e["scope"]
            if sc not in self.scopes:
                problems.append(f"unknown scope {sc}")
                continue
            cs, es = float(e["cost_share"]), float(e["energy_share"])
            if not (0 <= cs <= 1 and 0 <= es <= 1):
                problems.append(f"{sc}: shares must be between 0 and 1")
                continue
            b = self.base(sc)
            if sc.startswith("lic:"):
                # Energy of licences counts ACTIVE use only (energy engine): removing inactive seats
                # saves money but no energy. Energy falls only for the part beyond the inactive seats.
                act = self.lic_active.get(sc, 1.0)
                es = max(0.0, cs - (1 - act)) / act if act > 0 else 0.0
            s = pd.Series({c: b[c] * (cs if c.startswith("cost") else es) for c in SUMS})
            to = e.get("relocate_to")
            if to and self.offered:
                prov = provider_key(self.res_provider.get(self.resource_of(sc)))
                if prov in self.offered and to not in self.offered[prov]:
                    problems.append(f"{sc}: {self.res_provider.get(self.resource_of(sc))} offers no region in {to} "
                                    f"(only {sorted(self.offered[prov])}, data_center_locations.csv)")
                    continue
            frm = self.location(sc)
            if to and frm and to != frm and frm in self.grid and to in self.grid:
                for lvl, col in (("low", "co2_kg_low"), ("mid", "co2_kg_mid"), ("high", "co2_kg_high")):
                    remaining = b[col] * (1 - es)
                    s[col] += remaining * (1 - self.grid[to][lvl] / self.grid[frm][lvl])
            tot += s
            lines.append({"scope": sc, "cost_share": cs, "energy_share": es, "relocate_to": to,
                          "base_cost_chf": round(b["cost_chf"], 2), "base_kwh": round(b["kwh_mid"], 1),
                          "base_co2_kg": round(b["co2_kg_mid"], 1), "saved_cost_chf": round(s["cost_chf"], 2),
                          "saved_kwh": round(s["kwh_mid"], 1), "saved_co2_kg": round(s["co2_kg_mid"], 1),
                          "basis_fact_ids": e.get("basis_fact_ids", []), "reasoning": e.get("reasoning", "")})
        return tot, problems, lines

    # --------------------------------------------------------------- gate
    def touched(self, scope: str) -> list[dict]:
        """Constraints on the scope itself, on its resource, or on servers inside it."""
        rid = self.resource_of(scope)
        targets = {scope, rid, f"res:{rid}"} if rid else {scope}
        if scope.startswith("res:"):
            targets |= {s for s, r in self.srv_res.items() if r == rid}
        return [c for c in self.constraints if c["type"] in ("block", "window", "human_decision")
                and (targets & set(c["applies_to"]))]

    def gate(self, m: dict) -> tuple[str, list[str], list[str]]:
        status = m["proposed_status"] if m["proposed_status"] in STRICTNESS else "human"
        reasons, limit_ids = [], set()
        respected = set(m.get("respects_constraints", []))
        for e in m["effects"]:
            reduces = float(e["cost_share"]) > 0 or float(e["energy_share"]) > 0
            for c in self.touched(e["scope"]):
                limit_ids.add(c["id"])
                direct = e["scope"] in c["applies_to"] or self.resource_of(e["scope"]) in c["applies_to"]
                if c["type"] == "block" and reduces and direct:
                    new, why = "blocked", f"touches {c['applies_to']} which must not be reduced ({c['id']}: {c['summary']})"
                elif c["type"] == "block" and reduces and c["id"] not in respected:
                    new, why = "human", f"may affect protected {c['applies_to']} ({c['id']}) without addressing it"
                elif c["type"] == "human_decision":
                    new, why = "human", f"a person must decide first ({c['id']}: {c['summary']})"
                elif c["type"] == "window" and c["id"] not in respected:
                    new, why = "human", f"protection window not addressed ({c['id']}: {c['summary']})"
                else:
                    continue
                if STRICTNESS[new] > STRICTNESS[status]:
                    status = new
                reasons.append(why)
        return status, sorted(set(reasons)), sorted(limit_ids)

    # ------------------------------------------------------------ package
    def overlaps(self, measures: list[dict]) -> list[str]:
        use: dict[str, float] = {}
        for m in measures:
            for e in m["effects"]:
                if e["scope"] not in self.scopes:
                    continue
                k = self.resource_of(e["scope"])
                use[k] = use.get(k, 0) + float(e["cost_share"]) * self.share_of_resource(e["scope"])
        return [f"{k}: measures together remove {v:.0%} of its cost (more than 100 %)" for k, v in use.items() if v > 1.001]

    def evaluate(self, measures: list[dict], package: list[str]) -> dict:
        chosen = [m for m in measures if m["key"] in package and m["status"] != "blocked"]
        s = sum((m["_savings"] for m in chosen), pd.Series(0.0, index=SUMS))
        effort = sum(m["effort_days"] for m in chosen)
        cost_red = {lvl: s[c] / self.tot["cost_chf"] for lvl, c in (("low", "cost_chf_low"), ("mid", "cost_chf"), ("high", "cost_chf_high"))}
        co2_red = {lvl: s[f"co2_kg_{lvl}"] / self.tot[f"co2_kg_{lvl}"] for lvl in ("low", "mid", "high")}
        return {
            "measure_keys": [m["key"] for m in chosen], "effort_days": effort, "effort_chf": effort * PERSON_DAY_CHF,
            "savings": s, "reduction": {"cost": cost_red, "co2": co2_red},
            "meets": {"co2": bool(co2_red["mid"] >= 0.40), "cost": bool(cost_red["mid"] >= 0.25),
                      "budget": bool(effort * PERSON_DAY_CHF <= 16500)},
            # robustness: the least favourable factor set (whichever of low/high gives the smaller reduction)
            "meets_at_low": {"co2": bool(min(co2_red.values()) >= 0.40), "cost": bool(min(cost_red.values()) >= 0.25)},
            "blocked_in_package": [m["key"] for m in measures if m["key"] in package and m["status"] == "blocked"],
        }


def metrics_of(s: pd.Series) -> dict:
    return metrics(s)
