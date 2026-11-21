"""Verify the delivered GLB and JSON together; render with linked kit collections."""

import json
import math
from collections import Counter, defaultdict

import bpy
from mathutils import Matrix, Vector, Quaternion
import bmesh

from env.office import ENV, EYE, triangles
from env.layout import INFRA
from env.plan import DEPTS, ROOMS, MODELS, PREVIEWS, decor_items, gltf, local_children
from kit.common import PALETTE, material
from previews import studio, save


PIXELS_PER_METRE = 58


def frame(scene, width, height):
    # Square pixels and a fixed model-space scale; larger rooms get larger canvases.
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
    scene.render.resolution_x = math.ceil(width * PIXELS_PER_METRE)
    scene.render.resolution_y = math.ceil(height * PIXELS_PER_METRE)
    scene.camera.data.ortho_scale = (
        max(scene.render.resolution_x, scene.render.resolution_y) / PIXELS_PER_METRE
    )


def render_plan(scene):
    cam = scene.camera
    cam.location = (1.55, 0, 68)
    cam.rotation_euler = (0, 0, 0)
    frame(scene, 48, 33)
    labels = []
    for room, (w, n, e, s, *_) in ROOMS.items():
        x, z = (w + e) / 2, -1.10 if n == 0 else 29.12
        if room == "hr":
            x, z = 44.10, (n + s) / 2
        text = bpy.data.curves.new(room + " plan caption", "FONT")
        label = room.upper() if room in ("hr", "it") else room.title()
        text.body = f"{label}  ·  {(e - w) * (s - n):g} m²"
        text.size = 0.54
        text.align_x = text.align_y = "CENTER"
        text.materials.append(material("Graphite"))
        obj = bpy.data.objects.new(text.name, text)
        scene.collection.objects.link(obj)
        obj.location = (x - 21, 14 - z, 0)
        obj.visible_shadow = False
        labels.append(obj)
    save(scene, PREVIEWS / "office_plan.png")
    for obj in labels:
        curve = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.curves.remove(curve)


