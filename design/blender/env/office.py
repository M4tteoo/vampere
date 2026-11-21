"""Static cutaway office. Run with Blender -b -P design/blender/env/office.py."""

from math import ceil, radians
from pathlib import Path
import sys
import traceback

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
from kit.common import PALETTE, anchor, box, mesh, slab
from env.plan import (
    ROOMS,
    CORRIDOR,
    GALLERY,
    DISPLAY_BAYS,
    EAST_DISPLAY_BAY,
    frontage,
    DEPTS,
    MODELS,
    COLUMNS,
    DIVIDERS,
    DOOR_WIDTH,
    EXTRA_SIZES,
    decor_items,
    return_width,
)
from env.layout import build_layout, write_layout

EYE = Vector((1, -1, 1)).normalized()
HOME = EYE * 68 + Vector((0, 0, 0.25))
HOME_VIEW = EYE.to_track_quat("Z", "Y")
SPAN = 53
ENV = MODELS / "env_office_v1.glb"


def xyz(x, z, y):
    return (x - 21, 14 - z, y)


def block(name, x, z, y, w, d, h, finish, bevel=0):
    return box(name, xyz(x, z, y), (w, d, h), finish, bevel, 1)


def segment(name, x1, z1, x2, z2, bottom, top, thickness, finish):
    horizontal = abs(z2 - z1) < 1e-7
    return block(
        name,
        (x1 + x2) / 2,
        (z1 + z2) / 2,
        (top + bottom) / 2,
        abs(x2 - x1) if horizontal else thickness,
        thickness if horizontal else abs(z2 - z1),
        top - bottom,
        finish,
    )


def glazing(x1, z1, x2, z2, sill, panes):
    """Steel perimeter rails, real openings and glass inset between mullions."""
    dx, dz = x2 - x1, z2 - z1
    length = abs(dx) + abs(dz)
    if sill:
        segment("Masonry sill", x1, z1, x2, z2, 0, sill, 0.20, "Plaster")
    segment("Steel sill", x1, z1, x2, z2, sill, sill + 0.042, 0.092, "Graphite")
    segment("Steel lintel", x1, z1, x2, z2, 1.148, 1.20, 0.092, "Graphite")
    for i in range(panes):
        start = (i + 0.024 * panes / length) / panes
        end = (i + 1 - 0.024 * panes / length) / panes
        segment(
            "Glazing",
            x1 + dx * start,
            z1 + dz * start,
            x1 + dx * end,
            z1 + dz * end,
            sill + 0.042,
            1.148,
            0.013,
            "Glass",
        )
    for i in range(panes + 1):
        block(
            "Mullion",
            x1 + dx * i / panes,
            z1 + dz * i / panes,
            (1.20 + sill) / 2,
            0.048,
            0.048,
            1.20 - sill,
            "Graphite",
        )


def floor(name, w, n, e, s, finish, boards=True):
    if not boards:
        return block(name, (w + e) / 2, (n + s) / 2, -0.021, e - w, s - n, 0.042, finish)
    # Staggered oak strips stay in one tintable primitive per department.
    verts, faces = [], []
    for row in range(ceil((s - n) / 0.38)):
        z = n + row * 0.38
        x = w - ((row % 3) * 1.21)
        while x < e:
            x0, x1 = max(w, x) + 0.006, min(e, x + 3.62) - 0.006
            z0, z1 = z + 0.006, min(z + 0.38, s) - 0.006
            if x1 > x0 and z1 > z0:
                i = len(verts)
                verts.extend(xyz(a, b, 0) for a, b in ((x0, z1), (x1, z1), (x1, z0), (x0, z0)))
                faces.append((i, i + 1, i + 2, i + 3))
            x += 3.62
    return mesh(name, verts, faces, finish)


def join_parts(objects, name):
    objects = sorted(objects, key=lambda obj: obj.name)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    if len(objects) > 1:
        bpy.ops.object.join()
    objects[0].name = objects[0].data.name = name
    return objects[0]


