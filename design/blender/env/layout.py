"""Generate and validate the August 2026 office registry. Also runs with ordinary Python."""

import csv
import json
import math
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from env.island_layout import island_entries
from env.plan import (
    CASE,
    CORRIDOR,
    DISPLAY_BAYS,
    EAST_DISPLAY_BAY,
    frontage,
    MODELS,
    ROOMS,
    DEPTS,
    DOOR_WIDTH,
    asset_size,
    placed,
    offset,
    decor_items,
    local_children,
    bounds,
    intersects,
    structural_bounds,
    return_width,
)

CENTRES = dict(
    zip(
        ("4000", "4100", "4300", "4500", "4400", "4200", "4900"),
        ("consulting", "sales", "marketing", "it", "hr", "finance", "management"),
    )
)
PRODUCTS = {"Microsoft Copilot": "copilot", "Claude Team": "claude", "ChatGPT Team": "chatgpt"}
# Physical infrastructure IDs in §6. Support is a billing resource in §1.
INFRA = {
    "consulting": {"console_kiosk": ["dp-prod", "gpu-ml"], "storage_cabinet": ["st-proj", "dp-storage"]},
    "sales": {"storage_cabinet": ["st-archive"]},
    "finance": {"console_kiosk": ["db-fin"]},
    "marketing": {"wall_screen": ["web-cdn"]},
    "it": {
        "rack_compact": [
            "vm-app",
            "vm-test",
            "sandboxes",
            "dp-dev",
            "dr-failover",
            "st-backup",
            "cicd",
            "orphans",
        ],
        "wall_screen_large": ["pbi-kap", "logs"],
        "console_kiosk": ["net-egress"],
    },
}
WINDOWS = {
    "consulting": ["nightly-processing", "quarterly-training"],
    "finance": ["finance-closing"],
    "it": ["acceptance-freeze"],
}
AGENTS = {
    "consulting": ["support-agent", "research-agent"],
    "sales": ["sales-agent"],
    "finance": ["report-agent"],
    "it": ["code-agent"],
}


def source(file):
    with (CASE / file).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def august(file):
    return [r for r in source(file) if r["month"] == "2026-08-01" and r["contract_status"] == "Final"]


def desk_rows(room):
    if room == "consulting":
        for i, spine in enumerate((2.62, 7.5, 12.45, 17.36)):
            yield [
                (spine + side * 0.40, z, side * 90)
                for side, count in ((-1, 6 if i < 3 else 5), (1, 5))
                for z in (2.20, 3.66, 5.12, 7.98, 9.44, 10.90)[:count]
            ]
    elif room == "sales":
        for z, turn in ((2.45, 0), (5.62, 180), (8.45, 0)):
            # A cross aisle cuts each seven-seat row into a four and a three.
            yield [(21.18 + i * 1.41 + (0.90 if i >= 4 else 0), z, turn) for i in range(7)]
    elif room == "marketing":
        for spine, count in ((34.68, 4), (39.07, 3)):
            yield [
                (spine + side * 0.40, 1.55 + i * 1.49, side * 90)
                for side, n in ((-1, count), (1, 3))
                for i in range(n)
            ]
    elif room == "it":
        # Keep the occupied dual-monitor benches together, with service bays on either flank.
        for spine, start, count in ((4.20, 18.86, 5), (9.20, 17.25, 4)):
            yield [
                (spine + side * 0.40, start + i * 1.54, side * 90)
                for side, n in ((-1, count), (1, 4))
                for i in range(n)
            ]
    elif room == "finance":
        for x, count, turn in ((17.52, 7, -90), (21.85, 6, 90)):
            yield [(x, 16.22 + i * 1.46 + (0.78 if i >= 4 else 0), turn) for i in range(count)]
    elif room == "management":
        for z in (16.75, 19.25):
            yield [(x, z, 0) for x in (25.22, 27.85, 30.62)]
    elif room == "hr":
        for side in (-1, 1):
            yield [(34.78 + side * 0.4, z, side * 90) for z in (17.00, 18.49, 19.98)]


