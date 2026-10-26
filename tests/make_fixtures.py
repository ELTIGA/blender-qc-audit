"""Build QC test fixtures: a clean room and a room with planted defects.

blender -b --factory-startup -P make_fixtures.py -- OUTDIR
"""
import math
import os
import sys

import bpy
from mathutils import Vector

out = sys.argv[sys.argv.index("--") + 1]
os.makedirs(out, exist_ok=True)


def box(name, size, loc, mat=None, coll=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat:
        o.data.materials.append(mat)
    return o


def cyl(name, r, h, loc, mat=None):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, location=loc, vertices=24)
    o = bpy.context.active_object
    o.name = name
    if mat:
        o.data.materials.append(mat)
    return o


def mat(name, rgb):
    m = bpy.data.materials.new(name)
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*rgb, 1)
    return m


def base_room():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    wood, wall, cer = mat("wood", (0.4, 0.25, 0.12)), mat("wall", (0.8, 0.8, 0.75)), mat("ceramic", (0.9, 0.9, 0.9))
    bpy.ops.mesh.primitive_plane_add(size=6, location=(0, 0, 0))
    fl = bpy.context.active_object
    fl.name = "Floor"
    fl.data.materials.append(wood)
    box("Wall_Back", (6, 0.1, 2.6), (0, 3.05, 1.3), wall)
    # table: top + 4 legs (multi-part asset)
    box("Table_Top", (1.4, 0.8, 0.04), (0, 1.0, 0.73), wood)
    for k, (x, y) in enumerate([(-0.65, 0.65), (0.65, 0.65), (-0.65, 1.35), (0.65, 1.35)]):
        box(f"Table_Leg_{k}", (0.05, 0.05, 0.71), (x, y, 0.355), wood)
    cyl("Mug", 0.04, 0.1, (0.2, 1.0, 0.75 + 0.05), cer)
    box("Chair_Seat", (0.45, 0.45, 0.05), (0, 0.2, 0.45), wood)
    for k, (x, y) in enumerate([(-0.2, 0.0), (0.2, 0.0), (-0.2, 0.4), (0.2, 0.4)]):
        box(f"Chair_Leg_{k}", (0.04, 0.04, 0.425), (x, y + 0.0, 0.2125), wood)
    box("Chair_Back", (0.45, 0.04, 0.5), (0, 0.4, 0.725), wood)
    # lamp: base, pole, shade stacked
    cyl("Lamp_Base", 0.15, 0.03, (1.8, 2.5, 0.015), wood)
    cyl("Lamp_Pole", 0.015, 1.5, (1.8, 2.5, 0.03 + 0.75), wood)
    cyl("Lamp_Shade", 0.2, 0.3, (1.8, 2.5, 1.53 + 0.15), cer)
    bpy.ops.object.light_add(type="AREA", location=(0, -1.5, 2.4))
    l = bpy.context.active_object
    l.name = "Key"
    l.data.energy = 300
    l.data.size = 1.5
    l.rotation_euler = (math.radians(30), 0, 0)
    bpy.ops.object.camera_add(location=(0, -3.2, 1.5))
    cam = bpy.context.active_object
    cam.name = "Cam"
    sc.camera = cam
    target = bpy.data.objects["Table_Top"].location
    d = (target - cam.location)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    sc.world = bpy.data.worlds.new("World")
    sc.world.color = (0.05, 0.05, 0.05)
    sc.frame_start, sc.frame_end = 1, 48
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    bpy.ops.object.select_all(action="DESELECT")
    return sc


# ---------------- clean
sc = base_room()
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "clean_room.blend"))

