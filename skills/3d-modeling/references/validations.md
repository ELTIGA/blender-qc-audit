# Blender Modeling - Validations

## Unapplied Transforms in Export Script

### **Id**
unapplied-transforms-export
### **Severity**
critical
### **Category**
export
### **Description**
  Export scripts that don't apply transforms before exporting will cause
  scale and rotation issues in game engines.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
fbx_export|export_scene\.fbx|gltf_export
  #### **File Patterns**
    - *.py
    - *.blend
### **Anti Pattern Example**
  # BAD: Exporting without applying transforms
  import bpy
  
  def export_model(filepath):
      bpy.ops.export_scene.fbx(filepath=filepath)  # No transform application!
  
### **Correct Example**
  # GOOD: Apply transforms before export
  import bpy
  
  def export_model(filepath):
      # Select all mesh objects
      for obj in bpy.context.scene.objects:
          if obj.type == 'MESH':
              obj.select_set(True)
              bpy.context.view_layer.objects.active = obj
  
      # Apply all transforms
      bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
  
      # Now export
      bpy.ops.export_scene.fbx(
          filepath=filepath,
          apply_scale_options='FBX_SCALE_ALL',
          apply_unit_scale=True
      )
  
### **Fix Suggestion**
  Add transform application before export:
  ```python
  bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
  ```
  

## Missing Normals Recalculation

### **Id**
missing-normals-recalculation
### **Severity**
high
### **Category**
topology
### **Description**
  Scripts that modify geometry but don't recalculate normals can leave
  models with inverted or incorrect normals.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
bpy\.ops\.mesh\.(flip_normals|mirror|boolean|bridge_edge_loops|extrude)
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: Mirror without recalculating normals
  import bpy
  
  def mirror_mesh():
      bpy.ops.object.mode_set(mode='EDIT')
      bpy.ops.mesh.select_all(action='SELECT')
      bpy.ops.transform.mirror(constraint_axis=(True, False, False))
      # Missing: recalculate_normals!
      bpy.ops.object.mode_set(mode='OBJECT')
  
### **Correct Example**
  # GOOD: Recalculate normals after geometry operations
  import bpy
  
  def mirror_mesh():
      bpy.ops.object.mode_set(mode='EDIT')
      bpy.ops.mesh.select_all(action='SELECT')
      bpy.ops.transform.mirror(constraint_axis=(True, False, False))
      bpy.ops.mesh.normals_make_consistent(inside=False)  # Recalculate!
      bpy.ops.object.mode_set(mode='OBJECT')
  
### **Fix Suggestion**
  Add normals recalculation after geometry changes:
  ```python
  bpy.ops.mesh.normals_make_consistent(inside=False)
  ```
  

## No N-gon Check Before Export

### **Id**
no-ngon-check
### **Severity**
high
### **Category**
topology
### **Description**
  Export scripts should validate that meshes contain no n-gons before
  exporting to avoid subdivision and shading issues.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
export_scene\.(fbx|gltf|obj)
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: Export without n-gon validation
  import bpy
  
  def export_for_game(filepath):
      bpy.ops.export_scene.fbx(filepath=filepath)
  
### **Correct Example**
  # GOOD: Check for n-gons before export
  import bpy
  import bmesh
  
  def has_ngons(obj):
      """Check if mesh has any n-gons (faces with 5+ vertices)"""
      if obj.type != 'MESH':
          return False
      bm = bmesh.new()
      bm.from_mesh(obj.data)
      ngons = [f for f in bm.faces if len(f.verts) > 4]
      count = len(ngons)
      bm.free()
      return count > 0
  
  def export_for_game(filepath):
      for obj in bpy.context.selected_objects:
          if has_ngons(obj):
              raise ValueError(f"Object {obj.name} contains n-gons! Fix before export.")
  
      bpy.ops.export_scene.fbx(filepath=filepath)
  
### **Fix Suggestion**
  Add n-gon validation before export:
  ```python
  def has_ngons(obj):
      bm = bmesh.new()
      bm.from_mesh(obj.data)
      ngons = [f for f in bm.faces if len(f.verts) > 4]
      bm.free()
      return len(ngons) > 0
  ```
  

## No Non-Manifold Geometry Check

