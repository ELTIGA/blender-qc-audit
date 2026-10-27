# Blender Modeling & Scene Generation - Sharp Edges

This reference documents the critical failure modes, API breakages (Blender 4.0 through 5.2+), visual anomalies, and performance traps that AI coding agents and technical artists hit when building or modifying Blender scenes.

---

## 1. Blender 4.0 – 5.2+ Python API Breakages (Outdated Training-Weight Traps)

LLM training corpora are heavily polluted with Blender 2.8–3.6 snippets. Running those snippets in modern Blender (4.0 through 5.2 LTS) causes immediate exceptions or silent corruption.

### 1.1 Principled BSDF v2 Socket Renames (Blender 4.0+)
* **Why it fails:** Blender 4.0 rewrote the Principled BSDF node into a multi-layered coat/sheen/subsurface model. Legacy socket names and hardcoded indices (`principled.inputs[7]`) raise `KeyError` or modify the wrong parameter.
* **Never use integer indices** on `principled.inputs[i]`. Always index by the modern string name:

| Legacy Socket Name (3.x) | Modern Socket Name (4.0 – 5.x) | Notes |
| :--- | :--- | :--- |
| `"Subsurface"` | `"Subsurface Weight"` | Float `0.0–1.0` |
| *(none)* | `"Subsurface Scale"` | Scales `Subsurface Radius` (meters) |
| `"Subsurface Color"` | *(Removed)* | Use `"Base Color"` + `"Subsurface Radius"` |
| `"Specular"` | `"Specular IOR Level"` | Default `0.5` (= 4% reflectance at IOR 1.5) |
| `"Specular Tint"` | `"Specular Tint"` | Changed from Float to **RGBA Color**! |
| `"Transmission"` | `"Transmission Weight"` | Float `0.0–1.0` |
| `"Transmission Roughness"` | *(Removed)* | Controlled directly by `"Roughness"` |
| `"Clearcoat"` | `"Coat Weight"` | Float `0.0–1.0` |
| `"Clearcoat Roughness"` | `"Coat Roughness"` | Float `0.0–1.0` |
| `"Clearcoat Normal"` | `"Coat Normal"` | Vector |
| `"Sheen"` | `"Sheen Weight"` | Float `0.0–1.0` |
| `"Sheen Tint"` | `"Sheen Tint"` | Changed from Float to **RGBA Color**! |
| `"Emission"` | `"Emission Color"` | RGBA Color (pair with `"Emission Strength"`) |

```python
# GOOD (Blender 4.0 - 5.x)
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.6, 0.15, 0.08, 1.0)
bsdf.inputs["Roughness"].default_value = 0.35
bsdf.inputs["Specular IOR Level"].default_value = 0.5
bsdf.inputs["Coat Weight"].default_value = 0.2
bsdf.inputs["Coat Roughness"].default_value = 0.08
bsdf.inputs["Emission Color"].default_value = (1.0, 0.4, 0.1, 1.0)
bsdf.inputs["Emission Strength"].default_value = 5.0
```

### 1.2 Node Group Interface Overhaul (Blender 4.0+)
* **Why it fails:** `node_tree.inputs.new(...)` and `node_tree.outputs.new(...)` were removed in 4.0. Geometry Nodes and Shader Node groups now manage sockets through `node_tree.interface`.
```python
# BAD (3.x - raises AttributeError)
# node_group.inputs.new('NodeSocketFloat', 'Radius')

# GOOD (4.0+)
sock_in = node_group.interface.new_socket(
    name="Radius",
    in_out='INPUT',
    socket_type='NodeSocketFloat',
)
sock_in.default_value = 1.0

sock_out = node_group.interface.new_socket(
    name="Geometry",
    in_out='OUTPUT',
    socket_type='NodeSocketGeometry',
)
```

### 1.3 Mesh Edge Properties Migrated to Generic Attributes (Blender 4.0+)
* **Why it fails:** `edge.bevel_weight`, `edge.crease`, and `vert.bevel_weight` were removed from `MeshEdge`/`MeshVertex` in 4.0 and moved to generic attributes (`bevel_weight_edge`, `crease_edge`, `bevel_weight_vert`, `sharp_edge`).
```python
# GOOD (4.0+ Object Mode via attributes)
attr = mesh.attributes.get("bevel_weight_edge")
if attr is None:
    attr = mesh.attributes.new(name="bevel_weight_edge", type='FLOAT', domain='EDGE')
attr.data.foreach_set("value", [1.0] * len(mesh.edges))

# GOOD (4.0+ Edit Mode via bmesh)
bm = bmesh.from_edit_mesh(mesh)
bw_layer = bm.edges.layers.float.get("bevel_weight_edge") or bm.edges.layers.float.new("bevel_weight_edge")
for e in bm.edges:
    if not e.smooth:
        e[bw_layer] = 1.0
bmesh.update_edit_mesh(mesh)
```

