"""Pianta tecnica dell'ufficio ricavata dal modello 3D (reverse engineering, per l'animazione «planimetria → 3D»).

Taglia il modello dell'edificio a 0,90 m (come una vera pianta architettonica): le sezioni di muri e mattoni
diventano campiture piene, i vetri linee doppie, gli arredi contorni sottili visti dall'alto. Aggiunge quote,
assi, nomi e superfici dei locali, nord, scala grafica e cartiglio. Coordinate SVG = metri del modello (x, z),
così la pianta si sovrappone esattamente alla vista dall'alto della scena 3D.

Uso:  python web/scripts/make-floorplan.py   →   web/public/blueprints/level-01.svg (+ level-01.json)
"""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path

import numpy as np

WEB = Path(__file__).resolve().parent.parent
MODELS = WEB / "public" / "models"
OUT = WEB / "public" / "blueprints"

CUT = 0.90  # altezza del piano di sezione (m)
# Foglio A2 orizzontale in scala 1:100 → 59,4 × 42,0 m di modello.
PAPER = (-29.7, -18.2, 59.4, 42.0)  # x, z, larghezza, altezza

ROOM_NAME = {
    "consulting": "CONSULTING", "sales": "SALES", "marketing": "MARKETING", "it": "IT",
    "finance": "FINANCE", "management": "MANAGEMENT", "hr": "HR", "corridor": "CORRIDOR",
    "reception": "RECEPTION", "entry_gallery": "ENTRY",
}
ROOM_NO = {
    "consulting": "1.01", "sales": "1.02", "marketing": "1.03", "hr": "1.04", "management": "1.05",
    "finance": "1.06", "it": "1.07", "corridor": "1.10", "reception": "1.11", "entry_gallery": "1.12",
}


# ---------------------------------------------------------------------------------------------- lettura GLB
class Glb:
    def __init__(self, path: Path):
        b = path.read_bytes()
        n = struct.unpack("<I", b[12:16])[0]
        self.j = json.loads(b[20:20 + n])
        off = 20 + n
        blen = struct.unpack("<I", b[off:off + 4])[0]
        self.bin = b[off + 8:off + 8 + blen]

    def accessor(self, i: int) -> np.ndarray:
        a = self.j["accessors"][i]
        v = self.j["bufferViews"][a["bufferView"]]
        dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[a["componentType"]]
        k = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        start = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = v.get("byteStride", 0)
        isz = np.dtype(dt).itemsize
        if stride and stride != k * isz:
            raw = np.frombuffer(self.bin, np.uint8, a["count"] * stride, start).reshape(-1, stride)
            return raw[:, :k * isz].copy().view(dt).reshape(-1, k)
        return np.frombuffer(self.bin, dt, a["count"] * k, start).reshape(-1, k) if k > 1 else np.frombuffer(self.bin, dt, a["count"], start)

    def meshes(self):
        """(nome del nodo, nome del materiale, vertici in mondo Nx3, triangoli Mx3) per ogni primitiva."""
        nodes = self.j["nodes"]
        mats = self.j.get("materials", [])

        def walk(i, parent):
            n = nodes[i]
            m = parent @ trs(n)
            if "mesh" in n:
                for p in self.j["meshes"][n["mesh"]]["primitives"]:
                    pos = self.accessor(p["attributes"]["POSITION"]).astype(np.float64)
                    pos = (np.c_[pos, np.ones(len(pos))] @ m.T)[:, :3]
                    idx = self.accessor(p["indices"]).reshape(-1, 3) if "indices" in p else np.arange(len(pos)).reshape(-1, 3)
                    yield n.get("name", ""), mats[p["material"]]["name"] if "material" in p else "", pos, idx
            for c in n.get("children", []):
                yield from walk(c, m)

        for r in self.j["scenes"][self.j.get("scene", 0)]["nodes"]:
            yield from walk(r, np.eye(4))


def trs(n) -> np.ndarray:
    if "matrix" in n:
        return np.array(n["matrix"]).reshape(4, 4).T
    t = n.get("translation", [0, 0, 0])
    x, y, z, w = n.get("rotation", [0, 0, 0, 1])
    s = n.get("scale", [1, 1, 1])
    r = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    m = np.eye(4)
    m[:3, :3] = r * s
    m[:3, 3] = t
    return m


