"""Render the exported models at a consistent 35-degree orthographic angle."""
from math import ceil, cos, radians, sin

import bpy
from mathutils import Vector

ELEVATION = radians(35)
EYE = Vector((.62*cos(ELEVATION), -.78460181*cos(ELEVATION), sin(ELEVATION))).normalized()
VIEW = EYE.to_track_quat('Z','Y')
RIGHT = VIEW @ Vector((1,0,0))
UP = VIEW @ Vector((0,1,0))
ROWS = (
    "desk_bench chair_task monitor_27 monitor_dual licence_puck approval_desk",
    "console_kiosk rack_compact storage_cabinet wall_screen wall_screen_large m365_totem",
    "text_machine agent_robot ai_orb quote_device saas_terminal tablet_stand",
    "wall_calendar project_wall pinboard whiteboard phone_booth creative_table",
    "cabinet_tall armchair sofa_2 board_table_10 reception_desk coffee_bar",
    "bench plant_small plant_large server_rack_42u gpu_server storage_array",
)


def studio(width, height, span):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'Standard'
    scene.render.film_transparent = True
    scene.world = bpy.data.worlds.new("Studio fill")
    scene.world.use_nodes = True
    bg = next(n for n in scene.world.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs['Color'].default_value = (.88,.91,1,1)
    bg.inputs['Strength'].default_value = .68
    bpy.ops.object.light_add(type='SUN')
    sun = bpy.context.object
    sun.rotation_euler = Vector((-.48,-.62,1.7)).to_track_quat('Z','Y').to_euler()
    sun.data.energy = 1.55
    sun.data.angle = radians(24)
    sun.data.color = (1,.929,.84)
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0,0,-.001))
    bpy.context.object.is_shadow_catcher = True
    bpy.ops.object.camera_add(location=EYE*32)
    scene.camera = bpy.context.object
    scene.camera.rotation_euler = VIEW.to_euler()
    scene.camera.data.type = 'ORTHO'
    scene.camera.data.ortho_scale = span
    # Composite real contact shadows over the exact sRGB paper colour.
    tree = bpy.data.node_groups.new("Studio paper", 'CompositorNodeTree')
    scene.compositing_node_group = tree
    tree.interface.new_socket(name="Image",in_out='OUTPUT',socket_type='NodeSocketColor')
    output = tree.nodes.new('NodeGroupOutput')
    render = tree.nodes.new('CompositorNodeRLayers')
    over = tree.nodes.new('CompositorNodeAlphaOver')
    over.inputs['Background'].default_value = [((v/255+.055)/1.055)**2.4 for v in (247,243,238)]+[1]
    tree.links.new(render.outputs['Image'], over.inputs['Foreground'])
    tree.links.new(over.outputs[0],output.inputs[0])
    return scene


def load_model(folder, name):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(folder/f"kit_{name}_v1.glb"))
    objects = set(bpy.context.scene.objects)-before
    root = bpy.data.objects.new(name,None)
    bpy.context.collection.objects.link(root)
    for obj in objects:
        if obj.parent is None:
            obj.parent = root
    bpy.context.view_layer.update()
    return root


def extents(objects):
    points = [o.matrix_world @ v.co for o in objects if o.type == 'MESH' for v in o.data.vertices]
    axes = [[p.dot(axis) for p in points] for axis in (RIGHT,UP)]
    return [(min(values), max(values)) for values in axes]


def caption(name, x, y, ink):
    font = bpy.data.curves.new(name,'FONT')
    font.body = name
    font.size = .114
    font.align_x = 'CENTER'
    font.align_y = 'CENTER'
    font.materials.append(ink)
    obj = bpy.data.objects.new(name,font)
    bpy.context.collection.objects.link(obj)
    obj.location = RIGHT*x+UP*y+EYE*18
    obj.rotation_euler = VIEW.to_euler()
    obj.visible_shadow = obj.visible_diffuse = obj.visible_glossy = False


def save(scene, path):
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def render_previews(folder, names, destination):
    destination.mkdir(exist_ok=True)
    ordered = [n for row in ROWS for n in row.split() if n in names]
    ordered.extend(sorted(set(names)-set(ordered)))
    cols = 6
    rows = ceil(len(ordered)/cols)
    pitch_x, pitch_y = 2.0, 1.66
    scene = studio(cols*360, round(rows*360*pitch_y/pitch_x), cols*pitch_x)
    ink = bpy.data.materials.new("Catalogue ink")
    ink.use_nodes = True
    shader = next(n for n in ink.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    shader.inputs['Base Color'].default_value = (.045,.057,.062,1)
    ground_up = Vector((UP.x,UP.y,0))/sin(ELEVATION)**2
    for i,name in enumerate(ordered):
        root = load_model(folder,name)
        (left,right),(bottom,top) = extents(root.children_recursive)
        factor = min(1.62/(right-left),1.19/(top-bottom))
        x = (i%cols-(cols-1)/2)*pitch_x
        y = ((rows-1)/2-i//cols)*pitch_y
        root.scale *= factor
        root.location = RIGHT*(x-factor*(left+right)/2)+ground_up*(y+.105-factor*(top+bottom)/2)
        caption(name,x,y-.657,ink)
    save(scene,destination/'kit_contact_sheet.png')

    scene = studio(1280,960,2.12)
    desk = load_model(folder,'desk_bench')
    tower = load_model(folder,'pc_tower')
    tower.location = (.40,.13,0)
    screen = load_model(folder,'monitor_27')
    screen.location = (0,.216,.74)
    chair = load_model(folder,'chair_task')
    chair.rotation_euler.z = radians(180)
    chair.location = (0,-.71,0)
    bpy.context.view_layer.update()
    (left,right),(bottom,top) = extents(o for root in (desk,screen,chair,tower) for o in root.children_recursive)
    scene.camera.location += RIGHT*((left+right)/2) + UP*((bottom+top)/2)
    scene.camera.data.ortho_scale = 1.18*max(right-left,(top-bottom)*1280/960)
    save(scene,destination/'workstation_closeup.png')