### 1.4 Auto Smooth Removed from Mesh Data (Blender 4.1+)
* **Why it fails:** `mesh.use_auto_smooth` and `mesh.auto_smooth_angle` were completely removed in 4.1.
```python
# BAD (raises AttributeError in 4.1+)
# obj.data.use_auto_smooth = True

# GOOD (4.1+ operator or modifier)
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(30), keep_sharp_edges=True)
```

### 1.5 EEVEE Next Engine & Material API (Blender 4.2 LTS – 5.x)
* **Why it fails:** Blender 4.2 replaced legacy EEVEE with EEVEE Next. Screen-space toggles (`scene.eevee.use_ssr`, `scene.eevee.use_gtao`, `scene.eevee.use_bloom`) and material alpha/shadow properties (`mat.blend_method`, `mat.shadow_method`) were removed or deprecated.
  * *Engine ID quirk:* In Blender 4.2–4.5 the engine enum is `'BLENDER_EEVEE_NEXT'`; in Blender 5.0+ it returned to `'BLENDER_EEVEE'`.
  * *Bloom:* Moved to the **Compositor** (`Glare` node with `glare_type = 'BLOOM'`) accompanied by Viewport Compositor (`space.shading.use_compositor = 'ALWAYS'`).
```python
# Safe EEVEE engine assignment across 4.2 - 5.x
scene.render.engine = 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'

# Enable raytracing (replaces use_ssr / use_gtao)
scene.eevee.use_raytracing = True

# Material transparency (replaces mat.blend_method)
mat.surface_render_method = 'DITHERED'  # or 'BLENDED' for alpha blend
mat.use_raytrace_refraction = True      # for refractive glass
```

### 1.6 Slotted Actions Overhaul (Blender 4.4+)
* **Why it fails:** In Blender 4.4+, Actions hold multiple **Action Slots** so one Action can animate several datablocks. `action.fcurves` and `action.groups` were removed in 5.0 (deprecated in 4.4). F-Curves now live inside a `Channelbag` on a keyframe strip.
```python
# BAD (pre-4.4 - fails on modern slotted actions)
# fc = action.fcurves.new(data_path="location", index=2)

# GOOD (4.4 - 5.x)
from bpy_extras import anim_utils

if not obj.animation_data:
    obj.animation_data_create()
action = bpy.data.actions.new(name="MoveZ")
obj.animation_data.action = action
slot = action.slots.new(id_type='OBJECT', name=obj.name)
obj.animation_data.action_slot = slot

layer = action.layers.new("Layer") if not action.layers else action.layers[0]
strip = layer.strips.new(type='KEYFRAME') if not layer.strips else layer.strips[0]
channelbag = strip.channelbag(slot, ensure=True)

fc = channelbag.fcurves.new("location", index=2)
fc.keyframe_points.insert(1, 0.0)
fc.keyframe_points.insert(60, 2.5)
```

### 1.7 Blender 5.0 – 5.2 LTS Breaking Changes
* **No Dict-Style Access to RNA / `bpy.props` (5.0+):** `bpy.props` properties are no longer stored in the user IDProperty dict. `bpy.context.scene['cycles']` or `obj['my_registered_prop']` raises `KeyError`. Always use dot access (`scene.cycles`, `obj.my_registered_prop`).
* **Geometry Nodes Modifier Inputs as RNA Properties (5.2 LTS+):** Instead of fragile custom-property keys `mod["Socket_2_use_attribute"] = True`, 5.2 exposes structured RNA:
  ```python
  # Blender 5.2+ structured GN modifier inputs
  if hasattr(mod, "properties") and hasattr(mod.properties, "inputs"):
      inp = getattr(mod.properties.inputs, identifier)
      inp.value = 5.0
  else:
      mod[identifier] = 5.0
      obj.data.update()
  ```