# ---------------- defects
sc = base_room()
wood = bpy.data.materials["wood"]
# D1 floating box 10 cm above the table
box("Crate", (0.3, 0.3, 0.3), (-0.4, 1.0, 0.75 + 0.15 + 0.10), wood)
# D2 mug sunk 3 cm into the table top
m = bpy.data.objects["Mug"]
m.location.z -= 0.03
# D3 book touching only the wall
box("Book", (0.2, 0.03, 0.25), (1.0, 3.0 - 0.015, 1.4), wood)
# D4 helper hidden in viewport but renders
h = box("Helper_Proxy", (0.5, 0.5, 0.5), (-1.5, 1.5, 0.25))
h.hide_set(True)
# D5 missing texture + normal map tagged sRGB on the wall
wm = bpy.data.materials["wall"]
nt = wm.node_tree
img_missing = bpy.data.images.new("plaster_albedo", 8, 8)
img_missing.source = "FILE"
img_missing.filepath = "//textures/plaster_albedo.png"
t1 = nt.nodes.new("ShaderNodeTexImage")
t1.image = img_missing
nt.links.new(t1.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
img_n = bpy.data.images.new("plaster_normal", 8, 8)
t2 = nt.nodes.new("ShaderNodeTexImage")
t2.image = img_n
nm = nt.nodes.new("ShaderNodeNormalMap")
nt.links.new(t2.outputs["Color"], nm.inputs["Color"])
nt.links.new(nm.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])
# D6 oversize door and giant mug-like object
box("Door", (0.9, 0.05, 4.5), (-2.5, 3.0 - 0.025 - 0.05, 2.25), wood)
cyl("Coffee_Cup", 0.5, 1.2, (2.5, 0.5, 0.6), bpy.data.materials["ceramic"])
# D7 falling ball with default Bezier easing (lands softly)
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.11, location=(-1.0, -0.5, 2.0))
ball = bpy.context.active_object
ball.name = "Ball"
ball.keyframe_insert("location", frame=1)
ball.location.z = 0.11
ball.keyframe_insert("location", frame=36)
# D8 inverted normals crate
inv = box("Crate_Inverted", (0.3, 0.3, 0.3), (-2.2, -0.5, 0.15), wood)
inv.data.flip_normals()
# D9 unlinked object + unused material
bpy.data.objects.new("Ghost", bpy.data.meshes.new("ghost_mesh"))
bpy.data.materials.new("Unused_Gold")
# D10 stacked duplicate
c2 = bpy.data.objects["Chair_Back"].copy()
c2.name = "Chair_Back_dup"
sc.collection.objects.link(c2)
# D11 quaternion-mode rotation set through euler
q = box("Shelf_Rotated", (0.6, 0.2, 0.03), (-1.0, 2.89, 1.0), wood)
q.rotation_mode = "QUATERNION"
q.rotation_euler = (0, 0, math.radians(30))
bpy.ops.object.select_all(action="DESELECT")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "defect_room.blend"))

# ---------------- rigid body scene
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.mesh.primitive_plane_add(size=10)
gr = bpy.context.active_object
gr.name = "Ground"
bpy.ops.rigidbody.world_add()
bpy.ops.rigidbody.object_add(type="PASSIVE")
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 3))
c = bpy.context.active_object
c.name = "Crate_Drop"
bpy.ops.rigidbody.object_add(type="ACTIVE")
c.rigid_body.collision_shape = "MESH"
c.scale = (1, 2, 1)
bpy.ops.mesh.primitive_cube_add(size=0.5, location=(2, 0, 0.2))
c3 = bpy.context.active_object
c3.name = "Block_Overlap"
bpy.ops.rigidbody.object_add(type="ACTIVE")
bpy.ops.mesh.primitive_cube_add(size=0.5, location=(2.2, 0, 0.3))
c4 = bpy.context.active_object
c4.name = "Block_Overlap2"
bpy.ops.rigidbody.object_add(type="ACTIVE")
sc.rigidbody_world.point_cache.frame_end = 100
sc.frame_end = 150
bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
bpy.ops.object.camera_add(location=(8, -8, 5))
cam = bpy.context.active_object
sc.camera = cam
cam.rotation_euler = (c.location - cam.location).to_track_quat("-Z", "Y").to_euler()
bpy.ops.object.select_all(action="DESELECT")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "rigid_drop.blend"))
print("fixtures ->", out)

# ---------------- cloth + soft body scene
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.mesh.primitive_plane_add(size=10)
bpy.context.active_object.name = "Floor"
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.5))
bpy.context.active_object.name = "Table_Block"
bpy.ops.mesh.primitive_grid_add(x_subdivisions=20, y_subdivisions=20, size=1.6, location=(0, 0, 1.5))
cl = bpy.context.active_object
cl.name = "Tablecloth"
cl.modifiers.new("Cloth", "CLOTH")
bpy.ops.mesh.primitive_cube_add(size=0.5, location=(2, 0, 1.0))
sb = bpy.context.active_object
sb.name = "Jelly_Cube"
bpy.ops.object.modifier_add(type="SUBSURF")
sb.modifiers["Subdivision"].levels = 2
bpy.ops.object.modifier_apply(modifier="Subdivision")
m = sb.modifiers.new("Softbody", "SOFT_BODY")
sb.soft_body.use_goal = False
sc.frame_end = 60
bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
bpy.ops.object.camera_add(location=(6, -6, 4))
cam = bpy.context.active_object
sc.camera = cam
cam.rotation_euler = (Vector((1, 0, 0.8)) - cam.location).to_track_quat("-Z", "Y").to_euler()
bpy.ops.object.select_all(action="DESELECT")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "cloth_soft.blend"))
