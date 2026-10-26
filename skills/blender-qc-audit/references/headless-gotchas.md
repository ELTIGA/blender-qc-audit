# Headless Blender gotchas (verified on Blender 5.2.3 LTS unless marked)

Read before writing non-trivial bpy that runs with `blender -b`. Tags: **[5.2]** reproduced locally
on 5.2.3 with `-b --factory-startup`; **[docs]** official manual / release notes; **[forum]** user
reports; **[inferred]** reasoning, not measured.

## Contents
1. Process and command line
2. Context, operators, selection
3. Depsgraph and evaluation
4. Rendering headless
5. Saving, paths, data lifetime
6. Units, scale, axes, import/export
7. Agent-specific traps (blender-mcp, logs)

---

## 1. Process and command line

- **Arguments execute in order.** `blender -b file.blend --python x.py` runs the script on the
  file. `blender -b --python x.py file.blend` runs it on the *startup* scene (default Cube,
  `bpy.data.filepath == ''`) and loads the file afterwards. Same for `-o`/`-f`: set output before
  `-f`, after the file. [docs][5.2]
- **Exceptions exit 0 by default.** Pass `--python-exit-code 1` *before* `--python`; after it the
  exit code is still 0. Even then, some failures exit 0 (a caught `//` save error) and some exit 1
  when caught (`Cannot render, no camera`). Verify by checking output files/JSON, not exit codes. [5.2]
- **Script args go after `--`**: `sys.argv[sys.argv.index("--")+1:]`. Without `--`, Blender tries
  to open `--foo` as a file. Use `parse_known_args` if Blender flags such as `--cycles-device`
  (only read after `--`) share the tail. [docs][5.2]
- **Autoexec is off** in background. Simple and sandbox-safe driver expressions still evaluate;
  drivers that touch `bpy`/context stay at 0 with `BPY_driver_exec: restricted access…`.
  Detect with `bpy.app.autoexec_fail`. Enable with `--enable-autoexec` for trusted files. [5.2]
- **`--factory-startup`** skips user prefs and startup.blend (reproducible runs). Bundled add-ons
  (cycles, glTF, FBX…) stay on; user/extension add-ons don't load - enable explicitly. Cycles GPU
  settings live in prefs, so set them in the script each run. [5.2]
- **No event loop**: `bpy.app.timers` callbacks never fire before a `-b` script returns; call work
  directly. blender-mcp refuses to start in `-b` for this reason. [5.2][docs]
- `stdout` is buffered when piped, so tracebacks can print before earlier `print`s. Use
  `print(..., flush=True)` or write results to a file. Blender ignores `PYTHONPATH` unless
  `--python-use-system-env`. [5.2]
- 5.0 changed the log format (render progress lines) - don't scrape logs. [docs]

## 2. Context, operators, selection

- `poll() failed, context is incorrect` - background has a window/screen but `context.area`,
  `region`, `space_data` are `None`. Many View3D ops still work under
  `with bpy.context.temp_override(window=w, area=a, region=r):` using the VIEW_3D area of
  `w.screen`. `render.opengl` and screenshots never work headless. [5.2]
- **Override dicts were removed in 4.0** (`bpy.ops.x({...})` → `ValueError: 1-2 args execution
  context is supported`). Use `context.temp_override(...)`. [docs][5.2]
- **Selection leaks into operators.** Operators act on `context.selected_objects`; a leftover
  selection gets parented, joined, deleted or skinned along with the target (real case: props
  deformed by a character armature after `parent_set(type='ARMATURE_AUTO')`). `primitive_*_add`
  deselects others and makes the new object active; `bpy.data.objects.new` changes neither.
  `select_set(True)` on a hidden object silently does nothing. Deselect all, select explicitly,
  set `view_layer.objects.active`. [5.2]