### **Id**
no-nonmanifold-check
### **Severity**
high
### **Category**
topology
### **Description**
  Export scripts should check for non-manifold geometry which causes
  physics and baking failures.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
export_scene\.(fbx|gltf|obj)
  #### **File Patterns**
    - *.py
### **Correct Example**
  # GOOD: Check for non-manifold geometry
  import bpy
  import bmesh
  
  def has_nonmanifold(obj):
      """Check for non-manifold edges and verts"""
      if obj.type != 'MESH':
          return False
  
      bm = bmesh.new()
      bm.from_mesh(obj.data)
  
      # Non-manifold edges (not exactly 2 faces)
      nonmanifold_edges = [e for e in bm.edges if not e.is_manifold]
  
      # Non-manifold verts (edges don't form closed fan)
      nonmanifold_verts = [v for v in bm.verts if not v.is_manifold]
  
      has_issues = len(nonmanifold_edges) > 0 or len(nonmanifold_verts) > 0
      bm.free()
      return has_issues
  
  def export_validated(filepath):
      for obj in bpy.context.selected_objects:
          if has_nonmanifold(obj):
              print(f"WARNING: {obj.name} has non-manifold geometry!")
      bpy.ops.export_scene.fbx(filepath=filepath)
  

## Missing Merge by Distance After Boolean

### **Id**
merge-by-distance-missing
### **Severity**
medium
### **Category**
topology
### **Description**
  Boolean operations leave floating vertices. Scripts should clean up
  after boolean operations.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
bpy\.ops\.object\.modifier_apply.*bool|\.BOOLEAN
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: Apply boolean without cleanup
  import bpy
  
  def apply_boolean(obj_name, cutter_name):
      obj = bpy.data.objects[obj_name]
      mod = obj.modifiers.new(name="Boolean", type='BOOLEAN')
      mod.object = bpy.data.objects[cutter_name]
      mod.operation = 'DIFFERENCE'
  
      bpy.context.view_layer.objects.active = obj
      bpy.ops.object.modifier_apply(modifier="Boolean")
      # Missing cleanup!
  
### **Correct Example**
  # GOOD: Clean up after boolean
  import bpy
  
  def apply_boolean_clean(obj_name, cutter_name):
      obj = bpy.data.objects[obj_name]
      mod = obj.modifiers.new(name="Boolean", type='BOOLEAN')
      mod.object = bpy.data.objects[cutter_name]
      mod.operation = 'DIFFERENCE'
      mod.solver = 'EXACT'  # More reliable solver
  
      bpy.context.view_layer.objects.active = obj
      bpy.ops.object.modifier_apply(modifier="Boolean")
  
      # CLEANUP: Remove floating vertices
      bpy.ops.object.mode_set(mode='EDIT')
      bpy.ops.mesh.select_all(action='SELECT')
      bpy.ops.mesh.remove_doubles(threshold=0.0001)
      bpy.ops.mesh.delete_loose(use_verts=True, use_edges=True, use_faces=False)
      bpy.ops.object.mode_set(mode='OBJECT')
  

## Fast Boolean Solver

### **Id**
fast-boolean-solver
### **Severity**
medium
### **Category**
topology
### **Description**
  The Fast boolean solver produces artifacts with coplanar faces and
  non-manifold input. Use the Exact solver for production geometry.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