# ---------------------------------------------------------------------------------------------- geometria
def section(pos: np.ndarray, tri: np.ndarray, h: float) -> list[tuple]:
    """Segmenti (x1, z1, x2, z2) dove i triangoli attraversano il piano y = h."""
    out = []
    p = pos[tri]  # M×3×3
    d = p[:, :, 1] - h
    for t, dd in zip(p, d):
        pts = []
        for a, b in ((0, 1), (1, 2), (2, 0)):
            if (dd[a] < 0) != (dd[b] < 0):
                f = dd[a] / (dd[a] - dd[b])
                q = t[a] + f * (t[b] - t[a])
                pts.append((q[0], q[2]))
        if len(pts) == 2 and (abs(pts[0][0] - pts[1][0]) + abs(pts[0][1] - pts[1][1])) > 1e-5:
            out.append((*pts[0], *pts[1]))
    return out


def loops(segs: list[tuple]) -> list[list[tuple]]:
    """Unisce i segmenti in catene (chiuse quando possibile)."""
    key = lambda x, z: (round(x, 3), round(z, 3))
    adj: dict = {}
    for i, (x1, z1, x2, z2) in enumerate(segs):
        adj.setdefault(key(x1, z1), []).append(i)
        adj.setdefault(key(x2, z2), []).append(i)
    used = [False] * len(segs)
    out = []
    for i in range(len(segs)):
        if used[i]:
            continue
        used[i] = True
        x1, z1, x2, z2 = segs[i]
        chain = [(x1, z1), (x2, z2)]
        while True:
            k = key(*chain[-1])
            nxt = next((j for j in adj.get(k, []) if not used[j]), None)
            if nxt is None:
                break
            used[nxt] = True
            a = segs[nxt]
            chain.append((a[2], a[3]) if key(a[0], a[1]) == k else (a[0], a[1]))
        out.append(chain)
    return out


def hull(pts: np.ndarray) -> list[tuple]:
    pts = sorted(set(map(tuple, np.round(pts, 3))))
    if len(pts) < 3:
        return pts
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def area(pos: np.ndarray, tri: np.ndarray) -> float:
    p = pos[tri][:, :, [0, 2]]
    a = p[:, 1] - p[:, 0]
    b = p[:, 2] - p[:, 0]
    return float(np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]).sum() / 2)