- **`bpy.ops.object.transform_apply()` defaults to `location=True, rotation=True, scale=True`.**
  "Apply scale" written as `transform_apply(scale=True)` also moves every origin to the world
  origin, so later code that reads `obj.location` (aiming cameras, placing on top of) uses
  (0,0,0). Use `transform_apply(location=False, rotation=False, scale=True)`. [5.2 - found by this
  skill's own test fixtures]
- **`child.parent = p` doesn't set `matrix_parent_inverse`**, so the child jumps by the parent's
  transform. Set `child.matrix_parent_inverse = p.matrix_world.inverted()` after
  `view_layer.update()`, or restore `matrix_world`. [5.2][forum]
- **Edit-mode data is stale** until `obj.update_from_editmode()` or leaving Edit Mode; bmesh needs
  `ensure_lookup_table()` before indexing. Saving in Edit Mode reopens in Edit Mode. [5.2]
- **Names are not guaranteed** ("Cube.001"); keep object references rather than looking up by the
  name you asked for. Old references die after file load / `read_factory_settings` / undo
  (`ReferenceError: StructRNA … has been removed`). [docs][5.2]
- **2.7x API in LLM output**: `scene.objects.link`, `obj.select = True`, `scene.update()` raise.
  `Matrix * Matrix` does **not** raise - it is element-wise and silently wrong. Use `@`. [5.2]
- **Rotation mode**: imported assets are often `QUATERNION`; writing `rotation_euler` then does
  nothing and reports no error. Check `obj.rotation_mode`. [forum: blender-mcp #56]

## 3. Depsgraph and evaluation

- `matrix_world` and `dimensions` are stale after setting `location`/`scale` until
  `bpy.context.view_layer.update()`. [docs][5.2]
- `obj.bound_box` (after an update) already includes modifiers; `obj.data` does not. Evaluated
  geometry: `dg = context.evaluated_depsgraph_get(); oe = obj.evaluated_get(dg); me = oe.to_mesh();
  …; oe.to_mesh_clear()`. `BVHTree.FromObject` returns **local** coordinates - transform to world
  (or build with `FromPolygons` from world vertices) before comparing objects. [5.2]
- Objects with `hide_viewport=True` are not evaluated in background; `bmesh.from_object` raises
  `has no usable mesh data`. Fall back to `obj.data`. [5.2]
- `scene.frame_current = n` does not evaluate animation; `scene.frame_set(n)` does. [5.2]
- **Simulations only advance when frames are stepped in order** from the cache start. A cold
  `frame_set(60)` returns the un-simulated pose (rigid body) or garbage (cloth: through the floor).
  Jumping past the cached range returns the last cached value - stale but plausible. Bake
  (`with temp_override(scene=sc): bpy.ops.ptcache.bake_all(bake=True)`) for random access, and
  free/re-bake after any edit: bakes are not invalidated by edits. [5.2]
- Rigid body poses live in `matrix_world`; `obj.location` never changes during a sim. Skinned
  meshes' `matrix_world` never moves either - read pose bones or evaluated vertices. [5.2]

## 4. Rendering headless

- **Engine ids**: `BLENDER_EEVEE` (≤4.1) → `BLENDER_EEVEE_NEXT` (4.2-4.5) → `BLENDER_EEVEE` (5.0+).
  Guard with `bpy.app.version`. Dynamic enums look empty under introspection
  (`enum_items` lists only EEVEE) - read the assignment error instead. [docs][5.2]
- **EEVEE/Workbench need a GPU context** even with `-b`: fine on macOS (Metal); Linux falls back to
  headless EGL (needs `EGL_MESA_platform_surfaceless`), else use Cycles CPU or `xvfb-run`.
  EEVEE Next on llvmpipe/vGPU: unverified. [docs][forum]
- `gpu` module in `-b` raises "requires the gpu module to be initialized" - 5.2 added `gpu.init()`.
  `bgl` and `Image.bindcode` were removed in 5.0. [docs][5.2]
- **Cycles device**: on macOS prefs say METAL but `scene.cycles.device` is still CPU → silent CPU
  renders. Recipe: `p = bpy.context.preferences.addons['cycles'].preferences;
  p.compute_device_type = 'METAL'|'OPTIX'|'CUDA'|'HIP'; p.get_devices(); for d in p.devices: d.use = True;
  scene.cycles.device = 'GPU'`. First Metal GPU render can stall 70-100 s compiling kernels with no
  log line - use long timeouts. [5.2]
- **`bpy.ops.render.render()` writes nothing without `write_still=True`.** In `-b` the "Render
  Result" image has no pixels; save to a file and reload it to inspect. [5.2]
- 5.0: set `image_settings.media_type = 'VIDEO'` before `file_format = 'FFMPEG'` (else TypeError). [docs][5.2]
- **Black render checklist**: no `scene.camera` (`read_factory_settings(use_empty=True)` and new
  scenes have none); `film_transparent` (alpha 0 looks black in many viewers); world strength 0 or
  no world; lights at `bpy.data.lights.new()` default energy 10 W (near-black at room scale; the
  startup point light is 1000 W) and sun default 10 W/m² from `lights.new` vs 1.0 from `light_add`;
  object/collection `hide_render`; camera `clip_end` 100 m. [5.2]
- **Colour management**: AgX is the default view since 4.0 and desaturates strong colours (linear
  0.8,0.05,0.05 → display 0.80,0.31,0.27). Use `view_transform='Standard'` when exact brand colours
  matter. Colour space `'Linear'` is invalid - `'Linear Rec.709'`; data maps `'Non-Color'`. A
  missing texture's magenta turns dull purple under AgX + dim light. [docs][5.2]
- Expensive defaults: Cycles 4096 samples, EEVEE 64, 1920×1080, output `/tmp/`. Set them. [5.2]
- 5.0 compositor: `scene.node_tree` removed → `scene.compositing_node_group`; `scene.use_nodes`
  is a deprecated no-op. [docs][5.2]

## 5. Saving, paths, data lifetime

- `save_mainfile()` on a never-saved session raises; use `save_as_mainfile(filepath=<absolute>)`.
  Second save writes `.blend1` (prefs `save_version`). `copy=True` saves without retargeting. [5.2]
- **0-user data is dropped on save**: materials created but not assigned, `bpy.data.objects.new()`
  never linked to a collection. `use_fake_user=True` keeps data. [5.2]
- `//` paths with an unsaved file resolve against the CWD and renders then fail to write. Save
  first or use absolute paths. 4.5+: output paths support templates (`{blend_name}`), so literal
  braces are special. [5.2][docs]
- Fluid caches in an unsaved file default to a temp dir that vanishes at exit - set an absolute
  `cache_directory`. GN simulation bakes default to PACKED in 5.2. [5.2]
- A factory-fresh file already lists a bundled brush .blend as a dependency and may carry a
  "Dots Stroke" material when not using factory startup - don't report those as user problems. [5.2]

## 6. Units, scale, axes, import/export

- Changing `unit_settings` changes display, not geometry. Keep `scale_length = 1.0` and model in
  metres; `scene.gravity` is **not** rescaled with `scale_length` (cm scenes fall 100× slow). [5.2]
- Unapplied scale: mesh verts stay small while `dimensions` grow; bevel/solidify widths and
  modifiers work in local space. cm-based FBX imports arrive with object scale 0.01 (or 100× big).
  Check `obj.scale` after import and apply scale. [5.2][forum]
- glTF is Y-up (exporter `export_yup=True` converts); glTF `export_apply` defaults to **False**
  (modifiers not baked). FBX: `axis_forward='-Z', axis_up='Y'`. A glTF round trip changes vertex
  counts (seam splits) - compare dimensions/tri counts, not vertex counts. [5.2]
- 4.0: `import_scene.obj`/`export_scene.obj` → `wm.obj_import`/`wm.obj_export` (kwargs changed:
  `export_selected_objects`, `forward_axis`, `up_axis`, `apply_modifiers`); PLY/STL moved to `wm.*`;
  Collada import/export absent in 5.2. FBX/glTF keep old-style kwargs. [docs][5.2]

## 7. Agent-specific traps

- blender-mcp runs in a GUI session over a socket; its `execute_blender_code` returns only "Code
  executed successfully" for some versions - prints are swallowed, so return data explicitly.
  Long operations time out; split them. It cannot run in `-b`. [docs][forum]
- Repeated scripted material updates can create duplicate Output/BSDF nodes; only the *active*
  Material Output renders, so new links may go to an inactive copy (renders default grey).
  Reuse nodes by type, remove duplicates. [forum: blender-mcp #190]
- When an error appears, do not "fix" it by deleting the failing lines - that silently drops the
  feature (LL3M observed this). Re-check the plan's checklist after every fix.
- Snapshot scene state (names, transforms, materials) before and after a script and diff it;
  don't trust "it ran" or the script's own echo.