def slug(name):
    return re.sub("[^a-z0-9]+", "-", name.lower()).strip("-")


class Layout:
    def __init__(self):
        self.entries = []
        self.ids = set()
        self.occupied = list(structural_bounds())
        self.seats = defaultdict(list)
        self.wall_mounts = defaultdict(list)
        self.device_seats = defaultdict(list)
        for item in decor_items():
            self.reserve(item, item["id"])

    def fits(self, item):
        box = bounds(item)
        w, n, e, s = ROOMS.get(item["room"], CORRIDOR)[:4]
        return (
            box[0] >= w + 0.099
            and box[2] >= n + 0.099
            and box[3] <= e - 0.099
            and box[5] <= s - 0.099
            and all(not intersects(box, other) for _, other in self.occupied)
        )

    def reserve(self, item, label):
        if not self.fits(item):
            conflicts = [name for name, b in self.occupied if intersects(bounds(item), b)]
            raise ValueError(
                f"{label}: collision or outside room {item['room']}: {conflicts} {bounds(item)}"
            )
        self.occupied.append((label, bounds(item)))

    def add(self, id, room, item, **extra):
        if id in self.ids:
            raise ValueError(f"Duplicate ID {id}")
        entry = dict(id=id, room=room, **item, **extra)
        self.reserve(entry, id)
        for child in local_children(entry):
            self.reserve(dict(child, room=room), id + "/" + child["asset"])
        self.ids.add(id)
        self.entries.append(entry)
        return entry

    def first(self, id, room, asset, candidates, **extra):
        for x, z, angle, y in candidates:
            item = placed(asset, x, z, angle, y)
            if self.fits(dict(item, room=room)):
                return self.add(id, room, item, **extra)
        raise ValueError(f"No free position for {id} in {room}")

    def wall(self, id, room, asset, preferred=()):
        """Spread mounts across usable wall faces, leaving daylight and doorways clear."""
        w, n, e, s, *_ = ROOMS[room]
        width, depth, height = asset_size(asset)
        inset, y = 0.112 + depth / 2, max(0.09, 1.10 - height)
        faces = [(90, w + inset, n, s)]
        if e < 42:
            faces.append((-90, e - inset, n, s))
        if room == "marketing":
            faces.append((-90, e - inset, *EAST_DISPLAY_BAY))
        if n == 0:
            faces.append((0, n + inset, *DISPLAY_BAYS[room]))
        else:
            faces.append((180, s - inset, w, e))
        left, _, z, _ = frontage(room)
        faces.append(
            (180 if n == 0 else 0, z - inset if n == 0 else z + inset, left, left + return_width(room))
        )
        mounts = self.wall_mounts[room]

        def clearance(x, z, angle, y):
            item = placed(asset, x, z, angle, y)
            if not self.fits(dict(item, room=room)):
                return False
            # Minimum horizontal reveal between the ends of two panels on one face.
            for px, pz, pa, pw in mounts:
                if pa != angle:
                    continue
                same_plane = abs(px - x) < 0.10 if abs(angle) == 90 else abs(pz - z) < 0.10
                if same_plane and math.hypot(px - x, pz - z) < (pw + width) / 2 + 0.60:
                    return False
            return True

        options = []
        for angle, plane, start, end in faces:
            length = end - start
            usable = length - width - 0.38
            if usable < 0:
                continue
            steps = max(1, math.ceil(usable / 0.20))
            load = sum(
                a == angle and abs((px if abs(a) == 90 else pz) - plane) < 0.10 for px, pz, a, _ in mounts
            )
            sites = [start + 0.19 + width / 2 + usable * i / steps for i in range(steps + 1)]
            if 2 * width + 1.0 <= length <= 4.8:
                sites = [start + 0.19 + width / 2, end - 0.19 - width / 2]
            for along in sites:
                x, z = (plane, along) if abs(angle) == 90 else (along, plane)
                if clearance(x, z, angle, y):
                    separation = min((math.hypot(x - px, z - pz) for px, pz, _, _ in mounts), default=3)
                    score = (-load, min(separation, 4.5), -abs(along - (start + end) / 2))
                    options.append((score, (x, z, angle, y)))
        for candidate in preferred:
            if clearance(*candidate):
                position = candidate
                break
        else:
            if not options:
                raise ValueError(f"No clear wall face for {id} in {room}")
            position = max(options)[1]
        x, z, angle, y = position
        mounts.append((x, z, angle, width))
        return self.add(id, room, placed(asset, x, z, angle, y))

    def floor(self, id, room, asset, preferred=()):
        w, n, e, s, *_ = ROOMS[room]
        width, depth, _ = asset_size(asset)

        def locations():
            yield from preferred
            for i in range(int((e - w - width - 0.4) / 0.25) + 1):
                x = w + 0.24 + width / 2 + i * 0.25
                yield x, n + 0.25 + depth / 2, 0, 0
                yield x, s - 0.25 - depth / 2, 180, 0
            for i in range(int((s - n - width - 0.4) / 0.25) + 1):
                z = n + 0.24 + width / 2 + i * 0.25
                yield w + 0.25 + depth / 2, z, 90, 0
                yield e - 0.25 - depth / 2, z, -90, 0

        return self.first(id, room, asset, locations())

    def desktop(self, id, room, asset):
        occupied = self.device_seats[room]

        def priority(seat):
            x, _, z = seat["pos"]
            nearest = min((math.hypot(x - ox, z - oz) for ox, oz in occupied), default=0)
            return nearest

        seats = sorted(self.seats[room], key=priority, reverse=True)
        for x in (-0.36, 0.105, 0.36):
            for seat in seats:
                item = offset(seat, asset, x, 0.74, 0.161)
                if self.fits(dict(item, room=room)):
                    sx, _, sz = seat["pos"]
                    occupied.append((sx, sz))
                    return self.add(id, room, item, seatId=seat["id"])
        raise ValueError(f"No supported desktop space for {id}")


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
                ]
                seat = layout.add(
                    f"seat:{room}:{seq:02}",
                    room,
                    placed("desk_bench", x, z, turn),
                    children=children,
                    row=bank,
                    active=seq <= int(row["licences_active_30d"]),
                )
                seats.append(seat)
        assert len(seats) == int(row["licences_purchased"])
    for row in august("ai_subscriptions.csv"):
        room = CENTRES[row["cost_center"]]
        product = PRODUCTS[row["product"]]
        slot = ("copilot", "claude", "chatgpt").index(product)
        for i in range(int(row["licences_purchased"])):
            seat = layout.seats[room][i]
            item = offset(seat, "licence_puck", 0.52 - 0.14 * slot, 0.74, 0.235)
            layout.add(
                f"lic:{product}:{room}:{i + 1:02}",
                room,
                item,
                seatId=seat["id"],
                active=i < int(row["licences_active_30d"]),
            )
    # Four two-rack service stations: production, development, continuity and unassigned capacity.
    rack_bays = {
        "vm-app": (1.00, 19.15, 90, 0),
        "cicd": (1.00, 20.10, 90, 0),
        "vm-test": (5.50, 27.12, 180, 0),
        "dp-dev": (6.46, 27.12, 180, 0),
        "dr-failover": (14.19, 24.00, -90, 0),
        "st-backup": (14.19, 24.96, -90, 0),
        "sandboxes": (13.10, 16.13, 0, 0),
        "orphans": (14.06, 16.13, 0, 0),
    }
    for room, by_asset in INFRA.items():
        for asset, ids in by_asset.items():
            for i, id in enumerate(ids):
                if asset.startswith("wall_screen"):
                    preferred = []
                    if room == "it":
                        preferred = [(1.80 if i == 0 else 10.25, 27.838, 180, 0.12)]
                    layout.wall(id, room, asset, preferred)
                else:
                    preferred = []
                    if room == "consulting":
                        x = {"dp-prod": 0.78, "gpu-ml": 18.95, "st-proj": 12.0, "dp-storage": 13.15}[id]
                        preferred = [(x, 0.56, 0, 0)]
                    if id == "st-archive":
                        preferred = [(25.62, 11.45, 180, 0)]
                    if id == "db-fin":
                        preferred = [(19.19, 26.60, 90, 0)]
                    if asset == "rack_compact":
                        preferred = [rack_bays[id]]
                    if asset == "console_kiosk" and room == "it":
                        preferred = [(13.38, 22.5, 180, 0)]
                    layout.floor(id, room, asset, preferred)
    layout.floor("ai-marketing", "marketing", "text_machine", [(34.65, 9.27, 0, 0)])
    layout.floor("handover:queue", "management", "approval_desk", [(30.48, 21.27, 180, 0)])
    layout.add(
        "saas-m365", "corridor", placed("m365_totem", 32, 12.48), resourceIds=["saas-m365", "m365-usage"]
    )
    for room, events in WINDOWS.items():
        for event in events:
            layout.wall("window:" + event, room, "wall_calendar")
    reports = {}
    for row in source("extra/powerbi_usage.csv"):
        id, room = row["resource_id"], row["department"].lower()
        if id in reports and reports[id] != room:
            raise ValueError(f"Conflicting report owner for {id}")
        reports[id] = room
    assert set(reports) == {f"pbi-{i:02}" for i in range(1, 61)}
    for id, room in sorted(reports.items()):
        if id == "pbi-05":
            layout.wall(id, room, "wall_screen_large", [(27.8, 22.35, 0, 0.10)])
        else:
            layout.wall(id, room, "wall_screen")
    for room in DEPTS:
        layout.desktop("ai-assistant:" + room, room, "ai_orb")
    layout.desktop("ai-chatbot", "hr", "ai_orb")
    # The knowledge chatbot is shared: Consulting uses it too (department on each ai_usage.csv row).
    layout.desktop("ai-chatbot:consulting", "consulting", "ai_orb")
    layout.desktop("ai-quote", "sales", "quote_device")
    for room, agents in AGENTS.items():
        for i, agent in enumerate(agents):
            if room == "consulting":
                layout.add("agent:" + agent, room, placed("agent_robot", 5.30 + i * 0.84, 0.65, 0, 0.79))
            else:
                layout.desktop("agent:" + agent, room, "agent_robot")
    for row in contracts:
        if row["contract"] == "Microsoft 365":
            continue
        room = CENTRES[row["cost_center"]]
        contract = slug(row["contract"])
        id = f"saas:{contract}:{room}"
        if contract in ("design-tool", "survey-tool", "e-signature"):
            station = {
                ("marketing", "design-tool"): (39.75, 7.02, 0, 0),
                ("marketing", "survey-tool"): (36.09, 9.25, 0, 0),
                ("sales", "e-signature"): (24.06, 10.85, 180, 0),
                ("finance", "e-signature"): (19.45, 24.50, 180, 0),
            }[room, contract]
            layout.floor(id, room, "tablet_stand", [station])
        else:
            layout.desktop(id, room, "saas_terminal")
    expected = {"seat:": 119, "lic:": 157, "saas:": 48, "agent:": 5, "window:": 4, "ai-assistant:": 7}
    for prefix, count in expected.items():
        assert sum(id.startswith(prefix) for id in layout.ids) == count, (prefix, count)
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
        + ",\n".join("  " + json.dumps(row, separators=(",", ": ")) for row in [*layout.entries, *island_entries()])
        + "\n]\n"
    )


if __name__ == "__main__":
    write_layout(build_layout())