* **`bgl` Removed & GPU Shader Constructor Dropped (5.0+):** Always use `gpu.shader.from_builtin('UNIFORM_COLOR')` or `gpu.shader.create_from_info(shader_info)`. In headless (`-b`) mode, call `gpu.init()` first (5.2+).
* **Compositor Node Tree Moved (5.0+):** `scene.use_nodes` and `scene.node_tree` were removed in 5.0. Create a compositor group via `tree = bpy.data.node_groups.new("Comp", "CompositorNodeTree"); scene.compositing_node_group = tree`.
* **Video Output Media Type (5.0+):** Setting `scene.render.image_settings.file_format = 'FFMPEG'` directly raises `TypeError` unless you set `scene.render.image_settings.media_type = 'VIDEO'` first.
* **Boolean Fast Solver Renamed (5.0+):** `mod.solver = 'FAST'` was renamed to `'FLOAT'` in 5.0 (always prefer `'EXACT'` for clean topology).
* **Curves / Hair Resolution Evaluated (5.0+):** The `resolution` attribute on new `Curves` objects is now evaluated at render time; high values on dense hair curves can exhaust VRAM if left unchecked.
* **Color Management & Working Spaces (5.0+):** Supports `Linear Rec.709` (default), `Linear Rec.2020`, and `ACEScg` working spaces alongside `AgX`, `AgX HDR`, and native `ACES 1.3 / 2.0` view transforms. Always set `view_transform` **before** setting `look` (`'AgX - Medium High Contrast'`, `'AgX - Punchy'`).

---

## 2. AI Agent & MCP Failure Modes ("Silently Successful" Bugs)

Empirical benchmarks on LLM 3D generation (*BlenderGym*, *LL3M*, *SceneCraft*, and production *BlenderMCP* logs) show that **over 70% of agent failures exit with Python return code `0`**. The code runs cleanly, but the resulting 3D scene is broken.

### 2.1 Spatial & Metric Blindness (Floating, Sinking, and Interpenetrating Objects)
* **Why agents do it:** Agents place primitives at their center origin (e.g., `cube.location = (0, 0, 0)`, `table_top.location = (0, 0, 0.75)`) without accounting for half-extents (`dimensions.z / 2`), modifier thickness, or parent transforms. Result: furniture buried halfway into the floor (`z < 0`), floating legs, or table tops intersecting chairs.
* **How to prevent & diagnose:**
  1. Never guess heights. Compute the **evaluated world-space bounding box** after updating the view layer:
     ```python
     import bpy
     from mathutils import Vector

     def world_bbox(obj):
         bpy.context.view_layer.update()
         depsgraph = bpy.context.evaluated_depsgraph_get()
         eval_obj = obj.evaluated_get(depsgraph)
         corners = [eval_obj.matrix_world @ Vector(c) for c in eval_obj.bound_box]
         xs = [p.x for p in corners]
         ys = [p.y for p in corners]
         zs = [p.z for p in corners]
         return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))

     def snap_bottom_to_z(obj, target_z=0.0):
         bmin, _ = world_bbox(obj)
         obj.location.z += (target_z - bmin.z)
         bpy.context.view_layer.update()
     ```
  2. Stack objects using `target_z = bmax_below.z`, never hardcoded guesses.
  3. Detect unintended mesh intersections with `mathutils.bvhtree.BVHTree`:
     ```python
     from mathutils.bvhtree import BVHTree

     def meshes_overlap(obj_a, obj_b):
         depsgraph = bpy.context.evaluated_depsgraph_get()
         bvh_a = BVHTree.FromObject(obj_a.evaluated_get(depsgraph), depsgraph)
         bvh_b = BVHTree.FromObject(obj_b.evaluated_get(depsgraph), depsgraph)
         return len(bvh_a.overlap(bvh_b)) > 0
     ```

### 2.2 Stale Depsgraph & Un-Updated Matrices
* **Why agents do it:** In `bpy`, mutating `obj.location`, `obj.scale`, `obj.rotation_euler`, or adding a modifier **does not immediately update `obj.matrix_world` or `obj.bound_box`**. Reading `obj.matrix_world` on the next line returns the old identity matrix!
* **Fix:** Call `bpy.context.view_layer.update()` before reading `matrix_world`, `dimensions`, or `bound_box`. When modifiers are present, query `obj.evaluated_get(bpy.context.evaluated_depsgraph_get())`.

### 2.3 Radian vs. Degree & Quaternion Rotation Traps
* **Why agents do it:**
  1. `obj.rotation_euler` and modifier angles (`shade_smooth_by_angle`, `bevel.angle_limit`, `screw.angle`, `simple_deform.angle`) take **radians**, whereas humans think in degrees. Writing `obj.rotation_euler.z = 90` rotates the object by `5156.62°`, scrambling its alignment.
  2. Imported glTF/FBX objects often have `obj.rotation_mode == 'QUATERNION'`. Writing to `obj.rotation_euler` while in quaternion mode is **silently ignored** with zero error!
  3. Calling `bpy.ops.object.transform_apply(scale=True)` without `location=False, rotation=False` applies location and rotation too (both default to `True`!), resetting every selected object's origin to `(0, 0, 0)`.
