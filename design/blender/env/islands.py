"""Build the §5 environment and render the exported GLB with its physical hardware."""

import json
import math
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.geometry import convex_hull_2d

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from env.island_layout import DECK_HEIGHT, ISLANDS, M1, PROVIDER_COLOURS, footprint, island_entries
from env.layout import build_layout, write_layout
from env.office import join_parts, run_headless
from env.plan import MODELS, PREVIEWS, gltf
from kit.common import PALETTE, anchor, box, loft, material, mesh, rod, slab
from previews import ELEVATION, RIGHT, UP, caption, extents, load_model, save, studio

ENV = MODELS / "env_islands_v1.glb"
TAU = math.tau
ISLAND_COLOURS = {
    "Sandstone": "C99878",
    "Limestone": "E4CEAA",
    "Shale": "917C74",
    "Meadow": "A5BC84",
    "Lake": "65B4B7",
    "Shallows": "A8D2C5",
    "Ripple": "D7EAE0",
    "Hill": "83A572",
    "Tower glass": "82A8AD",
}


def point(x, z, h):
    return (x, -z, h)


def oval(name, x, z, h, radii, finish):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, location=point(x, z, h))
    obj = bpy.context.object
    obj.name, obj.scale = name, radii
    obj.data.materials.append(material(finish))
    for face in obj.data.polygons:
        face.use_smooth = True
    return obj


def outline(t, rx, rz, phase):
    r = 1 + 0.047 * math.sin(3 * t + phase) + 0.025 * math.cos(5 * t - phase)
    return rx * r * math.cos(t), rz * r * math.sin(t)


def stratum(name, x, z, rx, rz, phase, rings, finish):
    # Gently undulate the seams, keeping the upper planting surface level.
    n = 56
    vertices = []
    for scale, h, wave in rings:
        for i in range(n):
            t = -TAU * i / n
            dx, dz = outline(t, rx, rz, phase)
            vertices.append(point(x + dx * scale, z + dz * scale, h + wave * math.sin(3 * t + phase)))
    faces = [tuple(reversed(range(n)))]
    for k in range(len(rings) - 1):
        for i in range(n):
            a, b = n * k + i, n * k + (i + 1) % n
            faces.append((a, b, b + n, a + n))
    faces.append(tuple(range(len(vertices) - n, len(vertices))))
    obj = mesh(name, vertices, faces, finish, smooth=True)
    obj.data.polygons[-1].use_smooth = obj.data.polygons[0].use_smooth = False


def terrain(x, z, rx, rz, phase, depth=1, top="Meadow"):
    layers = [
        (
            "Bedrock",
            "Shale",
            [(0.26, -2.32, 0.11), (0.53, -2.05, 0.14), (0.71, -1.36, 0.06), (0.74, -1.29, 0.05)],
        ),
        (
            "Lower ledge",
            "Sandstone",
            [(0.73, -1.31, 0.05), (0.82, -1.23, 0.05), (0.88, -0.84, 0.05), (0.90, -0.76, 0.04)],
        ),
        (
            "Pale seam",
            "Limestone",
            [(0.89, -0.78, 0.04), (0.93, -0.69, 0.04), (0.945, -0.57, 0.04)],
        ),
        (
            "Stone lip",
            "Felt",
            [(0.94, -0.59, 0.04), (0.98, -0.49, 0.04), (1, -0.27, 0.03), (1, -0.22, 0.02)],
        ),
        ("Crown", top, [(0.997, -0.24, 0.02), (1.007, -0.15, 0.01), (1, -0.065, 0), (0.975, 0, 0)]),
    ]
    for name, finish, rings in layers:
        stratum(name, x, z, rx, rz, phase, [(s, h * depth, w * depth) for s, h, w in rings], finish)


