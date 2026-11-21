"""Island deck centres and resource attachments in public, Y-up metres."""

from math import cos, radians, sin

from env.plan import asset_size

# Each origin is the top of the turf. The satellite shares the Zurich root.
ISLANDS = {
    "zurich": (-33, 3.2, -23),
    "frankfurt": (-32.5, 3.4, -43),
    "dublin": (-22.5, 3.0, -32.5),
    "eu-mixed": (-42.5, 4.0, -33),
}
RACK = "server_rack_42u"
ARRAY = "storage_array"
GPU = "gpu_server"
DECK_HEIGHT = 0.18
# Each terrace defines a single local frame for the hardware and its support.
# Within each row, centres are spaced using the exported kit footprints.
TERRACES = {
    "zurich": [
        (-2.62, -0.55, 8, ((("dp-prod", RACK, None), ("vm-app", RACK, 12)),)),
        (-0.05, -1.75, 14, ((("db-fin", RACK, None), ("pbi-kap", RACK, None)),)),
        (1.60, 0.45, 12, ((("dp-storage", ARRAY, None), ("st-archive", ARRAY, None)),)),
        (7.55, 0.1, 0, ((("web-cdn", RACK, None),), (("logs", ARRAY, None), ("st-proj", ARRAY, None)))),
    ],
    "frankfurt": [
        (0, 0.7, 14, ((("dp-dev", RACK, None), ("gpu-ml", GPU, None)),)),
    ],
    "dublin": [
        (-2, -0.50, 10, ((("vm-test", RACK, 12), ("sandboxes", RACK, 24)),)),
        (1.10, -0.55, 8, ((("dr-failover", RACK, None), ("cicd", RACK, None)),)),
        (-1, 1.38, 16, ((("orphans", RACK, 3),),)),
        (1.25, 1.25, 15, ((("st-backup", ARRAY, None),),)),
    ],
}


def equipment_terraces(island):
    clearance, rim = 0.37, 0.24
    for x, z, yaw, rows in TERRACES.get(island, ()):
        depths = [max(asset_size(asset)[1] for _, asset, _ in row) for row in rows]
        depth = sum(depths) + clearance * (len(rows) - 1)
        back = -depth / 2
        width = 0
        slots = []
        angle = radians(yaw)
        for row, row_depth in zip(rows, depths):
            row_width = sum(asset_size(asset)[0] for _, asset, _ in row) + clearance * (len(row) - 1)
            width = max(width, row_width)
            left, dz = -row_width / 2, back + row_depth / 2
            for resource, asset, count in row:
                w = asset_size(asset)[0]
                dx = left + w / 2
                sx = x + cos(angle) * dx + sin(angle) * dz
                sz = z - sin(angle) * dx + cos(angle) * dz
                slots.append((resource, asset, sx, sz, yaw, count))
                left += w + clearance
            back += row_depth + clearance
        yield x, z, width + 2 * rim, depth + 2 * rim, yaw, slots


SWISS_HOSTER = {"logs", "st-proj", "web-cdn"}
M1 = ("slot_dp-dev_m1", "zurich", -1.78, 1.13, 8)
EU_SERVICES = (
    "ai-assistant",
    "ai-marketing",
    "ai-quote",
    "ai-chatbot",
    "agent:support",
    "agent:research",
    "agent:sales",
    "agent:code",
    "agent:report",
    "ai-subscriptions",
    "saas",
)


def island_entries():
    rows = []
    for island in TERRACES:
        cx, cy, cz = ISLANDS[island]
        for resource, asset, x, z, angle, count in (
            slot for *_, slots in equipment_terraces(island) for slot in slots
        ):
            row = dict(
                id=f"island:{resource}",
                resourceId=resource,
                asset=asset,
                view="island",
                island=island,
                slot=f"slot_{resource}",
                pos=[round(cx + x, 6), round(cy + DECK_HEIGHT, 3), round(cz + z, 6)],
                rotY=radians(angle),
            )
            if resource in SWISS_HOSTER:
                row["pad"] = "swiss-hoster"
            if count:
                row["representedCount"] = count
            if resource == "dp-dev":
                row["alternateSlotM1"] = M1[0]
            rows.append(row)
    return rows