* **Fix:** Always wrap literal angles in `math.radians(deg)`, set `obj.rotation_mode = 'XYZ'` before writing `rotation_euler`, and pass explicit flags `transform_apply(location=False, rotation=False, scale=True)`.

### 2.4 `RuntimeError: Operator poll() failed` in Headless / MCP Execution
* **Why agents do it:** `bpy.ops.*` operators check UI context (`bpy.context.area`, `bpy.context.region`, `active_object`, `mode`). In `--background` CLI runs or inside `blender-mcp` timer callbacks, `bpy.context.area` is `None`, causing `poll() failed`.
* **Fix:**
  1. **Prefer Data API over `bpy.ops`** whenever possible (`bpy.data.meshes.new`, `obj.modifiers.new`, `bmesh`, matrix transforms `mesh.transform(mat)`).
  2. When an operator is unavoidable in GUI/MCP mode, scope it with `bpy.context.temp_override`:
     ```python
     def run_with_view3d_override(fn, active_obj=None, selected=None):
         win = bpy.context.window or (bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None)
         area = next((a for a in win.screen.areas if a.type == 'VIEW_3D'), None) if win else None
         region = next((r for r in area.regions if r.type == 'WINDOW'), None) if area else None
         kw = {}
         if win: kw['window'] = win; kw['screen'] = win.screen
         if area: kw['area'] = area
         if region: kw['region'] = region
         if active_obj: kw['active_object'] = active_obj; kw['object'] = active_obj
         if selected is not None: kw['selected_objects'] = selected
         with bpy.context.temp_override(**kw):
             return fn()
     ```

### 2.5 "Geometry Soup" from Multi-Step Blind Generation
* **Why agents do it:** Writing 400 lines of procedural `bmesh` extrusions, insets, and booleans in one shot without intermediate checks compounds topological errors (extruding zero-area faces, booleaning non-manifold shells, flipping normals).
* **Fix:** Build modular components in isolated functions, run `mesh.validate(verbose=True)` and `bmesh.ops.recalc_face_normals(bm, faces=bm.faces)` on each component, and visually inspect before assembling.

---

## 3. Visual Anomalies & "CG Giveaway" Artifacts Agents Brush Off

Even when geometry is valid, agent-generated scenes frequently exhibit glaring visual defects that humans immediately spot.

### 3.1 Non-Color Data Maps Left on `sRGB`
* **Symptom:** Normal maps tilt shading toward one corner of the scene and show hard UV seam steps; roughness maps look overly glossy and plastic; displacement maps inflate the entire mesh outward instead of centering at `0.5`.
* **Root cause:** Blender defaults new `Image` datablocks to `sRGB`. Applying the sRGB EOTF (~2.2 gamma) to a normal map turns the neutral flat vector `(0.5, 0.5, 1.0)` into `(0.214, 0.214, 1.0)` — a **26° normal tilt** across every triangle!
* **Fix:** Explicitly set `colorspace_settings.name = 'Non-Color'` on every normal, roughness, metallic, AO, height/displacement, opacity, or packed ORM image **after** setting its `filepath`:
  ```python
  img = bpy.data.images.load(filepath, check_existing=True)
  img.colorspace_settings.name = 'Non-Color'  # MUST be set after load/filepath!
  ```

### 3.2 Physically Impossible PBR Albedo (`0.0` Black and `1.0` White)
* **Symptom:** Blown-out nuclear highlights, flat clay-like shadows, zero bounce light contrast, and persistent Cycles fireflies.
* **Root cause:** Agents routinely write `Base Color = (1.0, 1.0, 1.0, 1.0)` for white walls/snow or `(0.0, 0.0, 0.0, 1.0)` for black metal/tires. No real material reflects 100% or 0% of photons:
  * Fresh snow / white titanium paint: **linear `0.80 – 0.85`** (never `> 0.90`).
  * Charcoal / fresh asphalt / black rubber: **linear `0.03 – 0.05`** (never `< 0.02`).
  * Pure mirror (`Roughness = 0.0`): looks fake; even polished glass/chrome has microscopic roughness **`0.02 – 0.05`**.
  * `Metallic`: must be binary **`0.0` (dielectric)** or **`1.0` (conductor)** — intermediate values (`0.3–0.7`) are physically invalid except across dusty/oxidized transition masks.

