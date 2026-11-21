"""Build the §5 environment and render the exported GLB with its physical hardware."""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from env.island_layout import DECK_HEIGHT, EU_SERVICES, ISLANDS, M1, equipment_terraces
from env.layout import build_layout, write_layout
from env.office import join_parts, run_headless
from env.plan import MODELS, PREVIEWS, gltf
from kit.common import PALETTE, anchor, box, loft, material, mesh, rod, slab
from previews import load_model, save, studio

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
    "Cloud": "EEF2F6",
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


def pad(name, x, z, w, d, angle=0):
    obj = slab(
        name, point(x, z, DECK_HEIGHT / 2 - 0.012), (w, d, DECK_HEIGHT + 0.024), "Limestone", 0.22, 6
    )
    obj.rotation_euler.z = math.radians(angle)


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


def lake():
    # An open shoreline follows the actual southern rim of the Zurich terrain.
    n = 44
    rings = [[], [], []]
    for i in range(n + 1):
        q = i / n
        t = 0.07 * TAU + 0.39 * TAU * q
        x, z = outline(t, 4.95, 3.6, 0.4)
        wave = math.sin(math.pi * q) ** 0.9
        for ring, inset in zip(rings, (0, 0.32, 0.37)):
            ring.append(point(x * (0.974 - inset * wave), z * (0.974 - inset * wave), 0.014))
    for a, b, finish in ((rings[0], rings[1], "Lake"), (rings[1], rings[2], "Shallows")):
        mesh("Lake edge", a + b, [(i, n + 1 + i, n + 2 + i, i + 1) for i in range(n)], finish)
    for x, z, w in ((-0.5, 3.05, 0.52), (0.30, 3.04, 0.29), (1.28, 2.68, 0.38)):
        oval("Reflection", x, z, 0.023, (w, 0.035, 0.012), "Ripple")
    for i in range(6):
        slab("Jetty plank", point(-1.21, 2.36 + i * 0.135, 0.105), (0.42, 0.125, 0.085), "Oak", 0.025)
    for z in (2.4, 2.99):
        for x in (-1.37, -1.05):
            rod("Jetty pier", point(x, z, 0.006), point(x, z, 0.18), 0.029, "Walnut")


def zurich():
    terrain(0, 0, 4.95, 3.6, 0.4)
    terrain(7.55, 0.12, 2.18, 1.96, 2.3, 0.78, "Leaf")
    lake()
    slab("Hoster footbridge", point(5.28, 0.06, 0.10), (1.82, 0.68, 0.13), "Oak", 0.07)
    for x, z, h in ((-3.2, -1.96, 2.2), (-2.36, -2.36, 2.65), (1.92, -1.98, 2.6), (2.74, -1.55, 1.85)):
        tree(x, z, h, "fir")
    tree(-3.82, 0.91, 1.7, "Leaf")


def frankfurt():
    terrain(0, 0, 3.65, 2.85, 1.2, 0.94, "Hill")
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
    terrain(0, 0, 4.15, 3.12, 2.4, 0.92, "Meadow")
    oval("Western hill", -1.70, -1.58, -0.1, (1.86, 1.07, 1.08), "Hill")
    oval("Eastern hill", 0.83, -1.87, -0.13, (2.05, 1.02, 1.45), "Leaf")
    oval("Low knoll", 2.83, 0.33, -0.09, (0.92, 1.24, 0.59), "Hill")
    tree(0.65, -1.92, 1.61, "Moss", 1.25)
    tree(-2.00, -1.61, 1.29, "Hill", 0.93)
    tree(2.96, 0.26, 1.39, "Leaf", 0.48)