def f(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


def path(chain, close=True) -> str:
    s = "M" + " L".join(f"{f(x)} {f(z)}" for x, z in chain)
    return s + (" Z" if close else "")


# ---------------------------------------------------------------------------------------------- disegno
def main():
    office = Glb(MODELS / "env_office_v1.glb")
    walls, brick, glass, frames, floors, decor = [], [], [], [], {}, []
    for node, mat, pos, tri in office.meshes():
        if node.startswith("floor_"):
            r = node[6:]
            floors.setdefault(r, {"area": 0.0, "pts": []})
            floors[r]["area"] += area(pos, tri)
            floors[r]["pts"].append(pos[:, [0, 2]])
        elif node == "architecture" or node.startswith("accent_wall"):
            segs = section(pos, tri, CUT)
            (brick if mat.startswith("Brick") else glass if mat == "Glass" else frames if mat in ("Graphite", "Walnut", "Oak") else walls).extend(segs)
        elif node.startswith("decor:"):
            if pos[:, 1].max() > 0.02:
                decor.append(hull(pos[:, [0, 2]]))

    # Arredi delle postazioni: contorni dei moduli (scrivania, sedia, monitor) dalla libreria.
    kits = {}
    def kit(asset):
        if asset not in kits:
            g = Glb(MODELS / f"kit_{asset}_v1.glb")
            kits[asset] = np.vstack([p[:, [0, 2]] for _, _, p, _ in g.meshes()])
        return kits[asset]

    layout = json.loads((MODELS / "layout.json").read_text())
    seats = [i for i in layout if i.get("view") != "island" and i.get("room")]
    furniture = []
    for it in seats:
        def place(asset, dx, dz, rot):
            c, s = math.cos(rot), math.sin(rot)
            pts = kit(asset)
            x = pts[:, 0] * c + pts[:, 1] * s
            z = -pts[:, 0] * s + pts[:, 1] * c
            return np.c_[x + dx, z + dz]
        x0, _, z0 = it["pos"]
        furniture.append(("desk", hull(place(it["asset"], x0, z0, it["rotY"]))))
        for ch in it.get("children", []):
            c, s = math.cos(it["rotY"]), math.sin(it["rotY"])
            dx = ch["pos"][0] * c + ch["pos"][2] * s
            dz = -ch["pos"][0] * s + ch["pos"][2] * c
            kind = "chair" if "chair" in ch["asset"] else "monitor" if "monitor" in ch["asset"] else "pc"
            furniture.append((kind, hull(place(ch["asset"], x0 + dx, z0 + dz, it["rotY"] + ch["rotY"]))))

    # Riquadri dei locali e assi strutturali dai bordi dei pavimenti.
    rooms = {}
    for r, d in floors.items():
        p = np.vstack(d["pts"])
        rooms[r] = {"min": p.min(0).round(2).tolist(), "max": p.max(0).round(2).tolist(), "area": round(d["area"], 1)}
    allp = np.vstack([np.vstack(d["pts"]) for d in floors.values()])
    (bx0, bz0), (bx1, bz1) = allp.min(0), allp.max(0)
    xs = sorted({round(v, 1) for r in rooms.values() for v in (r["min"][0], r["max"][0])})
    zs = sorted({round(v, 1) for r in rooms.values() for v in (r["min"][1], r["max"][1])})
    xs = [v for i, v in enumerate(xs) if i == 0 or v - xs[i - 1] > 0.6]
    zs = [v for i, v in enumerate(zs) if i == 0 or v - zs[i - 1] > 0.6]

    px, pz, pw, ph = PAPER
    # Cianografia «da film»: carta blu di Prussia, linee bianche, quadrettatura sottile.
    PAPER_BG = "#1a4c8b"
    INK = "#ffffff"
    MID = "#d4e3f6"
    LIGHT = "#8fb2dc"
    GLASS = "#4f80bf"
    svg = []
    add = svg.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="594mm" height="420mm" viewBox="{f(px)} {f(pz)} {f(pw)} {f(ph)}" '
        f'font-family="Helvetica Neue, Helvetica, Arial, sans-serif" data-cut="{CUT}">')
    add('<defs><pattern id="hatch" width="0.25" height="0.25" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        f'<line x1="0" y1="0" x2="0" y2="0.25" stroke="{MID}" stroke-width="0.025"/></pattern></defs>')
    add('<defs><pattern id="minor" width="1" height="1" patternUnits="userSpaceOnUse">'
        f'<path d="M1 0 L0 0 0 1" fill="none" stroke="{LIGHT}" stroke-width="0.012" opacity="0.45"/></pattern>'
        '<pattern id="major" width="5" height="5" patternUnits="userSpaceOnUse">'
        f'<path d="M5 0 L0 0 0 5" fill="none" stroke="{LIGHT}" stroke-width="0.03" opacity="0.5"/></pattern>'
        '<radialGradient id="vignette" cx="50%" cy="48%" r="75%"><stop offset="55%" stop-color="#0b2a55" stop-opacity="0"/>'
        '<stop offset="100%" stop-color="#0b2a55" stop-opacity="0.55"/></radialGradient></defs>')
    add(f'<rect x="{f(px)}" y="{f(pz)}" width="{f(pw)}" height="{f(ph)}" fill="{PAPER_BG}"/>')
    add(f'<g id="paper"><rect x="{f(px)}" y="{f(pz)}" width="{f(pw)}" height="{f(ph)}" fill="url(#minor)"/>'
        f'<rect x="{f(px)}" y="{f(pz)}" width="{f(pw)}" height="{f(ph)}" fill="url(#major)"/>'
        f'<rect x="{f(px)}" y="{f(pz)}" width="{f(pw)}" height="{f(ph)}" fill="url(#vignette)"/></g>')
    # Cornice del foglio.
    m = 1.0
    add(f'<rect x="{f(px + m)}" y="{f(pz + m)}" width="{f(pw - 2 * m)}" height="{f(ph - 2 * m)}" fill="none" stroke="{INK}" stroke-width="0.09"/>')
    add(f'<rect x="{f(px + m + 0.25)}" y="{f(pz + m + 0.25)}" width="{f(pw - 2 * m - 0.5)}" height="{f(ph - 2 * m - 0.5)}" fill="none" stroke="{INK}" stroke-width="0.025"/>')

    # Griglia strutturale (assi A… e 1…), sotto a tutto.
    add('<g id="grid">')
    letters = "ABCDEFGHIJKLMN"
    for i, x in enumerate(xs):
        add(f'<line x1="{f(x)}" y1="{f(bz0 - 2.2)}" x2="{f(x)}" y2="{f(bz1 + 1.2)}" stroke="{LIGHT}" stroke-width="0.02" stroke-dasharray="0.6 0.15 0.08 0.15"/>')
        add(f'<circle cx="{f(x)}" cy="{f(bz0 - 2.75)}" r="0.5" fill="{PAPER_BG}" stroke="{INK}" stroke-width="0.04"/>')
        add(f'<text x="{f(x)}" y="{f(bz0 - 2.58)}" font-size="0.5" text-anchor="middle" fill="{INK}">{letters[i]}</text>')
    for i, z in enumerate(zs):
        add(f'<line x1="{f(bx0 - 2.2)}" y1="{f(z)}" x2="{f(bx1 + 1.2)}" y2="{f(z)}" stroke="{LIGHT}" stroke-width="0.02" stroke-dasharray="0.6 0.15 0.08 0.15"/>')
        add(f'<circle cx="{f(bx0 - 2.75)}" cy="{f(z)}" r="0.5" fill="{PAPER_BG}" stroke="{INK}" stroke-width="0.04"/>')
        add(f'<text x="{f(bx0 - 2.75)}" y="{f(z + 0.18)}" font-size="0.5" text-anchor="middle" fill="{INK}">{i + 1}</text>')
    add("</g>")

    # Pavimenti delle zone di passaggio: retino leggero.
    add('<g id="floors">')
    for r in ("corridor", "reception", "entry_gallery"):
        if r in rooms:
            a, b = rooms[r]["min"], rooms[r]["max"]
            add(f'<rect x="{f(a[0])}" y="{f(a[1])}" width="{f(b[0] - a[0])}" height="{f(b[1] - a[1])}" fill="url(#hatch)" opacity="0.35"/>')
    add("</g>")

    # Arredi: sotto la sezione dei muri, tratto sottile.
    add(f'<g id="furniture" fill="none" stroke="{MID}" stroke-width="0.025" stroke-linejoin="round">')
    for h in decor:
        if len(h) >= 3:
            add(f'<path d="{path(h)}"/>')
    for kind, h in furniture:
        if len(h) < 3:
            continue
        if kind == "chair":
            add(f'<path d="{path(h)}" stroke="{LIGHT}"/>')
        elif kind == "desk":
            add(f'<path d="{path(h)}" fill="{PAPER_BG}"/>')
        else:
            add(f'<path d="{path(h)}" stroke-width="0.02"/>')
    add("</g>")

    # Sezione: vetri (linea doppia), telai, muri e mattoni pieni.
    add(f'<g id="glass" fill="{GLASS}" stroke="{MID}" stroke-width="0.018">')
    for c in loops(glass):
        add(f'<path d="{path(c, len(c) > 2)}"/>')
    add("</g>")
    add(f'<g id="frames" fill="{MID}" stroke="{MID}" stroke-width="0.01">')
    for c in loops(frames):
        add(f'<path d="{path(c, len(c) > 2)}"/>')
    add("</g>")
    add(f'<g id="walls" fill="{INK}" stroke="{INK}" stroke-width="0.03" fill-rule="evenodd">')
    for c in loops(walls) + loops(brick):
        add(f'<path d="{path(c, len(c) > 2)}"/>')
    add("</g>")

    # Nomi, numeri e superfici dei locali.
    add(f'<g id="rooms" fill="{INK}" text-anchor="middle">')
    for r, d in rooms.items():
        if r not in ROOM_NAME:
            continue
        cx = (d["min"][0] + d["max"][0]) / 2
        cz = (d["min"][1] + d["max"][1]) / 2
        if r == "corridor":
            cx, cz = -3.0, cz
        small = r in ("corridor", "reception", "entry_gallery")
        fs = 0.42 if small else 0.62
        add(f'<g transform="translate({f(cx)} {f(cz)})">'
            f'<rect x="{f(-2.2 if not small else -1.6)}" y="-0.75" width="{f(4.4 if not small else 3.2)}" height="1.75" fill="{PAPER_BG}" opacity="0.92"/>'
            f'<text y="0" font-size="{fs}" font-weight="700" letter-spacing="0.06">{ROOM_NAME[r]}</text>'
            f'<text y="{f(fs * 1.05)}" font-size="{f(fs * 0.62)}" fill="{MID}">{ROOM_NO.get(r, "")}  ·  {d["area"]:.1f} m²</text></g>')
    add("</g>")

    # Quote: catena esterna (locali) e quota totale, sopra e a sinistra.
    add(f'<g id="dims" stroke="{INK}" stroke-width="0.02" fill="{INK}" font-size="0.34" text-anchor="middle">')

    def dim_h(x1, x2, z, label=True):
        add(f'<line x1="{f(x1 - 0.3)}" y1="{f(z)}" x2="{f(x2 + 0.3)}" y2="{f(z)}"/>')
        for x in (x1, x2):
            add(f'<line x1="{f(x - 0.15)}" y1="{f(z + 0.15)}" x2="{f(x + 0.15)}" y2="{f(z - 0.15)}" stroke-width="0.05"/>')
            add(f'<line x1="{f(x)}" y1="{f(z - 0.3)}" x2="{f(x)}" y2="{f(z + 0.3)}"/>')
        if label:
            add(f'<text x="{f((x1 + x2) / 2)}" y="{f(z - 0.15)}" stroke="none">{round((x2 - x1) * 1000):d}</text>')

    def dim_v(z1, z2, x):
        add(f'<line x1="{f(x)}" y1="{f(z1 - 0.3)}" x2="{f(x)}" y2="{f(z2 + 0.3)}"/>')
        for z in (z1, z2):
            add(f'<line x1="{f(x - 0.15)}" y1="{f(z + 0.15)}" x2="{f(x + 0.15)}" y2="{f(z - 0.15)}" stroke-width="0.05"/>')
            add(f'<line x1="{f(x - 0.3)}" y1="{f(z)}" x2="{f(x + 0.3)}" y2="{f(z)}"/>')
        add(f'<text transform="translate({f(x - 0.15)} {f((z1 + z2) / 2)}) rotate(-90)" stroke="none">{round((z2 - z1) * 1000):d}</text>')

    for a, b in zip(xs, xs[1:]):
        dim_h(a, b, bz0 - 0.9)
    dim_h(xs[0], xs[-1], bz0 - 1.7)
    for a, b in zip(zs, zs[1:]):
        dim_v(a, b, bx0 - 0.9)
    dim_v(zs[0], zs[-1], bx0 - 1.7)
    add("</g>")

    # Ingresso.
    add(f'<g id="entrance" fill="{INK}" font-size="0.36" text-anchor="middle"><path d="M{f(bx1 - 1)} {f(bz1 + 1.4)} l0.4 -0.7 l0.4 0.7 Z"/>'
        f'<text x="{f(bx1 - 0.6)}" y="{f(bz1 + 2.0)}">ENTRANCE</text></g>')

    # Nord, scala grafica, legenda e cartiglio (in basso).
    y0 = bz1 + 3.0
    add(f'<g id="north" transform="translate({f(px + 4)} {f(y0 + 1.7)})" fill="{INK}" stroke="{INK}" stroke-width="0.04">'
        '<circle r="1.1" fill="none"/><path d="M0 -1.1 L0.42 0.5 L0 0.15 L-0.42 0.5 Z"/>'
        '<text y="-1.35" font-size="0.5" text-anchor="middle" stroke="none">N</text></g>')
    sx = px + 7
    add(f'<g id="scale" font-size="0.3" fill="{INK}" stroke="{INK}" stroke-width="0.02">')
    for i in range(5):
        add(f'<rect x="{f(sx + i)}" y="{f(y0 + 1.5)}" width="1" height="0.25" fill="{INK if i % 2 == 0 else PAPER_BG}"/>')
    for i in (0, 1, 2, 5):
        add(f'<text x="{f(sx + i)}" y="{f(y0 + 1.3)}" text-anchor="middle" stroke="none">{i}</text>')
    add(f'<text x="{f(sx + 5.4)}" y="{f(y0 + 1.73)}" stroke="none">m</text>')
    add(f'<text x="{f(sx)}" y="{f(y0 + 2.6)}" stroke="none" font-size="0.34">SCALE 1:100 (A2)</text></g>')

    lx = sx + 8
    add(f'<g id="legend" font-size="0.3" fill="{INK}">'
        f'<rect x="{f(lx)}" y="{f(y0 + 0.4)}" width="0.9" height="0.35" fill="{INK}"/><text x="{f(lx + 1.2)}" y="{f(y0 + 0.68)}">Wall, cut at +{CUT:.2f} m</text>'
        f'<rect x="{f(lx)}" y="{f(y0 + 1.0)}" width="0.9" height="0.35" fill="{GLASS}" stroke="{MID}" stroke-width="0.02"/><text x="{f(lx + 1.2)}" y="{f(y0 + 1.28)}">Glazing / glass partition</text>'
        f'<rect x="{f(lx)}" y="{f(y0 + 1.6)}" width="0.9" height="0.35" fill="none" stroke="{MID}" stroke-width="0.025"/><text x="{f(lx + 1.2)}" y="{f(y0 + 1.88)}">Workstation module (desk 1.60 × 0.80)</text>'
        f'<rect x="{f(lx)}" y="{f(y0 + 2.2)}" width="0.9" height="0.35" fill="url(#hatch)"/><text x="{f(lx + 1.2)}" y="{f(y0 + 2.48)}">Circulation (limestone)</text></g>')

    # Cartiglio.
    tw, th = 17.5, 4.6
    tx = px + pw - m - 0.25 - tw
    ty = pz + ph - m - 0.25 - th
    n_seats = len(seats)
    net = sum(d["area"] for d in rooms.values())
    rows = [
        ("PROJECT", "Basel head office · Digital twin"),
        ("DRAWING", "Floor plan · Level 01"),
        ("SCALE", "1:100 @ A2"),
        ("NET AREA", f"{net:.0f} m²  ·  {n_seats} workstations"),
    ]
    add(f'<g id="titleblock" fill="{INK}" stroke="{INK}" stroke-width="0.03">')
    add(f'<rect x="{f(tx)}" y="{f(ty)}" width="{f(tw)}" height="{f(th)}" fill="{PAPER_BG}"/>')
    add(f'<line x1="{f(tx + 12)}" y1="{f(ty)}" x2="{f(tx + 12)}" y2="{f(ty + th)}"/>')
    for i, (k, v) in enumerate(rows):
        yy = ty + 0.25 + i * 1.08
        if i:
            add(f'<line x1="{f(tx)}" y1="{f(yy - 0.25)}" x2="{f(tx + 12)}" y2="{f(yy - 0.25)}" stroke-width="0.015"/>')
        add(f'<text x="{f(tx + 0.3)}" y="{f(yy + 0.3)}" font-size="0.24" fill="{MID}" stroke="none" letter-spacing="0.05">{k}</text>')
        add(f'<text x="{f(tx + 0.3)}" y="{f(yy + 0.78)}" font-size="0.42" stroke="none">{v}</text>')
    add(f'<text x="{f(tx + 12.3)}" y="{f(ty + 0.55)}" font-size="0.24" fill="{MID}" stroke="none">DWG NO.</text>')
    add(f'<text x="{f(tx + 12.3)}" y="{f(ty + 1.8)}" font-size="1.05" font-weight="700" stroke="none">A-101</text>')
    add(f'<text x="{f(tx + 12.3)}" y="{f(ty + 2.6)}" font-size="0.24" fill="{MID}" stroke="none">REV.  C   ·   STATUS  AS BUILT</text>')
    add(f'<text x="{f(tx + 12.3)}" y="{f(ty + 3.3)}" font-size="0.24" fill="{MID}" stroke="none">SHEET  1 / 1</text>')
    add(f'<text x="{f(tx + 12.3)}" y="{f(ty + 4.0)}" font-size="0.24" fill="{MID}" stroke="none">GREENOPS · FACILITIES</text>')
    add("</g>")
    add("</svg>")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "level-01.svg").write_text("\n".join(svg))
    # Metadati per l'animazione: foglio, ingombro dell'edificio, locali e numeri «riconosciuti».
    meta = {
        "paper": {"x": px, "z": pz, "w": pw, "h": ph},
        "building": {"minX": round(bx0, 2), "minZ": round(bz0, 2), "maxX": round(bx1, 2), "maxZ": round(bz1, 2)},
        "cut": CUT,
        "rooms": {r: {**d, "name": ROOM_NAME.get(r, r.upper()), "no": ROOM_NO.get(r, "")} for r, d in rooms.items()},
        "counts": {
            "wall_segments": len(walls) + len(brick),
            "glass_segments": len(glass),
            "workstations": n_seats,
            "furniture": len(decor),
            "axes": len(xs) + len(zs),
        },
    }
    (OUT / "level-01.json").write_text(json.dumps(meta, indent=1))
    print(f"level-01.svg: {meta['counts']}  ·  {len(rooms)} rooms, {net:.0f} m²")


if __name__ == "__main__":
    main()