### 3.3 Razor-Sharp 90° Edges (The #1 CG Giveaway)
* **Symptom:** Hard-surface objects look flat, paper-thin, and unmistakably synthetic because edges catch zero specular light.
* **Root cause:** Raw primitives (`primitive_cube_add`, boolean cuts) have mathematically infinite curvature at 90° edges. Real manufactured objects always have a micro-chamfer (`0.5mm – 5mm`).
* **Fix:** Every visible hard-surface mesh must have either:
  1. A **Bevel Modifier** at the end of its modeling stack:
     ```python
     bev = obj.modifiers.new(name="Bevel", type='BEVEL')
     bev.width = 0.003          # 3mm micro-bevel (adjust to asset scale)
     bev.segments = 2           # 2-3 segments
     bev.limit_method = 'ANGLE' # or 'WEIGHT'
     bev.angle_limit = math.radians(30)
     bev.harden_normals = True
     ```
  2. Or for static Cycles-only hero props, a `ShaderNodeBevel` (`samples=4, radius=0.003`) plugged into the `Normal` input of the `Principled BSDF`.

### 3.4 Z-Fighting & Depth Buffer Precision Collapse
* **Symptom:** Violent striped flickering on floors, decals, walls, or distant geometry.
* **Root causes:**
  1. **Coplanar faces:** Two surfaces share the exact same plane (e.g., floor at `z=0.0` and rug bottom at `z=0.0`, or duplicate overlapping objects created by a re-run script).
  2. **Extreme camera clip range:** Agents set `cam.data.clip_start = 0.0001` and `cam.data.clip_end = 100000.0` "just to be safe." Depth buffer precision scales with `clip_end / clip_start`. When that ratio exceeds `100,000`, floating-point Z-buffer precision collapses across the entire scene!
* **Fix:**
  * Offset thin overlays/rugs/decals by at least `0.001m – 0.002m` (or give them real thickness via `Solidify`).
  * Keep `cam.data.clip_start >= 0.05` (or `0.01` for macro close-ups) and `cam.data.clip_end <= 500.0` (`clip_end / clip_start <= 10,000`).

### 3.5 Shadow Terminator Artifact on Low-Poly Smooth Meshes
* **Symptom:** Dark, sawtooth-shaped bands along the light/shadow grazing boundary on smooth-shaded cylinders, spheres, and organic meshes in Cycles.
* **Root cause:** Smooth shading interpolates vertex normals across coarse polygons, causing the shading normal to face the light while the flat geometric triangle actually self-occludes the shadow ray.
* **Fix:**
  * Add a Subdivision Surface modifier or supporting loops on curved silhouettes, **or**
  * Increase the object's shadow terminator offset: `obj.shadow_terminator_offset = 0.1` (and `obj.shadow_terminator_geometry_offset = 0.1`).

### 3.6 Standard View Transform Clipping & Washed-Out AgX
* **Symptom:** Either highlights clip to ugly neon yellow/cyan (`Standard`), or the render looks flat and grey (`AgX` with default `Look = 'None'` and weak lighting).
* **Fix:** Always use `AgX` with a contrast look:
  ```python
  scene.view_settings.view_transform = 'AgX'
  scene.view_settings.look = 'AgX - Medium High Contrast'  # or 'AgX - Punchy'
  scene.view_settings.exposure = 0.0
  ```

### 3.7 Lighting & World Environment Blindness
* **Symptom:** Pitch-black renders, nuclear white blown-out frames, or metallic/glass materials rendering completely black.
* **Root causes:**
  * **Inverse-square falloff vs. scale:** A `10W` Point light inside a `20m` room is virtually invisible; a `5000W` Area light `0.2m` from an object blows out the frame.
  * **Zero environment reflections:** Dielectric gloss and metallic surfaces look dead black if `scene.world` has `Strength = 0` or is a flat `0.05` grey with no directional variation (`Sky Texture` or HDRI).
* **Fix:**
  * Pair key/fill/rim area lights (sized proportionally to the subject, with power scaled to distance squared: roughly `Power ≈ 15 * distance²` Watts for a key light at exposure `0`) with a subtle World shader (`ShaderNodeTexSky` type `'NISHITA'` / `'MULTIPLE_SCATTERING'` at `Strength = 0.1–0.3`, or an HDRI environment).

