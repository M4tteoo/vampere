import math
import bpy
from .common import PALETTE, material

SIZE = (7.02, 2.97, 3.28)
BUDGET = 12000
PARTS = ()


def build():
    PALETTE["Cloud"] = "EEF2F6"
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
    parts = []
    for x, z, h, rx, rz, rh in lobes:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, location=(x, -z, h))
        obj = bpy.context.object
        obj.scale = (rx, rz, rh)
        obj.data.materials.append(material("Cloud"))
        parts.append(obj)
    for obj in parts:
        obj.select_set(True)
    cloud = parts[0]
    bpy.context.view_layer.objects.active = cloud
    bpy.ops.object.join()
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
