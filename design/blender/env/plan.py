"""Plan coordinates in metres from the NW corner. The public layout is centre-relative."""

import json
import struct
from pathlib import Path
from math import cos, sin, pi
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[3]
MODELS = ROOT / "web/public/models"
PREVIEWS = ROOT / "design/blender/previews"
CASE = ROOT / "data/case"
# West, north, east, south, centre of corridor door, accent.
CORRIDOR = (0, 12, 42, 15)
GALLERY = (40, 15, 42, 22.5)
ROOMS = {
    "consulting": (0, 0, 20, 12, 10.0, "9DBFA8"),
    "sales": (20, 0, 32, 12, 29.65, "D98C6A"),
    "marketing": (32, 0, 42, 12, 37.70, "F2A7A0"),
    "it": (0, 15, 15, 28, 7.74, "7F9CC2"),
    "finance": (15, 15, 24, 28, 19.35, "D9B45A"),
    "management": (24, 15, 32, 28, 28.55, "4F7F86"),
    "hr": (32, 15, 40, 22.5, 36.90, "B9A7D9"),
    "reception": (32, 22.5, 42, 28, 41, None),
}
DEPTS = tuple(r for r in ROOMS if r != "reception")
COLUMNS = [(x, z) for x in range(7, 42, 7) for z in (7, 14, 21)]
DOOR_WIDTH = 1.54
# Opaque bays interrupt the north glazing at the project, sales and creative areas.
EAST_DISPLAY_BAY = (7.55, 11.15)
DISPLAY_BAYS = {"consulting": (7.65, 11.1), "sales": (23.0, 26.65), "marketing": (34.1, 37.75)}
# Partition centre lines in plan coordinates (axis aligned, openings at the ends).
DIVIDERS = [
    ("hr", 37.12, 17.72, 39.9, 17.72),
    ("hr", 37.12, 19.02, 37.12, 22.4),
    ("management", 24.1, 22.24, 30.28, 22.24),
]
EXTRA_SIZES = {
    "meeting_chair": (0.48, 0.5, 0.82),
    "agent_shelf": (1.8, 0.55, 0.79),
    "standing_table": (1.42, 0.72, 1.05),
}
# Built-in shell and furnishings are present in the environment only.
DECOR = {
    "consulting": [
        ("project_wall", 0.24, 3.25, 90, 0.04),
        ("sofa_2", 2.15, 0.80, 0),
        ("sofa_2", 16.90, 0.80, 0),
        ("agent_shelf", 5.72, 0.65, 0),
        ("standing_table", 17.10, 10.87, 0),
        ("plant_large", 7.90, 10.94, 0),
        ("plant_large", 12.85, 10.94, 0),
    ],
    "sales": [
        ("phone_booth", 20.91, 10.99, 180),
        ("phone_booth", 22.43, 10.99, 180),
        ("project_wall", 31.76, 8.88, -90, 0.04),
    ],
    "marketing": [
        ("creative_table", 39.85, 8.93, 90),
        ("pinboard", 40.47, 11.64, 180),
        ("plant_large", 41.24, 7.02, 0),
    ],
    "it": [("whiteboard", 12.63, 27.70, 180)],
    "finance": [("cabinet_tall", x, 27.55, 180) for x in (15.87, 16.73, 17.59, 18.45)]
    + [("creative_table", 21.21, 26.31, 0)],
    "management": [
        ("board_table_10", 28, 25.04, 0),
        ("armchair", 24.98, 21.26, 90),
        ("armchair", 27.00, 21.26, -90),
    ],
    "hr": [
        ("armchair", 37.88, 19.71, 90),
        ("armchair", 39.21, 20.05, -90),
        ("sofa_2", 38.59, 21.88, 180),
        ("plant_small", 39.63, 18.22, 0),
    ],
    "reception": [
        ("reception_desk", 37.84, 23.99, 0),
        ("coffee_bar", 32.64, 24.1, 90),
        ("sofa_2", 40.72, 25.48, -90),
        ("plant_large", 41.11, 24.05, 0),
        ("creative_table", 34.52, 26.63, 0),
    ],
    "corridor": [
        ("bench", 4.40, 12.49, 0),
        ("plant_large", 3.09, 12.58, 0),
        ("bench", 24.62, 14.49, 180),
        ("plant_large", 25.97, 14.44, 0),
    ],
}
for x in (33.82, 35.22):
    DECOR["reception"].extend([("meeting_chair", x, 25.77, 0), ("meeting_chair", x, 27.49, 180)])
