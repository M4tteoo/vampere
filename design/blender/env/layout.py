"""Generate and validate the August 2026 office registry. Also runs with ordinary Python."""

import csv
import json
import math
import sys
from collections import defaultdict, deque
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from env.island_layout import island_entries
from env.plan import (
    CASE,
    CORRIDOR_STRIPS,
    frontage,
    MODELS,
    ROOMS,
    DOOR_WIDTH,
    placed,
    offset,
    decor_items,
    local_children,
    bounds,
    intersects,
    structural_bounds,
)

CENTRES = dict(
    zip(
        ("4000", "4100", "4300", "4500", "4400", "4200", "4900"),
        ("consulting", "sales", "marketing", "it", "hr", "finance", "management"),
    )
)


def source(file):
    with (CASE / file).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def august(file):
    return [r for r in source(file) if r["month"] == "2026-08-01" and r["contract_status"] == "Final"]


def desk_pod(spine, positions, left, right):
    """Two facing runs on a common bench spine, with chairs on its outer sides."""
    return [
        (spine + side * 0.40, z, side * 90)
        for side, count in ((-1, left), (1, right))
        for z in positions[:count]
    ]


def crosswise_pod(z, xs, second):
    return [
        (x, z + side * 0.40, 0 if side == 1 else 180)
        for side, positions in ((-1, xs), (1, xs[:second]))
        for x in positions
    ]


def desk_rows(room):
    if room == "consulting":
        for i, spine in enumerate((2.89, 7.76, 12.96, 17.83)):
            yield desk_pod(spine, (3.26, 4.80, 6.34, 9.48, 11.02, 12.56), 6 if i < 3 else 5, 5)
    elif room == "sales":
        # Two window-side teams and a crosswise six-seat quoting team near the booths.
        for spine, count in ((23.69, 4), (29.65, 3)):
            yield desk_pod(spine, (2.35, 3.91, 5.47, 7.03), 4, count)
        yield [
            (x, 10.83 + side * 0.4, 0 if side == 1 else 180)
            for side in (-1, 1)
            for x in (23.15, 24.77, 26.39)
        ]
    elif room == "marketing":
        for z, xs, second in (
            (3.14, (34.45, 36.0), 2),
            (3.14, (38.65, 40.20), 1),
            (7.03, (34.65, 36.20), 1),
            (7.25, (38.80, 40.35), 1),
        ):
            yield crosswise_pod(z, xs, second)
    elif room == "it":
        for z, xs, second in (
            (20.05, (2.50, 4.06), 2),
            (20.05, (7.45, 9.01, 10.57), 2),
            (24.42, (2.57, 4.13), 2),
            (24.42, (8.15, 9.71), 2),
        ):
            yield crosswise_pod(z, xs, second)
    elif room == "finance":
        for spine, count in ((15.18, 4), (20.10, 3)):
            yield desk_pod(spine, (19.20, 20.80, 22.40, 24.00), count, 3)
    elif room == "management":
        for side in (-1, 1):
            yield [(x, 20.02 + side * 0.4, 0 if side == 1 else 180) for x in (26.48, 28.12, 29.76)]
    elif room == "hr":
        for side in (-1, 1):
            yield [(34.35 + side * 0.4, z, side * 90) for z in (18.10, 19.62, 21.14)]


class Layout:
    def __init__(self):
        self.entries = []
        self.ids = set()
        self.occupied = list(structural_bounds())
        self.seats = defaultdict(list)
        # Rugs may run under seating. They do not obstruct circulation, but
        # must clear boundaries, fixed partitions, doors and other rugs.
        self.rugs = []
        for item in decor_items():
            if item["asset"].startswith("rug_"):
                self.reserve(item, item["id"], self.rugs)
            else:
                self.reserve(item, item["id"])

    def reserve(self, item, label, rugs=None, box=None):
        box = bounds(item) if box is None else box
        if item["room"] == "corridor":
            strips = [r for r in CORRIDOR_STRIPS if box[0] < r[2] and box[3] > r[0]]
            if not strips:
                raise ValueError(f"{label} is outside the corridor")
            w, e = CORRIDOR_STRIPS[0][0], CORRIDOR_STRIPS[-1][2]
            n, s = max(r[1] for r in strips), min(r[3] for r in strips)
        else:
            w, n, e, s = ROOMS[item["room"]][:4]
        obstacles = self.occupied if rugs is None else [*structural_bounds(), *rugs]
        conflicts = [name for name, other in obstacles if intersects(box, other)]
        if (
            conflicts
            or box[0] < w + 0.099
            or box[2] < n + 0.099
            or box[3] > e - 0.099
            or box[5] > s - 0.099
        ):
            raise ValueError(f"{label} in {item['room']}: {conflicts} {box}")
        (self.occupied if rugs is None else rugs).append((label, box))

    def add_seat(self, entry):
        id, room = entry["id"], entry["room"]
        if id in self.ids:
            raise ValueError(f"Duplicate seat {id}")
        # The underside is open. Reserve the tabletop, runners and keyboard
        # separately so a tower can share the desk footprint without crossing a leg.
        x0, _, z0, x1, _, z1 = bounds(entry)
        self.reserve(entry, id, box=(x0, 0.604, z0, x1, 0.74, z1))
        for x, z, width, depth, bottom, top in (
            (-0.56, 0, 0.08, 0.59, 0, 0.604),
            (0.56, 0, 0.08, 0.59, 0, 0.604),
            (0, 0.16, 0.43, 0.145, 0.74, 0.759),
        ):
            cx, _, cz = offset(entry, "", x, 0, z)["pos"]
            if abs(math.sin(entry["rotY"])) > 0.5:
                width, depth = depth, width
            cx, cz = cx + 21, cz + 14
            self.reserve(
                entry,
                id + "/frame",
                box=(cx - width / 2, bottom, cz - depth / 2, cx + width / 2, top, cz + depth / 2),
            )
        for child in local_children(entry):
            self.reserve(dict(child, room=room), id + "/" + child["asset"])
        self.ids.add(id)
        self.entries.append(entry)


