"""Blender uses metres, Z up and -Y forward. glTF export maps these to Y up, +Z forward."""
from math import cos, pi, sin

import bpy
from mathutils import Matrix, Vector

PALETTE = {
    "Oak": "E6B980", "Walnut": "94694E", "Plaster": "F6E9D6",
    "Concrete": "8D9490", "Graphite": "37454A", "Felt": "C6A788",
    "Glass": "A9CBC1", "Leaf": "86AF82", "Moss": "597F69",
    "Screen": "30363B", "LED": "F3BF66", "Accent": "CECFCB",
    "Clay": "C77F62", "Enamel": "52857F", "Brass": "BD9559",
}


def material(name):
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    rgb = bytes.fromhex(PALETTE[name])
    srgb = [channel / 255 for channel in rgb]
    rgba = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in srgb] + [1]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = rgba
    shader.inputs["Roughness"].default_value = 0.85
    if name == "Glass":
        shader.inputs["Alpha"].default_value = .29
        shader.inputs["Roughness"].default_value = .40
    if name == "LED":
        shader.inputs["Emission Color"].default_value = rgba
        shader.inputs["Emission Strength"].default_value = .28
    mat.diffuse_color = rgba
    return mat


def mesh(name, vertices, faces, finish, smooth=False):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    data.materials.append(material(finish))
    for face in data.polygons:
        face.use_smooth = smooth
    return obj


def bevel(obj, radius, segments):
    mod = obj.modifiers.new("Edge radius", "BEVEL")
    mod.width = radius
    mod.segments = segments
    mod.harden_normals = True
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


def box(name, center, size, finish, radius=0.03, segments=2):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.data.transform(Matrix.Diagonal((*size, 1)))
    obj.data.materials.append(material(finish))
    if radius:
        bevel(obj, radius, segments)
    return obj


def loft(name, rings, finish, sides=20):
    """Closed stack of horizontal ellipses: each row is (x, y, z, rx, ry)."""
    verts = [(x + rx*cos(2*pi*j/sides), y + ry*sin(2*pi*j/sides), z)
             for x, y, z, rx, ry in rings for j in range(sides)]
    faces = [tuple(reversed(range(sides)))]
    for i in range(len(rings)-1):
        for j in range(sides):
            a, b = i*sides+j, i*sides+(j+1)%sides
            faces.append((a, b, b+sides, a+sides))
    faces.append(tuple(range(len(verts)-sides, len(verts))))
    obj = mesh(name, verts, faces, finish, smooth=True)
    for cap in (obj.data.polygons[0], obj.data.polygons[-1]):
        cap.use_smooth = False
    return obj


def turned(name, profile, finish, sides=24):
    return loft(name, [(0, 0, z, r, r) for z, r in profile], finish, sides)


def rod(name, start, end, radius, finish, sides=12, tip=None):
    direction = Vector(end) - Vector(start)
    obj = turned(name, [(0, radius), (direction.length, radius if tip is None else tip)], finish, sides)
    obj.location = start
    obj.rotation_euler = direction.to_track_quat('Z', 'Y').to_euler()
    return obj


def anchor(name, location, rotation=(0, 0, 0)):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_size = .025
    obj.location = location
    obj.rotation_euler = rotation
    bpy.context.collection.objects.link(obj)
    return obj


def slab(name, center, size, finish, radius=.035, steps=3):
    """Extruded round rectangle with independent plan radius and slab thickness."""
    w, d, h = size
    r = min(radius, w/2, d/2)*.999
    rim = []
    for i, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
        for j in range(steps+1):
            a = (i+j/steps)*pi/2
            rim.append((sx*(w/2-r)+r*cos(a), sy*(d/2-r)+r*sin(a)))
    n = len(rim)
    verts = [(x,y,z) for z in (-h/2,h/2) for x,y in rim]
    faces = [tuple(reversed(range(n))), tuple(range(n,2*n))]
    faces.extend((j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n))
    obj = mesh(name, verts, faces, finish)
    obj.location = center
    return obj


def panel(name, center, width, height, thickness, finish, radius=.032, steps=3):
    obj = slab(name, center, (width,height,thickness), finish, radius, steps)
    obj.rotation_euler.x = pi/2
    return obj


