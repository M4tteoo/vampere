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
ROOMS = {
    "consulting": (0, 0, 20.5, 14.5, 10.36, "9DBFA8"),
    "sales": (20.5, 0, 33, 14.5, 28.9, "D98C6A"),
    "marketing": (33, 0, 42, 13.2, 37.48, "F2A7A0"),
    "it": (0, 17.5, 12.6, 28, 5.0, "7F9CC2"),
    "finance": (12.6, 17.5, 22.6, 28, 17.72, "D9B45A"),
    "management": (22.6, 17.5, 32, 28, 30.94, "4F7F86"),
    "hr": (32, 16.2, 40, 23.6, 36.82, "B9A7D9"),
    "reception": (32, 23.6, 42, 28, 41, None),
}
# The change of alignment occurs between the HR and Marketing party walls.
CORRIDOR_STRIPS = (
    (0, ROOMS["sales"][3], ROOMS["hr"][0], ROOMS["management"][1]),
    (ROOMS["hr"][0], ROOMS["sales"][3], ROOMS["marketing"][0], ROOMS["hr"][1]),
    (ROOMS["marketing"][0], ROOMS["marketing"][3], 42, ROOMS["hr"][1]),
)
GALLERY = (ROOMS["hr"][2], ROOMS["hr"][1], 42, ROOMS["hr"][3])
DEPTS = tuple(r for r in ROOMS if r != "reception")
DOOR_WIDTH = 1.54
DISPLAY_BAYS = {"consulting": (7.65, 11.1), "sales": (25.0, 28.4), "marketing": (34.1, 37.75)}
DIVIDERS = [
    ("hr", 36.75, 18.99, 39.9, 18.99),
    ("hr", 36.75, 20.45, 36.75, 23.50),
    ("management", 22.7, 22.59, 30.28, 22.59),
]
EXTRA_SIZES = {
    "meeting_chair": (0.48, 0.5, 0.82),
}
# Built-in shell and furnishings are present in the environment only.
DECOR = {
    "consulting": [
        ("project_wall", 0.164, 7.75, 90, 0.12),
        ("sofa_2", 5.325, 0.86, 0),
        ("rug_round", 5.325, 1.36, 0),
        ("coffee_table", 5.48, 1.79, 0),
        ("floor_lamp", 6.49, 0.65, 0),
        ("sofa_2", 15.395, 0.86, 0),
        ("rug_round", 15.395, 1.36, 0),
        ("coffee_table", 15.24, 1.79, 0),
        ("floor_lamp", 14.23, 0.65, 0),
        ("bookshelf_low", 0.30, 2.05, 90),
        ("plant_small", 0.30, 1.54, 90, 0.78),
        ("bookshelf_low", 8.72, 0.31, 0),
        ("plant_small", 9.24, 0.31, 0, 0.78),
        ("plant_large", 0.65, 13.66, 0),
        ("plant_large", 19.82, 0.71, 0),
        ("standing_table", 18.53, 13.70, 0),
        ("stool", 18.90, 13.04, 0),
    ],
    "sales": [
        ("phone_booth", 32.14, 7.95, -90),
        ("phone_booth", 32.14, 10.08, -90),
        ("sideboard", 26.68, 0.40, 0),
        ("plant_small", 26.10, 0.40, 0, 0.72),
        ("wall_art", 27.16, 0.132, 0, 0.35),
        ("bench", 31.02, 13.96, 180),
        ("rug_rect", 31.02, 13.60, 180),
        ("plant_large", 32.48, 0.68, 0),
    ],
    "marketing": [
        ("moodboard", 33.15, 10.97, 90, 0.29),
        ("creative_table", 36.60, 10.75, 0),
        ("rug_rect", 36.60, 10.75, 0),
        ("stool", 35.92, 9.90, 0),
        ("stool", 36.94, 11.60, 0),
        ("bookshelf_low", 34.72, 0.31, 0),
        ("plant_small", 34.18, 0.31, 0, 0.78),
        ("plant_large", 41.42, 12.54, 0),
    ],
    "it": [
        ("standing_table", 2.44, 27.06, 0),
        ("stool", 1.89, 26.40, 0),
        ("stool", 2.99, 26.40, 0),
        ("rug_rect", 2.44, 27.06, 0),
        ("bookshelf_low", 5.13, 27.66, 180),
        ("plant_small", 4.59, 27.66, 180, 0.78),
        ("plant_large", 11.95, 27.37, 0),
        ("wall_art", 0.135, 25.62, 90, 0.31),
        ("plant_large", 0.66, 18.18, 0),
    ],
    "finance": [
        ("cabinet_tall", 12.94, 26.40, 90),
        ("cabinet_tall", 12.94, 27.20, 90),
        ("cabinet_tall", 13.57, 27.55, 180),
        ("cabinet_tall", 14.37, 27.55, 180),
        ("creative_table", 19.81, 26.31, 0),
        ("floor_lamp", 21.58, 26.55, 0),
        ("plant_large", 13.23, 18.16, 0),
        ("plant_large", 17.08, 27.45, 0),
        ("wall_art", 12.735, 24.54, 90, 0.31),
    ],
    "management": [
        ("sideboard", 28.70, 27.66, 180),
        ("vase", 29.18, 27.66, 180, 0.72),
        ("wall_art", 22.735, 24.60, 90, 0.31),
        ("plant_large", 23.27, 23.21, 0),
        ("board_table_10", 28, 25.04, 0),
        ("armchair", 23.58, 19.03, 28),
        ("coffee_table", 24.18, 20.16, 90),
        ("armchair", 23.58, 21.29, 152),
    ],
    "hr": [
        ("armchair", 37.56, 19.96, 38),
        ("armchair", 39.32, 19.96, -38),
        ("sofa_2", 38.60, 22.96, 180),
        ("plant_large", 39.43, 22.02, 0),
        ("rug_rect", 38.44, 21.40, 0),
        ("coffee_table", 38.44, 21.10, 0),
        ("bookshelf_low", 38.94, 16.53, 0),
        ("plant_small", 39.43, 16.53, 0, 0.78),
    ],
    "reception": [
        ("reception_desk", 37.64, 24.54, 0),
        ("coffee_bar", 32.63, 25.83, 90),
        ("sofa_2", 41.34, 26.50, -90),
        ("plant_large", 41.39, 25.14, 0),
        ("creative_table", 35.27, 26.49, 0),
    ],
    "corridor": [
        ("bench", 5.90, 15.00, 0),
        ("plant_large", 4.59, 15.04, 0),
        ("bench", 26.54, 16.99, 180),
        ("plant_large", 27.88, 16.92, 0),
    ],
}
for x in (34.55, 35.99):
    DECOR["reception"].extend([("meeting_chair", x, 25.61, 0), ("meeting_chair", x, 27.39, 180)])
for x in (19.09, 20.53):
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
    return tuple(
        round(max(b[1][i] for b in bounds) - min(b[0][i] for b in bounds), 5) for i in (0, 2, 1)
    )


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
    for room, x0, z0, x1, z1 in DIVIDERS:
        yield room + " inner glass wall", (x0 - 0.06, 0, z0 - 0.06, x1 + 0.06, 1.2, z1 + 0.06)
    for room, (w, n, e, s, door, _) in ROOMS.items():
        z = s if n == 0 else n
        yield (
            room + " doorway",
            (door - DOOR_WIDTH / 2, 0, z - 1.02, door + DOOR_WIDTH / 2, 2.2, z + 1.02),
        )
    yield "entrance path", (38.20, 0, 26.3, 39.8, 2.2, 28)