def provider_pad(provider, footprints):
    # Round the perimeter around the equipment on this terrace.
    corners = [
        Vector((x + 0.145 * math.cos(i * TAU / 16), -z + 0.145 * math.sin(i * TAU / 16)))
        for outline in footprints
        for x, z in outline
        for i in range(16)
    ]
    rim = [corners[i] for i in convex_hull_2d(corners)]
    if sum(a.x * b.y - a.y * b.x for a, b in zip(rim, rim[1:] + rim[:1])) < 0:
        rim.reverse()
    n = len(rim)
    verts = [(p.x, p.y, h) for h in (-0.015, DECK_HEIGHT) for p in rim]
    faces = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    faces.extend((i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n))
    return mesh("pad_" + provider, verts, faces, "Pad " + provider)


def tree(x, z, h, style, base=0):
    trunk = "Walnut"
    rod("Trunk", point(x, z, base - 0.04), point(x, z, base + h * 0.72), h * 0.047, trunk, tip=h * 0.031)
    if style == "fir":
        for lo, hi, width, finish in (
            (0.24, 0.78, 0.25, "Moss"),
            (0.43, 0.95, 0.216, "Leaf"),
            (0.62, 1.08, 0.16, "Hill"),
        ):
            profile = [
                (lo, 0.72 * width),
                (lo + 0.025, width),
                (lo + 0.09, width * 0.99),
                (hi - 0.055, 0.032),
                (hi, 0.009),
            ]
            loft("Fir boughs", [(x, -z, base + y * h, r * h, r * h) for y, r in profile], finish, 14)
    else:
        oval("Canopy", x, z, base + 0.73 * h, (0.25 * h, 0.22 * h, 0.34 * h), style)
        rod(
            "Branch",
            point(x, z, base + h * 0.35),
            point(x - 0.14 * h, z + 0.035 * h, base + h * 0.58),
            h * 0.027,
            trunk,
        )
        oval(
            "Side crown",
            x - 0.13 * h,
            z + 0.035 * h,
            base + 0.6 * h,
            (0.17 * h, 0.16 * h, 0.20 * h),
            style,
        )


def lake(rx, rz):
    # An open shoreline follows the actual southern rim of the Zurich terrain.
    n = 44
    rings = [[], [], []]
    for i in range(n + 1):
        q = i / n
        t = 0.07 * TAU + 0.39 * TAU * q
        x, z = outline(t, rx, rz, 0.4)
        wave = math.sin(math.pi * q) ** 0.9
        for ring, inset in zip(rings, (0, 0.32, 0.37)):
            ring.append(point(x * (0.974 - inset * wave), z * (0.974 - inset * wave), 0.014))
    for a, b, finish in ((rings[0], rings[1], "Lake"), (rings[1], rings[2], "Shallows")):
        mesh("Lake edge", a + b, [(i, n + 1 + i, n + 2 + i, i + 1) for i in range(n)], finish)
    for x, z, w in ((-0.5, 3.43, 0.52), (0.30, 3.42, 0.29), (1.28, 3.02, 0.38)):
        oval("Reflection", x, z, 0.023, (w, 0.035, 0.012), "Ripple")
    for i in range(6):
        slab("Jetty plank", point(-1.21, 2.68 + i * 0.135, 0.105), (0.42, 0.125, 0.085), "Oak", 0.025)
    for z in (2.72, 3.31):
        for x in (-1.37, -1.05):
            rod("Jetty pier", point(x, z, 0.006), point(x, z, 0.18), 0.029, "Walnut")


def pitched_roof(x, z, width, depth, eaves, ridge, finish):
    """Gabled roof with the ridge running from front to back."""
    verts = [
        point(px, pz, h)
        for pz in (z - depth / 2, z + depth / 2)
        for px, h in ((x - width / 2, eaves), (x + width / 2, eaves), (x, ridge))
    ]
    mesh("Gable", verts, [(0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)], finish)