def section(source, limits, cap):
    """Cut a temporary render copy on the four room boundaries in world space."""
    bm = bmesh.new()
    bm.from_mesh(source.data)
    bm.transform(source.matrix_world)
    if cap:
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.00001)
    w, n, e, s = limits
    for point, normal in [
        ((w - 21, 0, 0), (1, 0, 0)),
        ((e - 21, 0, 0), (-1, 0, 0)),
        ((0, 14 - n, 0), (0, -1, 0)),
        ((0, 14 - s, 0), (0, 1, 0)),
    ]:
        result = bmesh.ops.bisect_plane(
            bm,
            geom=[*bm.verts, *bm.edges, *bm.faces],
            plane_co=point,
            plane_no=normal,
            dist=0.000001,
            clear_inner=True,
        )
        if cap:
            edges = [v for v in result["geom_cut"] if isinstance(v, bmesh.types.BMEdge) and v.is_boundary]
            if edges:
                bmesh.ops.holes_fill(bm, edges=edges)
    data = bpy.data.meshes.new("Room section")
    for material_slot in source.data.materials:
        data.materials.append(material_slot)
    bm.to_mesh(data)
    bm.free()
    obj = bpy.data.objects.new("Room section", data)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def verify_and_render():
    data = json.loads((MODELS / "layout.json").read_text())
    data = [row for row in data if row.get("view", "office") == "office"]
    shell = gltf(ENV)
    nodes = {n["name"]: n for n in shell["nodes"]}
    for room in DEPTS:
        assert "mesh" in nodes["floor_" + room] and "mesh" in nodes["accent_wall_" + room]
        assert "mesh" not in nodes["label_" + room]
    assert all("mesh" not in nodes[n] for n in ("entrance", "camera_home"))
    assert not shell.get("animations") and not shell.get("cameras")
    scene = studio(1840, 1290, nodes["camera_home"]["extras"]["orthoWidth"])
    frame(scene, nodes["camera_home"]["extras"]["orthoWidth"], 34)
    scene.cycles.samples = 16
    scene.render.image_settings.color_mode = "RGB"
    mat_room = {}
    for room in DEPTS:
        name = "Preview fabric " + room
        PALETTE[name] = ROOMS[room][-1]
        mat_room[room] = material(name)
    PALETTE.update({"Working display": "668985", "Dormant badge": "85908E"})
    catcher = next(o for o in scene.objects if o.type == "MESH" and o.is_shadow_catcher)
    catcher.location.z = -0.617
    bpy.ops.import_scene.gltf(filepath=str(ENV))
    cam = scene.camera
    home = scene.objects["camera_home"]
    camera_rotation = home.matrix_world.to_3x3().normalized() @ Matrix.Rotation(math.pi / 2, 3, "X")
    cam.location = home.matrix_world.translation
    cam.rotation_euler = camera_rotation.to_euler()
    # The actual exported empty must be directly usable by a Three camera.
    q = nodes["camera_home"]["rotation"]
    direction = Quaternion((q[3], *q[:3])) @ Vector((0, 0, -1))
    position = Vector(nodes["camera_home"]["translation"])
    assert all(abs(abs(v) - 1 / math.sqrt(3)) < 1e-5 for v in direction)
    assert direction.dot((Vector((0, 0.25, 0)) - position).normalized()) > 0.9999
    prototypes = {}
    counts = defaultdict(Counter)
    static_counts = Counter()
    room_tri = Counter()
    kit_tris = {}
    for o in decor_items():
        static_counts[o["asset"]] += 1

    def instance(row, room, owner, active=False):
        asset = row["asset"]
        variant = (
            room
            if asset == "chair_task"
            else active
            if asset in ("monitor_27", "monitor_dual", "licence_puck")
            else None
        )
        key = (asset, variant)
        if key not in prototypes:
            path = MODELS / f"kit_{asset}_v1.glb"
            before = set(scene.objects)
            bpy.ops.import_scene.gltf(filepath=str(path))
            group = bpy.data.collections.new(f"{asset}.{variant}")
            for o in set(scene.objects) - before:
                if o.type == "MESH":
                    for slot in o.material_slots:
                        name = slot.material.name.split(".")[0]
                        if asset == "chair_task" and name == "Accent":
                            slot.material = mat_room[room]
                        if asset.startswith("monitor_") and active and name == "Screen":
                            slot.material = material("Working display")
                        if asset == "licence_puck" and not active and name == "LED":
                            slot.material = material("Dormant badge")
                group.objects.link(o)
                for c in list(o.users_collection):
                    if c != group:
                        c.objects.unlink(o)
            prototypes[key] = group
            kit_tris[asset] = triangles(gltf(path))
        obj = bpy.data.objects.new(owner, None)
        scene.collection.objects.link(obj)
        obj["room"] = room
        obj.instance_type = "COLLECTION"
        obj.instance_collection = prototypes[key]
        x, y, z = row["pos"]
        obj.location = (x, -z, y)
        obj.rotation_euler.z = row["rotY"]
        counts[room][asset] += 1
        room_tri[room] += kit_tris[asset]

    for row in data:
        instance(row, row["room"], row["id"], row.get("active", False))
        for child in local_children(row):
            instance(child, row["room"], row["id"] + "/" + child["asset"], row.get("active", False))
    static_tri = triangles(shell)
    total = static_tri + sum(room_tri.values())
    # Count each evaluated render instance, including linked copies of the same mesh.
    bpy.context.view_layer.update()
    observed = 0
    mesh_counts = {}
    for item in bpy.context.evaluated_depsgraph_get().object_instances:
        obj = item.object
        if obj.type == "MESH" and not obj.is_shadow_catcher:
            mesh = obj.data
            if mesh not in mesh_counts:
                mesh.calc_loop_triangles()
                mesh_counts[mesh] = len(mesh.loop_triangles)
            observed += mesh_counts[mesh]
    if observed != total or total > 300000:
        raise ValueError(f"Office triangles: evaluated {observed:,}, from GLBs {total:,}, target 300,000")
    assets = sum(counts.values(), Counter())
    lines = ["Asset                         Layout   Static decor"]
    lines += [
        f"{k:26} {assets[k]:8} {static_counts[k]:14}"
        for k in sorted(assets.keys() | static_counts.keys())
    ]
    lines += ["", "Room                   Stable IDs   Layout instances   Static decor"]
    for room in (*ROOMS, "corridor"):
        lines.append(
            f"{room:20} {sum(r['room'] == room for r in data):12} {sum(counts[room].values()):18} "
            f"{sum(1 for r in decor_items() if r['room'] == room):14}"
        )
    infrastructure = {id for groups in INFRA.values() for ids in groups.values() for id in ids}
    lines += [
        "",
        "Room             Area m²   Desks   Pucks  Reports  SaaS   Infra  AI apps  Agents  Windows",
    ]
    for room, (w, n, e, s, *_) in ROOMS.items():
        ids = [r["id"] for r in data if r["room"] == room]
        infra = sum(id in infrastructure for id in ids)
        lines.append(
            f"{room:15} {(e - w) * (s - n):8.1f} {counts[room]['desk_bench']:7} "
            f"{counts[room]['licence_puck']:7} {sum(id.startswith('pbi-') and id[4:].isdigit() for id in ids):8} "
            f"{sum(id.startswith('saas:') for id in ids):5} {infra:7} "
            f"{sum(id.startswith('ai-') for id in ids):8} {sum(id.startswith('agent:') for id in ids):7} "
            f"{sum(id.startswith('window:') for id in ids):8}"
        )
    lines += [
        "",
        f"Static environment: {static_tri:,} triangles",
        f"Layout instances: {sum(room_tri.values()):,} triangles",
        f"Full scene: {total:,} / 300,000 triangles ({300000 - total:,} available)",
    ]
    report = "\n".join(lines) + "\n"
    print(report, flush=True)
    PREVIEWS.mkdir(exist_ok=True)
    (PREVIEWS / "office_counts.txt").write_text(report)
    save(scene, PREVIEWS / "office_overview.png")

    render_plan(scene)
    shells = [
        scene.objects[name]
        for name in (
            "architecture",
            "Plinth foot",
            "Cut timber",
            "Plywood lamina",
            "Edge reveal",
            "Subfloor",
        )
    ]
    for obj in shells:
        obj.hide_render = True
    scene.cycles.samples = 20
    for room, (w, n, e, s, *_) in ROOMS.items():
        for obj in scene.objects:
            if obj.get("room"):
                obj.hide_render = obj["room"] != room
            elif obj.name.startswith(("floor_", "accent_wall_")):
                obj.hide_render = obj.name not in ("floor_" + room, "accent_wall_" + room)
        eye = EYE
        rotation = camera_rotation
        right, up = rotation @ Vector((1, 0, 0)), rotation @ Vector((0, 1, 0))
        cam.rotation_euler = rotation.to_euler()
        pad = 0.106
        sections = [
            section(o, (w - pad, n - pad, e + pad, s + pad), o.name != "architecture") for o in shells
        ]
        pts = [Vector((x - 21, 14 - z, y)) for x in (w, e) for z in (n, s) for y in (-0.62, 2.0)]
        ranges = [(min(p.dot(axis) for p in pts), max(p.dot(axis) for p in pts)) for axis in (right, up)]
        (l, r), (b, t) = ranges
        cam.location = eye * 68 + right * ((l + r) / 2) + up * ((b + t) / 2)
        frame(scene, r - l + 1.8, t - b + 1.8)
        save(scene, PREVIEWS / f"room_{room}.png")
        for obj in sections:
            data_block = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.meshes.remove(data_block)