def builtins(asset):
    if asset == "meeting_chair":
        box("Upholstery", (0, 0, 0.44), (0.48, 0.47, 0.095), "Felt", 0.035, 1)
        box("Chair back", (0, 0.208, 0.64), (0.48, 0.084, 0.36), "Felt", 0.034, 1)
        for x in (-0.182, 0.182):
            for y in (-0.17, 0.17):
                box("Foot", (x, y, 0.20), (0.046, 0.047, 0.40), "Walnut", 0)
    else:
        w, d, h = EXTRA_SIZES[asset]
        box("Counter", (0, 0, h - 0.035), (w, d, 0.070), "Oak", 0.023, 1)
        for x in (-0.35 * w, 0.35 * w):
            box("Support", (x, 0, (h - 0.07) / 2), (0.094, d * 0.80, h - 0.07), "Plaster", 0.024, 1)


def furnishings():
    library = {}
    for item in decor_items():
        asset = item["asset"]
        if asset not in library:
            before = set(bpy.context.scene.objects)
            if asset in EXTRA_SIZES:
                builtins(asset)
            else:
                bpy.ops.import_scene.gltf(filepath=str(MODELS / f"kit_{asset}_v1.glb"))
            new = set(bpy.context.scene.objects) - before
            for o in list(new):
                if o.type == "EMPTY":
                    bpy.data.objects.remove(o, do_unlink=True)
                    new.remove(o)
            proto = join_parts(new, "prototype_" + asset)
            # Bake the joined mesh's source transform once before instancing.
            bpy.context.view_layer.update()
            proto.data.transform(proto.matrix_world)
            data = proto.data
            # Simplify fine bevels and hidden upholstery at architectural scale.
            if asset in (
                "plant_large",
                "plant_small",
                "sofa_2",
                "armchair",
                "cabinet_tall",
                "creative_table",
            ):
                mod = proto.modifiers.new("Diorama detail", "DECIMATE")
                mod.ratio = 0.57
                bpy.ops.object.modifier_apply(modifier=mod.name)
                data = proto.data
            library[asset] = data
            bpy.data.objects.remove(proto, do_unlink=True)
        obj = bpy.data.objects.new(item["id"], library[asset])
        bpy.context.collection.objects.link(obj)
        x, y, z = item["pos"]
        obj.location = (x, -z, y)
        obj.rotation_euler.z = item["rotY"]
        obj["room"] = item["room"]
        obj["asset"] = asset