solver\s*=\s*['"]FAST['"]
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: Fast solver
  mod = obj.modifiers.new(name="Boolean", type='BOOLEAN')
  mod.solver = 'FAST'
  
### **Correct Example**
  # GOOD: Exact solver
  mod = obj.modifiers.new(name="Boolean", type='BOOLEAN')
  mod.solver = 'EXACT'
  
### **Fix Suggestion**
  Switch the Boolean modifier to the Exact solver:
  ```python
  mod.solver = 'EXACT'
  ```
  

## Deprecated Auto Smooth API (Blender 4.1+)

### **Id**
deprecated-auto-smooth
### **Severity**
high
### **Category**
compatibility
### **Description**
  Mesh.use_auto_smooth and Mesh.auto_smooth_angle were removed in Blender 4.1.
  Scripts using them raise AttributeError. Use Smooth by Angle instead.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
use_auto_smooth|auto_smooth_angle
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: Removed in Blender 4.1
  import math
  obj.data.use_auto_smooth = True
  obj.data.auto_smooth_angle = math.radians(30)
  
### **Correct Example**
  # GOOD: Blender 4.1+
  import bpy
  import math
  
  bpy.ops.object.shade_smooth_by_angle(angle=math.radians(30), keep_sharp_edges=True)
  
### **Fix Suggestion**
  Replace auto smooth properties with:
  ```python
  bpy.ops.object.shade_smooth_by_angle(angle=math.radians(30))
  ```
  

## Legacy OBJ Exporter (Removed in Blender 4.0)

### **Id**
legacy-obj-exporter
### **Severity**
high
### **Category**
compatibility
### **Description**
  The Python OBJ add-on (export_scene.obj / import_scene.obj) was removed
  in Blender 4.0. Use the built-in C++ OBJ operators instead.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
export_scene\.obj|import_scene\.obj
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: Operator no longer exists in Blender 4.0+
  bpy.ops.export_scene.obj(filepath=filepath, use_selection=True)
  
### **Correct Example**
  # GOOD: Built-in OBJ exporter/importer
  bpy.ops.wm.obj_export(
      filepath=filepath,
      export_selected_objects=True,
      apply_modifiers=True,
  )
  bpy.ops.wm.obj_import(filepath=filepath)
  
### **Fix Suggestion**
  Replace with `bpy.ops.wm.obj_export(...)` / `bpy.ops.wm.obj_import(...)`.
  

## Export Without Selection Filter

### **Id**
export-without-selection
### **Severity**
medium
### **Category**
export
### **Description**
  Exporting without limiting to selected objects exports everything in the
  scene - boolean cutters, bake cages, high polys, lights, and cameras.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
export_scene\.(fbx|gltf)\((?![^)]*use_selection)
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: Exports the whole scene, including hidden cutters
  bpy.ops.export_scene.fbx(filepath=filepath)
  
### **Correct Example**
  # GOOD: Export only what is selected
  bpy.ops.export_scene.fbx(filepath=filepath, use_selection=True)
  bpy.ops.export_scene.gltf(filepath=filepath, use_selection=True)
  
### **Fix Suggestion**
  Add `use_selection=True` (or `use_active_collection=True`) to the export call.
  

## Reading Mesh Data While in Edit Mode

### **Id**
stale-edit-mode-data
### **Severity**
medium
### **Category**
scripting
### **Description**
  While an object is in Edit Mode, obj.data.vertices / edges / polygons are
  NOT updated. Reading or writing them returns stale data or is lost on exit.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
mode_set\(mode=['"]EDIT['"]\)[\s\S]*?\.data\.(vertices|edges|polygons)
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: Mesh data is stale in Edit Mode
  bpy.ops.object.mode_set(mode='EDIT')
  selected = [v for v in obj.data.vertices if v.select]
  
### **Correct Example**
  # GOOD: Use bmesh for Edit Mode access
  import bmesh
  
  bpy.ops.object.mode_set(mode='EDIT')
  bm = bmesh.from_edit_mesh(obj.data)
  selected = [v for v in bm.verts if v.select]
  # ... modify ...
  bmesh.update_edit_mesh(obj.data)
  
### **Fix Suggestion**
  Use `bmesh.from_edit_mesh()` in Edit Mode, or switch to Object Mode
  before reading `obj.data`.
  

## Invalid Asset Naming Convention

### **Id**
invalid-asset-naming
### **Severity**
low
### **Category**
organization
### **Description**
  Asset names should follow consistent conventions for organization
  and automation compatibility.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
(?i)^(final|new|test|old|copy|backup|\d+)[._-]|\s+\.|[^a-zA-Z0-9_.-]
  #### **File Patterns**
    - *.fbx
    - *.obj
    - *.gltf
    - *.glb
    - *.blend
### **Anti Pattern Example**
  # BAD naming examples:
  Final_Chair.fbx
  chair final v2.fbx
  New Folder/model.fbx
  test123.fbx
  chair (1).fbx
  
### **Correct Example**
  # GOOD naming convention:
  SM_Chair_Wood_LOD0.fbx
  SK_Character_Hero.fbx
  SM_Prop_Barrel_Metal_v02.fbx
  
  # Pattern: [Type]_[Category]_[Name]_[Variant]_[LOD/Version]
  

## Missing LOD Suffix on LOD Meshes

### **Id**
missing-lod-suffix
### **Severity**
low
### **Category**
organization
### **Description**
  LOD meshes should have explicit _LOD# suffix for proper identification
  and auto-import by game engines.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
(?<!LOD[0-9])\.fbx$
  #### **File Patterns**
    - *_low.fbx
    - *_med.fbx
    - *_high.fbx
### **Anti Pattern Example**
  # BAD: Unclear LOD naming
  chair_low.fbx
  chair_medium.fbx
  chair_high.fbx
  
### **Correct Example**
  # GOOD: Standard LOD naming
  SM_Chair_LOD0.fbx  # Base mesh
  SM_Chair_LOD1.fbx  # 50% reduction
  SM_Chair_LOD2.fbx  # 25% reduction
  SM_Chair_LOD3.fbx  # 12.5% reduction
  

## Non-Power-of-Two Texture Dimensions

### **Id**
non-power-of-two-textures
### **Severity**
medium
### **Category**
optimization
### **Description**
  Textures should be power-of-two dimensions (256, 512, 1024, 2048, 4096)
  for optimal GPU memory usage and mipmap generation.
  
### **Detection**
  #### **Type**
script
  #### **Script**
    # This would be validated by a separate texture checking tool
    # Dimensions should be: 256, 512, 1024, 2048, 4096
    valid_sizes = [256, 512, 1024, 2048, 4096, 8192]
    
### **File Patterns**
  - *.png
  - *.tga
  - *.jpg
### **Correct Example**
  # GOOD texture dimensions:
  T_Chair_D.png     # 2048x2048
  T_Character_D.png # 4096x4096
  T_Icon_UI.png     # 256x256
  
  # Can be non-square but still power-of-two:
  T_Ribbon_D.png    # 2048x256
  

## Wrong Texture Type Suffix

### **Id**
wrong-texture-suffix
### **Severity**
low
### **Category**
organization
### **Description**
  Texture files should have correct suffixes indicating their type
  for material auto-assignment.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
(?i)(?<!_[DNRMAOHE])(_diffuse|_normal|_roughness|_metallic|_ao|_height|_emissive|_opacity)\.(?:png|tga|jpg)
  #### **File Patterns**
    - *.png
    - *.tga
    - *.jpg
### **Anti Pattern Example**
  # BAD: Full word suffixes (inconsistent)
  chair_diffuse.png
  chair_normal.png
  chair_roughness.png
  
### **Correct Example**
  # GOOD: Single letter suffixes (industry standard)
  T_Chair_D.png   # Diffuse/Albedo
  T_Chair_N.png   # Normal
  T_Chair_R.png   # Roughness
  T_Chair_M.png   # Metallic
  T_Chair_AO.png  # Ambient Occlusion
  T_Chair_H.png   # Height
  T_Chair_E.png   # Emissive
  
  # OR packed textures:
  T_Chair_ORM.png # Occlusion, Roughness, Metallic (RGB)
  T_Chair_ARM.png # AO, Roughness, Metallic (RGB)

## Calling bpy.ops Inside Loops (O(N^2) Scene Resync)

### **Id**
bpy-ops-in-loop
### **Severity**
high
### **Category**
optimization
### **Description**
  Calling `bpy.ops.*` inside a `for` or `while` loop triggers a full
  dependency-graph update and undo push on every iteration, causing quadratic
  slowdowns and MCP socket timeouts.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
(for\s+[^\n]+:|while\s+[^\n]+:)\s*\n(?:\s+[^\n]*\n){0,5}?\s+bpy\.ops\.
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: Spawning 500 cubes via bpy.ops triggers 500 scene updates
  for i in range(500):
      bpy.ops.mesh.primitive_cube_add(location=(i * 2.0, 0, 0))
  
### **Correct Example**
  # GOOD: Create mesh once, link 500 lightweight Object instances, update once
  import bpy
  
  bpy.ops.mesh.primitive_cube_add()
  shared_mesh = bpy.context.active_object.data
  bpy.data.objects.remove(bpy.context.active_object, do_unlink=True)
  
  col = bpy.context.collection
  for i in range(500):
      obj = bpy.data.objects.new(f"Cube_{i:04d}", shared_mesh)
      obj.location = (i * 2.0, 0, 0)
      col.objects.link(obj)
  bpy.context.view_layer.update()
  
### **Fix Suggestion**
  Move `bpy.ops` outside the loop or replace with `bpy.data.objects.new(name, shared_mesh)`
  and a single `bpy.context.view_layer.update()` after the loop.
  

## Legacy Principled BSDF Socket Names or Indices (Blender 4.0+)

### **Id**
legacy-principled-bsdf-sockets
### **Severity**
critical
### **Category**
compatibility
### **Description**
  Blender 4.0 renamed key Principled BSDF sockets (`Specular` -> `Specular IOR Level`,
  `Transmission` -> `Transmission Weight`, `Clearcoat` -> `Coat Weight`,
  `Clearcoat Roughness` -> `Coat Roughness`, `Subsurface` -> `Subsurface Weight`,
  `Sheen` -> `Sheen Weight`, `Emission` -> `Emission Color`) and reordered socket indices.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
inputs\[\s*(?:['"](?:Specular|Clearcoat|Clearcoat Roughness|Transmission|Transmission Roughness|Subsurface|Subsurface Color|Sheen|Emission)['"]|\d+)\s*\]
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: Legacy 3.x socket names and integer indices fail in Blender 4.0-5.x
  bsdf.inputs["Specular"].default_value = 0.5
  bsdf.inputs["Clearcoat"].default_value = 1.0
  bsdf.inputs["Transmission"].default_value = 1.0
  bsdf.inputs["Emission"].default_value = (1, 0.5, 0, 1)
  bsdf.inputs[7].default_value = 0.2
  
### **Correct Example**
  # GOOD: Modern Blender 4.0-5.x socket names
  bsdf.inputs["Specular IOR Level"].default_value = 0.5
  bsdf.inputs["Coat Weight"].default_value = 1.0
  bsdf.inputs["Transmission Weight"].default_value = 1.0
  bsdf.inputs["Emission Color"].default_value = (1, 0.5, 0, 1)
  bsdf.inputs["Roughness"].default_value = 0.2
  
### **Fix Suggestion**
  Use Blender 4.0+ Principled BSDF socket names (`"Specular IOR Level"`, `"Coat Weight"`,
  `"Coat Roughness"`, `"Transmission Weight"`, `"Subsurface Weight"`, `"Sheen Weight"`,
  `"Emission Color"`) and never index `inputs` by integer.
  

## Legacy Node Group Inputs/Outputs API (Removed in Blender 4.0)

### **Id**
legacy-nodetree-interface
### **Severity**
high
### **Category**
compatibility
### **Description**
  `node_tree.inputs.new()` and `node_tree.outputs.new()` were removed in
  Blender 4.0 in favor of `node_tree.interface.new_socket()`.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
\.(?:inputs|outputs)\.new\(\s*['"]NodeSocket
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: Removed in Blender 4.0
  node_group.inputs.new('NodeSocketFloat', 'Radius')
  node_group.outputs.new('NodeSocketGeometry', 'Geometry')
  
### **Correct Example**
  # GOOD: Blender 4.0-5.x NodeTreeInterface API
  node_group.interface.new_socket(name='Radius', in_out='INPUT', socket_type='NodeSocketFloat')
  node_group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
  
### **Fix Suggestion**
  Use `node_group.interface.new_socket(name=..., in_out='INPUT'|'OUTPUT', socket_type=...)`.
  

## Legacy Action.fcurves Direct Access (Blender 4.4+ Slotted Actions)

### **Id**
legacy-action-fcurves
### **Severity**
high
### **Category**
compatibility
### **Description**
  Blender 4.4 introduced Slotted Actions and Blender 5.0 removed direct
  `action.fcurves` access. F-Curves now live on a slot's `channelbag`.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
\baction\.fcurves\b
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: Deprecated in 4.4, removed in 5.0
  fc = action.fcurves.new(data_path="location", index=2)
  
### **Correct Example**
  # GOOD: Slotted Actions channelbag API (Blender 4.4 - 5.x)
  slot = action.slots.new(id_type='OBJECT', name=obj.name)
  obj.animation_data.action_slot = slot
  layer = action.layers.new("Layer") if not action.layers else action.layers[0]
  strip = layer.strips.new(type='KEYFRAME') if not layer.strips else layer.strips[0]
  channelbag = strip.channelbag(slot, ensure=True)
  fc = channelbag.fcurves.new("location", index=2)
  
### **Fix Suggestion**
  Fetch or create the slot's `channelbag` via `strip.channelbag(slot, ensure=True)`
  or `bpy_extras.anim_utils.action_get_channelbag_for_slot(action, slot)` and access
  `.fcurves` on the channelbag.
  

## Legacy EEVEE Properties (Removed in Blender 4.2 EEVEE Next)

### **Id**
legacy-eevee-properties
### **Severity**
high
### **Category**
compatibility
### **Description**
  EEVEE Next (Blender 4.2+) removed `scene.eevee.use_ssr`, `use_gtao`,
  `use_bloom`, and material `blend_method` / `shadow_method`.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
\.eevee\.(?:use_ssr|use_gtao|use_bloom)\b|\.(?:blend_method|shadow_method)\s*=
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: Legacy EEVEE 3.x properties
  scene.eevee.use_ssr = True
  scene.eevee.use_gtao = True
  mat.blend_method = 'BLEND'
  
### **Correct Example**
  # GOOD: EEVEE Next (Blender 4.2 - 5.x)
  scene.eevee.use_raytracing = True
  mat.surface_render_method = 'DITHERED'  # or 'BLENDED'
  mat.use_raytrace_refraction = True
  
### **Fix Suggestion**
  Replace `use_ssr`/`use_gtao` with `scene.eevee.use_raytracing = True`, and
  `mat.blend_method` with `mat.surface_render_method = 'DITHERED'` or `'BLENDED'`.
  

## Dict-Style Access to RNA Properties (Removed in Blender 5.0)

### **Id**
blender5-dict-prop-access
### **Severity**
high
### **Category**
compatibility
### **Description**
  Blender 5.0 separated `bpy.props` storage from user IDProperties.
  Accessing RNA property groups like `scene['cycles']` raises `KeyError`.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
\b(?:scene|obj|object|mat|material)\[\s*['"](?:cycles|eevee|render|view_settings)['"]\s*\]
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: Raises KeyError in Blender 5.0+
  samples = bpy.context.scene['cycles']['samples']
  
### **Correct Example**
  # GOOD: Standard RNA attribute access
  samples = bpy.context.scene.cycles.samples
  
### **Fix Suggestion**
  Use standard attribute syntax (`scene.cycles.samples`) instead of dictionary indexing.
  

## Non-Color Data Map Left on Default sRGB Colorspace

### **Id**
non-color-map-missing-colorspace
### **Severity**
critical
### **Category**
materials
### **Description**
  Normal, Roughness, Metallic, AO, ORM, and Displacement maps loaded without
  setting `colorspace_settings.name = 'Non-Color'` have a ~2.2 sRGB gamma curve
  applied, tilting surface normals and corrupting roughness/displacement values.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
(?i)images\.load\([^)]*(?:normal|nrm|_n\.|rough|rgh|_r\.|metal|_m\.|disp|height|_orm|_arm)[^)]*\)(?![\s\S]{0,200}?Non-Color)
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: Normal map stays in default 'sRGB' colorspace!
  norm_img = bpy.data.images.load("/textures/T_Chair_N.png")
  tex_node.image = norm_img
  
### **Correct Example**
  # GOOD: Explicitly set Non-Color after loading
  norm_img = bpy.data.images.load("/textures/T_Chair_N.png", check_existing=True)
  norm_img.colorspace_settings.name = 'Non-Color'
  tex_node.image = norm_img
  
### **Fix Suggestion**
  Set `img.colorspace_settings.name = 'Non-Color'` immediately after loading any
  normal, roughness, metallic, AO, height, or packed ORM texture.
  

## Physically Implausible Pure Black (0.0) or Pure White (1.0) Albedo

### **Id**
implausible-pbr-albedo
### **Severity**
medium
### **Category**
materials
### **Description**
  Setting Principled BSDF `Base Color` to pure white `(1.0, 1.0, 1.0, 1.0)` or
  pure black `(0.0, 0.0, 0.0, 1.0)` violates energy conservation, causes
  Cycles fireflies, and flattens indirect bounce lighting.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
inputs\[\s*['"]Base Color['"]\s*\]\.default_value\s*=\s*\(\s*(?:1(?:\.0+)?\s*,\s*1(?:\.0+)?\s*,\s*1(?:\.0+)?|0(?:\.0+)?\s*,\s*0(?:\.0+)?\s*,\s*0(?:\.0+)?)\s*,
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: 100% or 0% reflectance never occurs in physical materials
  bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
  bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1.0)
  
### **Correct Example**
  # GOOD: Keep linear albedo within [0.03, 0.85]
  bsdf.inputs["Base Color"].default_value = (0.82, 0.82, 0.80, 1.0)  # Fresh white paint
  bsdf.inputs["Base Color"].default_value = (0.04, 0.04, 0.04, 1.0)  # Matte black rubber
  
### **Fix Suggestion**
  Clamp dielectric `Base Color` RGB channels to `[0.03, 0.85]`.
  

## Extreme Camera Clipping Range (Z-Fighting Trigger)

### **Id**
extreme-camera-clip-range
### **Severity**
high
### **Category**
rendering
### **Description**
  Setting `clip_start` extremely small (`< 0.001`) or `clip_end` extremely
  large (`> 10000`) destroys depth-buffer precision and causes scene-wide Z-fighting.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
clip_start\s*=\s*0\.000\d*|clip_end\s*=\s*[1-9]\d{4,}
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: clip_end / clip_start = 1,000,000,000 -> catastrophic Z-fighting
  cam.data.clip_start = 0.0001
  cam.data.clip_end = 100000.0
  
### **Correct Example**
  # GOOD: Tight clip range preserves depth buffer precision
  cam.data.clip_start = 0.05
  cam.data.clip_end = 500.0
  
### **Fix Suggestion**
  Keep `clip_start >= 0.01` (prefer `0.05`) and `clip_end / clip_start <= 10,000`.
  

## Raw Degree Literals Assigned to Euler Rotations

### **Id**
euler-degrees-in-rotation
### **Severity**
high
### **Category**
scripting
### **Description**
  `rotation_euler` expects radians. Passing raw degree numbers (`45`, `90`, `180`)
  rotates the object by dozens of full revolutions toward an arbitrary angle.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
rotation_euler(?:\.[xyz]|\[\d\])?\s*=\s*(?:\(\s*)?(?:-?(?:30|45|60|90|120|135|180|270|360)(?:\.0)?\b)
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: 90 radians is 5156.6 degrees!
  obj.rotation_euler = (0, 0, 90)
  obj.rotation_euler.x = 45
  
### **Correct Example**
  # GOOD: Convert degrees to radians
  import math
  obj.rotation_euler = (0, 0, math.radians(90))
  obj.rotation_euler.x = math.radians(45)
  
### **Fix Suggestion**
  Wrap degree values in `math.radians(...)`.
  

## Excessive Subdivision Surface Levels

### **Id**
excessive-subsurf-levels
### **Severity**
high
### **Category**
optimization
### **Description**
  Setting Subdivision Surface `levels > 3` or `render_levels > 4` causes
  $4^N$ polygon explosion (`levels = 5` is 1,024x faces), freezing the viewport
  or exhausting VRAM.
  
### **Detection**
  #### **Type**
regex
  #### **Pattern**
\.(?:levels|render_levels)\s*=\s*[5-9]\b
  #### **File Patterns**
    - *.py
### **Anti Pattern Example**
  # BAD: 4^6 = 4096x polygon multiplier!
  subsurf = obj.modifiers.new(name="Subdivision", type='SUBSURF')
  subsurf.levels = 5
  subsurf.render_levels = 6
  
### **Correct Example**
  # GOOD: Keep viewport <= 2 and render <= 3
  subsurf = obj.modifiers.new(name="Subdivision", type='SUBSURF')
  subsurf.levels = 2
  subsurf.render_levels = 3
  
### **Fix Suggestion**
  Keep `subsurf.levels <= 2` and `subsurf.render_levels <= 3`, and enable
  `scene.render.use_simplify = True`.