### 3.8 Missing UVs on Script-Generated Meshes
* **Symptom:** Image textures or UV-based procedural shaders render as a single uniform flat color across the entire mesh.
* **Root cause:** `mesh.from_pydata()` and raw `bmesh` extrusions do **not** generate UV coordinates (`len(mesh.uv_layers) == 0`).
* **Fix:** Either use `Texture Coordinate -> Object` with **Box projection** (`tex_node.projection = 'BOX'`, `projection_blend = 0.2`) for procedural/tiling materials, or create a UV layer and unwrap before assigning UV-mapped textures.

---

## 4. Scene Un-Optimization Traps (Performance & Memory Killers)

Agents routinely write naive Python that freezes Blender's viewport, balloons `.blend` files to gigabytes, or multiplies render times by 10x.

### 4.1 `bpy.ops` Inside Loops ($O(N^2)$ Dependency Graph Thrashing)
* **Why it's catastrophic:** Every `bpy.ops.mesh.primitive_*_add()`, `bpy.ops.object.duplicate()`, or `bpy.ops.object.modifier_apply()` call rebuilds selection caches, pushes an undo step, and forces a full scene dependency-graph resync. Creating 1,000 objects via `bpy.ops` takes ~45 seconds; creating them via `bpy.data` takes **< 0.05 seconds**.
* **Fix:** Never call `bpy.ops` inside a loop. Build the mesh once, then link instances via `bpy.data.objects.new(name, shared_mesh)` and `collection.objects.link(obj)`.

### 4.2 Duplicate Mesh Datablocks Instead of Instancing
* **Why it's catastrophic:** Creating 500 chairs, trees, bricks, or bolts with 500 separate `bpy.data.meshes` multiplies RAM/VRAM usage and BVH build time by 500x.
* **Fix:**
  * **10 – 2,000 repeats:** Share a single `bpy.types.Mesh` datablock across `bpy.data.objects.new(f"Prop_{i}", shared_mesh)` (Linked Duplicates), or instantiate a Collection via `inst = bpy.data.objects.new(name, None); inst.instance_type = 'COLLECTION'; inst.instance_collection = col`.
  * **2,000+ repeats (foliage, tiles, bolts, debris):** Use **Geometry Nodes** (`Instance on Points`) — never spawn tens of thousands of individual `bpy.types.Object` datablocks in the Outliner.

### 4.3 Subdivision Surface Explosion ($4^N$ Polygon Growth)
* **Why it's catastrophic:** Each Catmull-Clark level multiplies quad count by **4x** (`levels=5` = **1,024x** polygons!). Agents often set `subsurf.levels = 4` or `5` on dozens of objects or stack a Subdivision modifier after a high-segment Bevel modifier.
* **Fix:**
  * Keep `subsurf.levels <= 2` (viewport) and `subsurf.render_levels <= 3`.
  * Enable global scene protection:
    ```python
    scene.render.use_simplify = True
    scene.render.simplify_subdivision = 2
    scene.render.simplify_subdivision_render = 3
    ```

### 4.4 Material & Image Proliferation (`Wood.001` .. `Wood.300`)
* **Why it's catastrophic:** Calling `bpy.data.materials.new("Wood")` or `bpy.data.images.load(path)` inside an object creation helper creates hundreds of duplicate shader graphs and texture copies in VRAM, forcing EEVEE/Cycles to recompile identical shaders hundreds of times.
* **Fix:** Always use an idempotent get-or-create pattern:
  ```python
  mat = bpy.data.materials.get("M_Wood") or create_wood_material("M_Wood")
  img = bpy.data.images.load(filepath, check_existing=True)
  ```

### 4.5 Orphaned Datablock Memory Leaks
* **Why it's catastrophic:** Removing an object via `bpy.data.objects.remove(obj, do_unlink=True)` does **not** free its `Mesh`, `Material`, `Image`, or `NodeTree` datablocks. Across iterative agent edits, dozens of dead high-poly meshes and 4K textures accumulate in memory.
* **Fix:** At the end of every generation or cleanup pass, purge orphans recursively:
  ```python
  bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
  ```

### 4.6 Unconfigured Cycles & EEVEE Render Defaults
* **Why it's catastrophic:** Default Cycles renders on CPU with 4096 samples, no clamping, and reflective/refractive caustics enabled — turning a 5-second GPU render into a 15-minute noisy CPU render.
* **Fix:** Always configure GPU acceleration, adaptive sampling, denoising, light tree, bounce limits, and indirect clamping (`sample_clamp_indirect = 10.0`) before triggering a render.