def build_layout():
    layout = Layout()
    contracts = august("saas_contracts.csv")
    for row in contracts:
        if row["contract"] != "Microsoft 365":
            continue
        room = CENTRES[row["cost_center"]]
        seats = layout.seats[room]
        for bank, positions in enumerate(desk_rows(room), 1):
            for x, z, turn in positions:
                seq = len(seats) + 1
                children = [
                    dict(asset="chair_task", pos=[0, 0, 0.71], rotY=math.pi),
                    dict(
                        asset="monitor_dual" if room == "it" else "monitor_27",
                        pos=[0, 0.74, -0.216],
                        rotY=0,
                    ),
                    dict(asset="pc_tower", pos=[0.40, 0, -0.13], rotY=0),
                ]
                seat = dict(
                    id=f"seat:{room}:{seq:02}",
                    room=room,
                    **placed("desk_bench", x, z, turn),
                    children=children,
                    row=bank,
                    active=seq <= int(row["licences_active_30d"]),
                )
                layout.add_seat(seat)
                seats.append(seat)
        assert len(seats) == int(row["licences_purchased"])
    assert len(layout.entries) == 119 and all(id.startswith("seat:") for id in layout.ids)
    check_walkways(layout)
    return layout


def check_walkways(layout):
    """Flood walkable floor for a 80 cm wide pedestrian from the real entrance."""
    step, radius = 0.12, 0.40
    nx, nz = int(42 / step) + 1, int(28 / step) + 1
    blocked = set()

    def obstruct(x0, z0, x1, z1):
        for i in range(
            max(0, math.ceil((x0 - radius) / step)), min(nx, math.floor((x1 + radius) / step) + 1)
        ):
            for j in range(
                max(0, math.ceil((z0 - radius) / step)), min(nz, math.floor((z1 + radius) / step) + 1)
            ):
                blocked.add((i, j))

    for label, (x0, y0, z0, x1, y1, z1) in layout.occupied:
        if "doorway" in label or label == "entrance path" or y0 >= 1.85:
            continue
        obstruct(x0, z0, x1, z1)
    for room, (w, n, e, s, door, _) in ROOMS.items():
        _, _, z, door = frontage(room)
        obstruct(w, z - 0.10, door - DOOR_WIDTH / 2, z + 0.10)
        obstruct(door + DOOR_WIDTH / 2, z - 0.10, e, z + 0.10)
        obstruct(w - 0.1, n, w + 0.1, s)
        obstruct(e - 0.1, n, e + 0.1, s)
    obstruct(0, 0, 42, 0.10)
    obstruct(0, 27.90, 38.13, 28)
    obstruct(39.87, 27.90, 42, 28)
    obstruct(0, 0, 0.10, 28)
    obstruct(41.90, 0, 42, 28)
    start = (round(39 / step), round(27.5 / step))
    reachable = {start}
    queue = deque([start])
    while queue:
        i, j = queue.popleft()
        for pt in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1)):
            if 0 <= pt[0] < nx and 0 <= pt[1] < nz and pt not in blocked and pt not in reachable:
                reachable.add(pt)
                queue.append(pt)

    def near(x, z, distance):
        i, j = round(x / step), round(z / step)
        r = math.ceil(distance / step)
        return any(
            (i + di, j + dj) in reachable and math.hypot(di, dj) * step <= distance
            for di in range(-r, r + 1)
            for dj in range(-r, r + 1)
        )

    for room, (w, n, e, s, door, _) in ROOMS.items():
        if not near(door, (s - 1 if n == 0 else n + 1), 0.32):
            raise ValueError(f"Unreachable doorway: {room}")
    for room, seats in layout.seats.items():
        for seat in seats:
            chair = next(local_children(seat))
            x, _, z = chair["pos"]
            if not near(x + 21, z + 14, 1.06):
                raise ValueError(f"No aisle access to {seat['id']}")


def write_layout(layout):
    path = MODELS / "layout.json"
    path.write_text(
        "[\n"
        + ",\n".join(
            "  " + json.dumps(row, separators=(",", ": "))
            for row in [*layout.entries, *island_entries()]
        )
        + "\n]\n"
    )


if __name__ == "__main__":
    write_layout(build_layout())