def grossmunster(x, z):
    box("Limestone nave", point(x, z, 0.49), (0.94, 1.15, 0.98), "Limestone", 0.035)
    pitched_roof(x, z, 0.99, 1.20, 0.96, 1.33, "Clay")
    for tx in (x - 0.50, x + 0.50):
        tz = z + 0.30
        box("Bell tower", point(tx, tz, 0.81), (0.43, 0.47, 1.62), "Plaster", 0.022, 2)
        slab("Belfry cornice", point(tx, tz, 1.61), (0.48, 0.52, 0.09), "Limestone", 0.035)
        for dx in (-0.083, 0.083):
            box("Bell opening", point(tx + dx, tz + 0.237, 1.36), (0.090, 0.016, 0.28), "Walnut", 0.035)
        loft(
            "Tower crown",
            [
                (tx, -tz, h, r, r)
                for h, r in (
                    (1.65, 0.24),
                    (1.75, 0.25),
                    (1.90, 0.16),
                    (1.96, 0.10),
                    (2.06, 0.09),
                    (2.15, 0.022),
                )
            ],
            "Shale",
            8,
        )
        rod("Finial", point(tx, tz, 2.13), point(tx, tz, 2.25), 0.017, "Brass", 8, 0.008)


def custom_house(x, z):
    slab("Stone steps", point(x, z + 0.06, 0.07), (2.10, 0.89, 0.14), "Limestone", 0.055)
    box("River frontage", point(x, z, 0.46), (1.98, 0.73, 0.70), "Plaster", 0.032)
    slab("Parapet", point(x, z, 0.81), (2.05, 0.79, 0.09), "Limestone", 0.035)
    for dx in (-0.76, -0.53, 0.53, 0.76):
        box("Sash window", point(x + dx, z + 0.369, 0.50), (0.12, 0.018, 0.30), "Shale", 0.025)
    for dx in (-0.27, -0.09, 0.09, 0.27):
        rod(
            "Portico column",
            point(x + dx, z + 0.44, 0.13),
            point(x + dx, z + 0.44, 0.76),
            0.042,
            "Limestone",
            10,
        )
    pitched_roof(x, z + 0.35, 0.77, 0.34, 0.76, 0.99, "Limestone")
    loft(
        "Cupola drum",
        [(x, -z, h, r, r) for h, r in ((0.84, 0.33), (0.90, 0.35), (1.19, 0.31))],
        "Plaster",
        16,
    )
    loft(
        "Copper dome",
        [
            (x, -z, h, r, r)
            for h, r in ((1.18, 0.35), (1.29, 0.35), (1.44, 0.29), (1.58, 0.18), (1.64, 0.07))
        ],
        "Enamel",
        20,
    )
    rod("Lantern", point(x, z, 1.63), point(x, z, 1.82), 0.042, "Brass", 10, 0.024)


def zurich():
    rx, rz = 5.82, 4.05
    terrain(0, 0, rx, rz, 0.4)
    terrain(8.85, 0.12, 2.18, 1.96, 2.3, 0.78, "Leaf")
    lake(rx, rz)
    grossmunster(3.22, -0.85)
    slab("Hoster footbridge", point(6.17, 0.06, 0.10), (1.85, 0.68, 0.13), "Oak", 0.07)
    for x, z, h in ((-3.78, -2.18, 2.2), (-2.74, -2.87, 2.65), (1.64, -3.30, 1.70)):
        tree(x, z, h, "fir")
    tree(-4.63, 1.19, 1.7, "Leaf")


def frankfurt():
    terrain(0, 0.30, 3.65, 3.16, 1.2, 0.94, "Hill")
    x, z = -0.62, -1.28
    slab("Tower footing", point(x, z, 0.10), (1.48, 1.20, 0.20), "Limestone", 0.17)
    box("Tower shaft", point(x, z, 1.61), (0.86, 0.75, 2.90), "Tower glass", 0.085, 3)
    box("Tower shoulder", point(x + 0.38, z + 0.06, 1.21), (0.46, 0.69, 2.17), "Enamel", 0.05, 3)
    for a in (-0.33, 0.33):
        box("Tower mullion", point(x + a, z + 0.37, 1.62), (0.064, 0.057, 2.80), "Plaster", 0.018)
    for h in (0.72, 1.44, 2.16, 2.88):
        slab("Tower belt", point(x, z, h), (0.90, 0.79, 0.06), "Limestone", 0.10)
    box("Setback crown", point(x, z, 3.27), (0.54, 0.49, 0.49), "Tower glass", 0.055, 3)
    rod("Spire", point(x, z, 3.48), point(x, z, 4.35), 0.051, "Brass", tip=0.018)
    for tx, tz, h in ((1.72, -1.25, 1.75), (2.4, -0.7, 1.32), (-2.38, 0.13, 1.65)):
        tree(tx, tz, h, "Leaf")


