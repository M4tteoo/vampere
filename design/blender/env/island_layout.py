"""Island deck centres and resource attachments in public, Y-up metres."""

import json
from math import cos, radians, sin
from pathlib import Path

from env.plan import ROOT, asset_size

# Each origin is the top of the turf. The satellite shares the Zurich root.
ISLANDS = {
    "zurich": (-33, 3.2, -23),
    "frankfurt": (-32.5, 3.4, -43),
    "dublin": (-22.5, 3.0, -32.5),
}
DECK_HEIGHT = 0.18
PROVIDER_COLOURS = {"azure": "5B8FC7", "aws": "E3A445", "hoster": "C9605A"}
INVOICE_PROVIDER = {"azure_costs.csv": "azure", "aws_costs.csv": "aws", "hoster_invoice.csv": "hoster"}
LOCATIONS = {"CH": "zurich", "DE": "frankfurt", "IE": "dublin"}
M1 = ("slot_dp-dev_m1", "zurich", -3.01, 1.08, 8)
# Surveyed attachment centres in island-local X/Z metres; yaw is degrees about Y.
SLOTS = {
    "zurich": (
        ("dp-prod", "hw_cluster", -4.05, -0.43, 8, None),
        ("vm-app", "hw_compute", -2.17, -1.00, 8, 12),
        ("db-fin", "hw_database", -0.66, -1.73, 14, None),
        ("pbi-kap", "hw_compute", 0.74, -2.23, 14, None),
        ("dp-storage", "hw_storage", 0.85, -0.03, 12, None),
        ("st-archive", "hw_storage", -1.21, 1.62, 0, None),
        ("web-cdn", "hw_compute", 8.85, -0.435, 0, None),
        ("logs", "hw_storage", 8.215, 0.785, 0, None),
        ("st-proj", "hw_storage", 9.485, 0.785, 0, None),
    ),
    "frankfurt": (
        ("dp-dev", "hw_cluster", -0.773068, 1.810066, 14, None),
        ("gpu-ml", "hw_gpu", 0.740593, 1.432668, 14, None),
    ),
    "dublin": (
        ("vm-test", "hw_compute", -1.816, -0.206, 40, 12),
        ("sandboxes", "hw_compute", -1.180, -0.740, 40, 24),
        ("dr-failover", "hw_compute", -0.491, -1.319, 40, None),
        ("cicd", "hw_compute", -0.014, 1.506, 40, None),
        ("orphans", "hw_compute", -0.642, 2.033, 40, 3),
        ("st-backup", "hw_storage", 1.174, 0.509, 40, None),
    ),
}


def island_entries():
    entities = {e["id"]: e for e in json.loads((ROOT / "output/entities.json").read_text())["entities"]}
    rows = []
    for island, slots in SLOTS.items():
        cx, cy, cz = ISLANDS[island]
        for resource, asset, x, z, yaw, count in slots:
            if resource in ("dr-failover", "orphans"):
                # These two inventory groups have no separate billed resource entity.
                provider = "aws"
            else:
                entity = entities["res:" + ("sandbox" if resource == "sandboxes" else resource)]
                if LOCATIONS[entity["location"]] != island:
                    raise ValueError(f"{resource}: entity location differs from its island")
                providers = {
                    INVOICE_PROVIDER[Path(f).name]
                    for f in entity["calc"]["source_files"]
                    if Path(f).name in INVOICE_PROVIDER
                }
                if len(providers) != 1:
                    raise ValueError(f"{resource}: ambiguous invoice provider {providers}")
                provider = providers.pop()
            row = dict(
                id=f"island:{resource}",
                resourceId=resource,
                asset=asset,
                view="island",
                island=island,
                slot=f"slot_{resource}",
                pos=[round(cx + x, 6), round(cy + DECK_HEIGHT, 3), round(cz + z, 6)],
                rotY=radians(yaw),
                provider=provider,
            )
            if count:
                row["representedCount"] = count
            if provider == "hoster":
                row["pad"] = "swiss-hoster"
            if resource == "dp-dev":
                row["alternateSlotM1"] = M1[0]
            rows.append(row)
    return rows


def footprint(asset, x, z, yaw):
    w, d, _ = asset_size(asset)
    return [
        (x + cos(yaw) * u + sin(yaw) * v, z - sin(yaw) * u + cos(yaw) * v)
        for u, v in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2))
    ]