def environment():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    PALETTE.update(
        {"Floor oak": "E6CFAC", "Floor limestone": "DAD4CA", "Cut edge": "BB8A60", "Veneer": "E6C99C"}
    )
    for r in DEPTS:
        PALETTE["Accent " + r] = ROOMS[r][5]
        PALETTE["Floor " + r] = PALETTE["Floor oak"]
    for name, w, d, base, h, material in (
        ("Plinth foot", 42.22, 28.22, -0.615, 0.095, "Walnut"),
        ("Cut timber", 42.45, 28.45, -0.52, 0.28, "Cut edge"),
        ("Plywood lamina", 42.46, 28.46, -0.24, 0.065, "Veneer"),
        ("Edge reveal", 42.43, 28.43, -0.175, 0.035, "Walnut"),
        ("Subfloor", 42.38, 28.38, -0.14, 0.135, "Veneer"),
    ):
        slab(name, (0, 0, base + h / 2), (w, d, h), material, 0.095, 3)
    for room, (w, n, e, s, door, _) in ROOMS.items():
        floor(
            "floor_" + room,
            w,
            n,
            e,
            s,
            "Floor " + room if room in DEPTS else "Floor limestone",
            room in DEPTS,
        )
        if room in DEPTS:
            wall = block(
                "accent_wall_" + room,
                w + 0.105,
                (n + s) / 2,
                0.61,
                0.012,
                s - n - 0.25,
                1.17,
                "Accent " + room,
            )
            wall.data.name = wall.name
            anchor("label_" + room, xyz((w + e) / 2, (n + s) / 2, 2.45))
    floor("floor_corridor", *CORRIDOR, "Floor limestone", False)
    floor("floor_entry_gallery", *GALLERY, "Floor limestone", False)
    before = set(bpy.context.scene.objects)
    # Opaque party walls, south facade and its entrance opening.
    segment("West facade", 0.0, 0, 0.0, 28, 0, 1.2, 0.20, "Plaster")
    for room, (w, n, e, s, *_) in ROOMS.items():
        if w and room != "reception":
            segment("Party wall", w, n, w, s if room != "hr" else 28, 0, 1.2, 0.20, "Plaster")
    gw, gn, _, gs = GALLERY
    segment("Gallery wall", gw, gn, gw, gs, 0, 1.2, 0.20, "Plaster")
    segment("Interview rear wall", ROOMS["hr"][0], gs, gw, gs, 0, 1.2, 0.20, "Plaster")
    for start, end in ((0, 38.13), (39.87, 42)):
        segment("South facade", start, 28, end, 28, 0, 1.2, 0.20, "Plaster")
    # Full-height masonry display bays alternate with real window openings.
    start = 0
    for a, b in DISPLAY_BAYS.values():
        glazing(start, 0, a, 0, 0.34, ceil((a - start) / 1.75))
        segment("Display bay", a, 0, b, 0, 0, 1.2, 0.20, "Plaster")
        start = b
    glazing(start, 0, 42, 0, 0.34, ceil((42 - start) / 1.75))
    a, b = EAST_DISPLAY_BAY
    glazing(42, 0, 42, a, 0.34, ceil(a / 1.75))
    segment("Display bay", 42, a, 42, b, 0, 1.2, 0.20, "Plaster")
    glazing(42, b, 42, 28, 0.34, ceil((28 - b) / 1.75))
    for room in ROOMS:
        w, e, z, door = frontage(room)
        left = w + return_width(room)
        if left > w:
            segment("Solid return", w, z, left, z, 0, 1.2, 0.20, "Plaster")
        for a, b in ((left, door - DOOR_WIDTH / 2), (door + DOOR_WIDTH / 2, e)):
            if b > a:
                glazing(a, z, b, z, 0, max(1, ceil((b - a) / 2.35)))
    for room, x0, z0, x1, z1 in DIVIDERS:
        glazing(x0, z0, x1, z1, 0, ceil((x1 - x0 + z1 - z0) / 1.5))
    for x, z in COLUMNS:
        block("Concrete column", x, z, 0.56, 0.31, 0.31, 1.12, "Concrete", 0.022)
        block("Capital", x, z, 1.155, 0.34, 0.34, 0.09, "Plaster", 0.018)
    join_parts(set(bpy.context.scene.objects) - before, "architecture")
    furnishings()
    anchor("entrance", xyz(39, 28, 0))
    cam = anchor("camera_home", HOME, HOME_VIEW.to_euler())
    cam["orthoWidth"] = SPAN
    # Blender's bpy camera looks down local -Z. An empty undergoes an additional
    # axis basis change on glTF export; compensate for Three's camera convention.
    cam.rotation_euler.rotate_axis("X", radians(-90))
    bpy.ops.export_scene.gltf(
        filepath=str(ENV),
        export_format="GLB",
        export_yup=True,
        export_extras=True,
        export_cameras=False,
        export_lights=False,
        export_animations=False,
    )


def triangles(g):
    return sum(
        g["accessors"][p["indices"]]["count"] // 3
        for n in g["nodes"]
        if "mesh" in n
        for p in g["meshes"][n["mesh"]]["primitives"]
    )


def main():
    layout = build_layout()
    environment()
    write_layout(layout)
    from env.review import verify_and_render

    verify_and_render()


def run_headless(build):
    # Blender -P otherwise reports uncaught script exceptions with exit code zero.
    try:
        build()
    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_headless(main)