def screen_panel(center, width, height, depth, *, tilt=0, suffix=""):
    """Framed panel with a front-facing, independently addressable display."""
    rotation = Matrix.Rotation(tilt, 3, 'X')
    c = Vector(center)
    bezel = panel("Bezel", c, width, height, depth, "Graphite", .035)
    bezel.rotation_euler.x += tilt
    inset = min(width,height)*.065
    front = c + rotation @ Vector((0,-depth/2-.001,0))
    display = panel("screen"+suffix, front, width-inset, height-inset, .002, "Screen", .018)
    display.rotation_euler.x += tilt
    anchor("anchor_screen"+suffix, front + rotation @ Vector((0,-.001,0)), (tilt,0,0))


def led(center, width, height=.026):
    panel("status_led", center, width, height, .008, "LED", height/2)
    anchor("anchor_led", (center[0],center[1]-.004,center[2]))


def table(width, depth, height, finish="Oak"):
    box("Slab", (0,0,height-.048), (width,depth,.096), finish, .038, 3)
    for side in (-1,1):
        box("End support", (side*width*.32,0,(height-.09)/2),
            (.12,depth*.70,height-.09), "Plaster", .035)


def lounge(width, depth, seats):
    box("Timber base", (0,.025,.13), (width-.16,depth-.13,.26), "Walnut", .035)
    box("Back bolster", (0,depth*.36,.515), (width-.026,.22,.57), "Felt", .095, 4)
    for side in (-1,1):
        box("Arm bolster", (side*(width/2-.07),0,.39), (.14,depth,.40), "Felt", .067, 4)
    span=(width-.24)/seats
    for i in range(seats):
        box("Seat cushion", ((i-(seats-1)/2)*span,-.065,.31),
            (span-.013,depth-.21,.20), "Felt", .071, 4)


def export_glb(path, size, interactive, budget):
    """Bake the nominal design into a given (width, depth, height) envelope."""
    groups = {key: [] for key in ("body", *interactive)}
    points = []
    anchors = []
    pivots = {}
    bpy.context.view_layer.update()
    for obj in list(bpy.context.scene.objects):
        if obj.type == "EMPTY" and obj.name.startswith("anchor_"):
            anchors.append(obj)
            continue
        if obj.type != "MESH":
            raise ValueError(f"Unexpected scene object {obj.name}")
        key = obj.name.split(".")[0]
        if key in ("fan", "belt") and key == obj.name:
            pivots[key] = obj.matrix_world.translation.copy()
        obj.data.transform(obj.matrix_world, shape_keys=True)
        obj.matrix_world = Matrix.Identity(4)
        points.extend(v.co.copy() for v in obj.data.vertices)
        groups[key if key in interactive else "body"].append(obj)

    lo, hi = ([func(p[i] for p in points) for i in range(3)] for func in (min, max))
    origin = Vector(((lo[0]+hi[0])/2, (lo[1]+hi[1])/2, lo[2]))
    scale = Matrix.Diagonal(tuple(size[i]/(hi[i]-lo[i]) for i in range(3)) + (1,))
    transform = scale @ Matrix.Translation(-origin)
    for obj in anchors:
        obj.location = transform @ obj.location
    triangles = 0
    for name, parts in groups.items():
        if not parts:
            raise ValueError(f"{path.stem} missing {name}")
        bpy.ops.object.select_all(action='DESELECT')
        for obj in parts:
            obj.select_set(True)
        obj = parts[0]
        bpy.context.view_layer.objects.active = obj
        if len(parts) > 1:
            bpy.ops.object.join()
        obj.name = obj.data.name = name
        pivot = transform @ pivots[name] if name in pivots else Vector((0,0,0))
        obj.data.transform(Matrix.Translation(-pivot) @ transform, shape_keys=True)
        obj.location = pivot
        obj.data.calc_loop_triangles()
        triangles += len(obj.data.loop_triangles)
    if triangles > budget:
        raise ValueError(f"{path.stem}: {triangles} triangles exceeds {budget}")
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', export_yup=True,
                              export_cameras=False, export_lights=False, export_animations=False)
    return triangles