def dublin():
    terrain(0.35, -0.08, 5.55, 3.80, 2.4, 0.92, "Meadow")
    custom_house(2.93, -1.24)
    oval("Western hill", -2.10, -2.39, -0.1, (1.86, 1.07, 1.08), "Hill")
    oval("Eastern hill", 1.09, -2.89, -0.13, (1.48, 0.84, 1.45), "Leaf")
    oval("Low knoll", 3.76, 1.52, -0.09, (0.83, 0.84, 0.59), "Hill")
    tree(1.09, -2.89, 1.61, "Moss", 1.25)
    tree(-2.40, -2.42, 1.29, "Hill", 0.93)
    tree(3.81, 1.56, 1.39, "Leaf", 0.48)


def export_islands():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    PALETTE.update(ISLAND_COLOURS)
    sand = bytes.fromhex(ISLAND_COLOURS["Limestone"])
    for provider, hex_colour in PROVIDER_COLOURS.items():
        PALETTE["Pad " + provider] = bytes(
            round(0.70 * c + 0.30 * s) for c, s in zip(bytes.fromhex(hex_colour), sand)
        ).hex()
    rows = island_entries()
    for name, build in (("zurich", zurich), ("frankfurt", frankfurt), ("dublin", dublin)):
        before = set(bpy.context.scene.objects)
        build()
        body = join_parts(set(bpy.context.scene.objects) - before, "landscape_" + name)
        cx, h, cz = ISLANDS[name]
        root = anchor("island_" + name, point(cx, cz, h))
        body.parent = root
        groups = {}
        for row in rows:
            if row["island"] != name:
                continue
            x, z = row["pos"][0] - cx, row["pos"][2] - cz
            yaw = row["rotY"]
            anchor(row["slot"], point(x, z, DECK_HEIGHT), (0, 0, yaw)).parent = root
            west_terrace = name == "zurich" and row["resourceId"] in ("dp-prod", "vm-app")
            groups.setdefault((row["provider"], west_terrace), []).append(
                footprint(row["asset"], x, z, yaw)
            )
        spare, island, x, z, yaw = M1
        if island == name:
            angle = math.radians(yaw)
            alternate = anchor(spare, point(x, z, 0), (0, 0, angle))
            alternate.parent = root
            alternate["asset"] = "hw_cluster"
            alternate["provider"] = "azure"
        terraces = {}
        for (provider, _), outlines in groups.items():
            terraces.setdefault(provider, []).append(provider_pad(provider, outlines))
        # The two Zurich terraces remain addressable as the same provider mesh.
        for provider, parts in terraces.items():
            join_parts(parts, "pad_" + provider).parent = root
    bpy.ops.export_scene.gltf(
        filepath=str(ENV),
        export_format="GLB",
        export_yup=True,
        export_lights=False,
        export_cameras=False,
        export_animations=False,
        export_extras=True,
    )

    # Blender requires globally unique datablock names. glTF permits the same
    # node and mesh names on different islands; publish the scoped pad contract.
    raw = ENV.read_bytes()
    length = struct.unpack_from("<I", raw, 12)[0]
    document = json.loads(raw[20 : 20 + length])
    for node in document["nodes"]:
        if node["name"].startswith("pad_"):
            node["name"] = node["name"].split(".")[0]
            document["meshes"][node["mesh"]]["name"] = node["name"]
    encoded = json.dumps(document, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 4)
    binary = raw[20 + length :]
    ENV.write_bytes(
        struct.pack("<4sIIII", b"glTF", 2, 20 + len(encoded) + len(binary), len(encoded), 0x4E4F534A)
        + encoded
        + binary
    )