def eu_mixed():
    # Fuse interlocking ellipsoids into one smooth cumulus surface.
    lobes = (
        # Along the silhouette, depth, height, and the three lobe radii.
        (-2.65, 0.03, 0.02, 1.06, 0.94, 0.66),
        (-1.79, -0.08, 0.28, 1.34, 1.20, 1.02),
        (-0.63, -0.22, 0.84, 1.48, 1.30, 1.61),
        (0.76, -0.20, 0.55, 1.31, 1.16, 1.22),
        (2.08, 0.00, 0.20, 1.33, 1.12, 0.93),
        (0.01, 0.48, -0.04, 2.23, 1.03, 0.83),
        (1.30, 0.40, -0.03, 1.06, 0.96, 0.79),
    )
    parts = [oval("Cloud lobe", x, z, h, (rx, rz, rh), "Cloud") for x, z, h, rx, rz, rh in lobes]
    cloud = join_parts(parts, "landscape_eu-mixed")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    cloud.data.remesh_voxel_size = 0.085
    bpy.ops.object.voxel_remesh()
    soften = cloud.modifiers.new("Blend lobes", "SMOOTH")
    soften.factor, soften.iterations = 0.95, 18
    bpy.ops.object.modifier_apply(modifier=soften.name)
    simplify = cloud.modifiers.new("Simplify surface", "DECIMATE")
    simplify.ratio = 0.28
    bpy.ops.object.modifier_apply(modifier=simplify.name)
    for face in cloud.data.polygons:
        face.use_smooth = True
    # The lobes run along world X, the descending 30° diagonal in the isometric preview.
    cloud.shape_key_add(name="Basis")
    billow = cloud.shape_key_add(name="Billow")
    stretch = cloud.shape_key_add(name="Stretch")
    for v in cloud.data.vertices:
        x, y, h = v.co
        crown = math.exp(-(((x + 0.65) / 1.25) ** 2)) * max(h, 0)
        billow.data[v.index].co = (x - 0.10 * crown, y * 1.10, h + 0.30 * crown)
        stretch.data[v.index].co = (1.18 * x + 0.12 * h, 0.94 * y, 0.88 * h)
    for i, service in enumerate(EU_SERVICES):
        t = TAU * i / len(EU_SERVICES)
        anchor("slot_" + service, point(2.2 * math.cos(t), 1.34 * math.sin(t), 0.18))


def export_islands():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    PALETTE.update(ISLAND_COLOURS)
    for name, build in (
        ("zurich", zurich),
        ("frankfurt", frankfurt),
        ("dublin", dublin),
        ("eu-mixed", eu_mixed),
    ):
        before = set(bpy.context.scene.objects)
        build()
        for tx, tz, w, d, yaw, slots in equipment_terraces(name):
            pad("Equipment terrace", tx, tz, w, d, yaw)
            for resource, _, x, z, angle, _ in slots:
                anchor("slot_" + resource, point(x, z, DECK_HEIGHT), (0, 0, math.radians(angle)))
        spare, island, x, z, angle = M1
        if name == island:
            anchor(spare, point(x, z, 0), (0, 0, math.radians(angle)))
        objects = set(bpy.context.scene.objects) - before
        body = join_parts([o for o in objects if o.type == "MESH"], "landscape_" + name)
        root = anchor("island_" + name, (0, 0, 0))
        for obj in [
            body,
            *(o for o in bpy.context.scene.objects if o.name.startswith("slot_") and o.parent is None),
        ]:
            obj.parent = root
        x, h, z = ISLANDS[name]
        root.location = point(x, z, h)
    bpy.ops.export_scene.gltf(
        filepath=str(ENV),
        export_format="GLB",
        export_yup=True,
        export_lights=False,
        export_cameras=False,
        export_animations=False,
    )


def review():
    scene = studio(1680, 1140, 36)
    rows = [r for r in json.loads((MODELS / "layout.json").read_text()) if r.get("view") == "island"]
    document = gltf(ENV)
    assert (
        len(document["meshes"]) == 4 and not document.get("cameras") and not document.get("animations")
    )
    cloud = next(m for m in document["meshes"] if m["name"] == "landscape_eu-mixed")
    assert cloud["extras"]["targetNames"] == ["Billow", "Stretch"]
    bpy.ops.import_scene.gltf(filepath=str(ENV))
    for row in rows:
        slot = scene.objects[row["slot"]]
        x, h, z = row["pos"]
        pos = Vector(point(x, z, h))
        assert slot.type == "EMPTY" and slot.parent.name == "island_" + row["island"]
        assert (slot.matrix_world.translation - pos).length < 1e-4, row["id"]
        assert abs(slot.matrix_world.to_euler().z - row["rotY"]) < 1e-5, row["id"]
        obj = load_model(MODELS, row["asset"])
        obj.location, obj.rotation_euler.z = pos, row["rotY"]
    assert len(rows) == len({r["slot"] for r in rows}) == 17
    assert scene.objects[M1[0]].parent.name == "island_zurich"
    assert all(scene.objects["slot_" + s].parent.name == "island_eu-mixed" for s in EU_SERVICES)
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


def main():
    export_islands()
    write_layout(build_layout())
    review()


if __name__ == "__main__":
    run_headless(main)
