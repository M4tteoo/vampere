"""Resolve structured advisor scopes to recurring billing rows and their allocated share."""
from __future__ import annotations

import pandas as pd


class ScopeRows:
    def __init__(self, base: pd.DataFrame, advisor_facts: dict | None, ai_usage: pd.DataFrame | None):
        self.base = base
        self.recurring = ~base["is_one_off"].eq(True)
        details = advisor_facts or {}
        self.servers = {s["id"]: s["resource"] for s in details.get("servers", [])}
        self.server_facts = details.get("facts", {})
        self.ai_usage = None if ai_usage is None else ai_usage.set_index("source_row")

    def resolve(self, scope: str) -> tuple[pd.Series, float]:
        kind, _, key = scope.partition(":")
        base = self.base
        share = 1.0
        if kind == "res":
            rows = base["resource_id"].eq(key)
        elif kind == "srv":
            allocation = self.server_facts.get(f"{scope}.share_of_resource")
            if scope not in self.servers or allocation is None:
                raise ValueError(f"No server allocation for {scope}")
            share = float(allocation["value"])
            if not 0 <= share <= 1:
                raise ValueError(f"Invalid server allocation for {scope}")
            rows = base["resource_id"].eq(self.servers[scope])
        elif kind == "lic":
            rows = base["source_file"].isin(["ai_subscriptions.csv", "saas_contracts.csv"]) & base["tool"].eq(key)
        elif kind == "ai":
            resource, sep, selection = key.partition(":")
            task, model_sep, model = selection.rpartition(":")
            if not (resource and sep and task and model_sep and model) or self.ai_usage is None:
                raise ValueError(f"No AI allocation for {scope}")
            candidates = base["source_file"].eq("ai_usage.csv") & base["resource_id"].eq(resource)
            source_rows = base.loc[candidates, "source_row"]
            rows = pd.Series(False, index=base.index)
            rows.loc[candidates] = (
                source_rows.map(self.ai_usage["task_type"]).eq(task)
                & source_rows.map(self.ai_usage["model_class"]).eq(model)
            )
        else:
            raise ValueError(f"Unsupported scope: {scope}")
        return (self.recurring & rows).fillna(False), share