def review():
    scene = studio(1680, 1140, 36)
    rows = [r for r in json.loads((MODELS / "layout.json").read_text()) if r.get("view") == "island"]
    document = gltf(ENV)
    assert not document.get("cameras") and not document.get("animations")
    nodes = document["nodes"]
    roots = [nodes[i] for i in document["scenes"][0]["nodes"]]
    assert {n["name"] for n in roots} == {"island_" + name for name in ISLANDS}
    for root in roots:
        island = root["name"][7:]
        pads = [nodes[i]["name"] for i in root["children"] if nodes[i]["name"].startswith("pad_")]
        assert sorted(pads) == sorted({"pad_" + r["provider"] for r in rows if r["island"] == island})
    bpy.ops.import_scene.gltf(filepath=str(ENV))
    for row in rows:
        slot = scene.objects[row["slot"]]
        x, h, z = row["pos"]
        pos = Vector(point(x, z, h))
        assert slot.type == "EMPTY" and slot.parent.name == "island_" + row["island"]
        assert (slot.matrix_world.translation - pos).length < 1e-4 and abs(
            slot.matrix_world.to_euler().z - row["rotY"]
        ) < 1e-5
        for sx, sz in footprint(row["asset"], x, z, row["rotY"]):
            hit, where, _, _, obj, _ = scene.ray_cast(
                bpy.context.evaluated_depsgraph_get(),
                Vector(point(sx, sz, h + 0.02)),
                Vector((0, 0, -1)),
                distance=0.04,
            )
            assert (
                hit and obj.name.split(".")[0] == "pad_" + row["provider"] and abs(where.z - h) < 1e-4
            ), row["id"]
    assert len(rows) == len({r["slot"] for r in rows}) == 17
    assert scene.objects[M1[0]].parent.name == "island_zurich"
    for row in rows:
        obj = load_model(MODELS, row["asset"])
        x, h, z = row["pos"]
        obj.location, obj.rotation_euler.z = point(x, z, h), row["rotY"]
        band = next(o for o in obj.children_recursive if o.name.split(".")[0] == "provider")
        PALETTE[row["provider"]] = PROVIDER_COLOURS[row["provider"]]
        band.data.materials[0] = material(row["provider"])
    bpy.context.view_layer.update()
    eye = Vector((1, -1, 1)).normalized()
    view = eye.to_track_quat("Z", "Y")
    right, up = view @ Vector((1, 0, 0)), view @ Vector((0, 1, 0))
    pts = [
        o.matrix_world @ v.co
        for o in scene.objects
        if o.type == "MESH" and not o.is_shadow_catcher
        for v in o.data.vertices
    ]
    (left, rightmost), (bottom, top), (_, far) = [
        (min(p.dot(a) for p in pts), max(p.dot(a) for p in pts)) for a in (right, up, eye)
    ]
    scene.camera.location = (
        right * ((rightmost + left) / 2) + up * ((top + bottom) / 2) + eye * (far + 35)
    )
    scene.camera.rotation_euler = view.to_euler()
    scene.camera.data.ortho_scale = 1.16 * max(rightmost - left, (top - bottom) * 1680 / 1140)
    scene.render.image_settings.color_mode = "RGB"
    PREVIEWS.mkdir(exist_ok=True)
    save(scene, PREVIEWS / "islands.png")
    print(f"Verified {len(rows)} physical attachments on {len(ISLANDS)} islands.")


def hardware_contact_sheet():
    types = ("compute", "cluster", "database", "storage", "gpu")
    scene = studio(1800, 640, 12.8)
    ink = material("Graphite")
    floor_up = Vector((UP.x, UP.y, 0)) / math.sin(ELEVATION) ** 2
    for i, kind in enumerate(types):
        model = load_model(MODELS, "hw_" + kind)
        (left, right), (bottom, _) = extents(model.children_recursive)
        x = (i - 2) * 2.43
        model.location = RIGHT * (x - (left + right) / 2) + floor_up * (-0.94 - bottom)
        caption(kind.upper(), x, -1.28, ink)
    save(scene, PREVIEWS / "hardware_contact_sheet.png")


def main():
    export_islands()
    write_layout(build_layout())
    review()
    hardware_contact_sheet()


if __name__ == "__main__":
    run_headless(main)