for x in (20.49, 21.93):
    DECOR["finance"].extend([("meeting_chair", x, 25.39, 0), ("meeting_chair", x, 27.23, 180)])
for x in (26.53, 27.50, 28.47, 29.44):
    DECOR["management"].extend([("meeting_chair", x, 24.0, 0), ("meeting_chair", x, 26.08, 180)])
DECOR["management"].extend([("meeting_chair", 25.64, 25.04, 90), ("meeting_chair", 30.36, 25.04, -90)])


def frontage(room):
    w, n, e, s, door, _ = ROOMS[room]
    if room == "reception":
        w = GALLERY[0]
    return w, e, s if n == 0 else n, door


def return_width(room):
    w, _, _, door = frontage(room)
    return max(0, min(4.4 if room == "marketing" else 3.1, door - DOOR_WIDTH / 2 - w - 0.75))


def gltf(path):
    with path.open("rb") as f:
        f.seek(12)
        length, kind = struct.unpack("<II", f.read(8))
        if kind != 0x4E4F534A:
            raise ValueError(path)
        return json.loads(f.read(length))


@lru_cache(None)
def asset_size(name):
    if name in EXTRA_SIZES:
        return EXTRA_SIZES[name]
    g = gltf(MODELS / f"kit_{name}_v1.glb")
    bounds = []
    for node in g["nodes"]:
        if "mesh" not in node:
            continue
        t = node.get("translation", [0, 0, 0])
        for p in g["meshes"][node["mesh"]]["primitives"]:
            a = g["accessors"][p["attributes"]["POSITION"]]
            bounds.append(
                ([a["min"][i] + t[i] for i in range(3)], [a["max"][i] + t[i] for i in range(3)])
            )
    return tuple(round(max(b[1][i] for b in bounds) - min(b[0][i] for b in bounds), 5) for i in (0, 2, 1))


def placed(asset, x, z, angle=0, y=0):
    return dict(
        asset=asset,
        pos=[round(x - 21, 5), round(y, 5), round(z - 14, 5)],
        rotY=round(angle * pi / 180, 8),
    )


def offset(parent, asset, x, y, z, yaw=0):
    """Resolve a local attachment into the same world coordinates as its parent."""
    a = parent["rotY"]
    px, py, pz = parent["pos"]
    return dict(
        asset=asset,
        pos=[
            round(px + x * cos(a) + z * sin(a), 5),
            round(py + y, 5),
            round(pz - x * sin(a) + z * cos(a), 5),
        ],
        rotY=round(a + yaw, 8),
    )


def decor_items():
    for room, rows in DECOR.items():
        for i, (asset, x, z, angle, *height) in enumerate(rows):
            yield dict(placed(asset, x, z, angle, *height), room=room, id=f"decor:{room}:{i:02d}")


def local_children(seat):
    for c in seat.get("children", []):
        x, y, z = c["pos"]
        yield offset(seat, c["asset"], x, y, z, c["rotY"])


def bounds(item):
    w, d, h = asset_size(item["asset"])
    a = item["rotY"]
    rx = (abs(cos(a)) * w + abs(sin(a)) * d) / 2
    rz = (abs(sin(a)) * w + abs(cos(a)) * d) / 2
    x, y, z = item["pos"]
    return (x + 21 - rx, y, z + 14 - rz, x + 21 + rx, y + h, z + 14 + rz)


def intersects(a, b):
    return all(a[i] < b[i + 3] - 0.0001 and b[i] < a[i + 3] - 0.0001 for i in range(3))


def structural_bounds():
    for x, z in COLUMNS:
        yield "column", (x - 0.17, 0, z - 0.17, x + 0.17, 1.2, z + 0.17)
    for room, x0, z0, x1, z1 in DIVIDERS:
        yield room + " inner glass wall", (x0 - 0.06, 0, z0 - 0.06, x1 + 0.06, 1.2, z1 + 0.06)
    for room, (w, n, e, s, door, _) in ROOMS.items():
        z = s if n == 0 else n
        yield (
            room + " doorway",
            (door - DOOR_WIDTH / 2, 0, z - 1.02, door + DOOR_WIDTH / 2, 2.2, z + 1.02),
        )
    yield "entrance path", (38.20, 0, 26.3, 39.8, 2.2, 28)
