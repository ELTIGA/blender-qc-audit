---
name: blender-qc-audit
description: Audit and QC a Blender scene after you build, edit, import into, animate or simulate anything in it - and before you tell the user it is done. Runs a headless, read-only check of the saved .blend (floating, sunk and interpenetrating objects, support and tip-over, real-world scale, rigid body / cloth / soft body sims, falls that ease out, foot sliding, pops, camera framing and occlusion, black or blown renders, missing textures, wrong colour spaces, hidden helpers that still render, quaternion-mode rotations that do nothing, Blender 4.x-5.x API traps) and renders a camera view plus a "dollhouse" contact sheet to look at. Use it whenever you have run bpy code (blender -b, blender-mcp, a build script) that changed a scene, whenever the user asks to check, verify, review, debug, sanity-check or QC a .blend or a render that looks wrong, and whenever physical plausibility matters - even if they never say "QC".
---

# Blender QC audit

Scripts that run are not scenes that are right. Benchmarks keep finding the same pattern:
agent retry loops push bpy scripts to ~97% "executes" while geometry and placement quality stay
flat; the leftover errors are physical (floating or disconnected parts, interpenetration) and
spatial (orientation, framing, scale). Vision-model judges agree with humans only ~0.66 of the
time and miss physical errors entirely. And agents habitually declare "done" from the code they
wrote, or from one flattering render. (Sources: `references/llm-failure-modes.md`.)

So this skill measures the actual scene state with deterministic checks, then makes you look at
renders from several angles, then has you fix and re-measure. The order matters: numbers catch
what images hide (a 3 cm sink, a 6 mm gap, an object behind the camera), images catch what
numbers can't judge (composition, "does this look like what was asked").

## The loop

1. **Decide the physics intent** (below). Default is `realistic`.
2. **Save the scene.** The audit reads the .blend on disk - that is what will render and ship.
   An unsaved scene has nothing to audit and `//` relative paths cannot resolve.
3. **Run the audit**:
   ```bash
   python3 <skill-dir>/scripts/run_qc.py path/to/scene.blend --out-dir path/to/qc_out \
       [--intent intent.json] [--frames 1,mid,end] [--focus "Mug*"]
   ```
   It finds Blender itself (`--blender PATH` or `$BLENDER` to override), runs two separate
   headless processes, prints a summary, writes `qc.md` / `qc.json` / `render_report.json` and
   images, and exits 0 (no FAIL), 2 (FAILs) or 1 (the tool broke - read `blender_audit.log`).
   Typical runtime: seconds for small scenes, ~30 s for a 500-object set.
4. **Read `qc.md`, then look at every image it lists** (`camera_f*.png`, `contact_sheet.png`).
   The contact sheet is front / right / top / iso orthographic Workbench views with walls and
   ceilings hidden and each object in a random colour, so gaps, sinks and overlaps are visible.
   Use `--focus "<glob>"` for close-ups of a specific contact.
5. **Check the request, not just the audit.** List every explicit requirement in the user's
   prompt (objects, counts, colours, sizes, "left of", "on top of", camera, frame range) and
   verify each against `qc.json` → `inventory` (world bbox and `dims_m` in metres, material
   base colours as hex, and `camera_view.screen_xy` - x < 0.5 is the left of the frame *as the
   camera sees it*, which is what "left" means to the user, not world -X).
6. **Fix at the source and re-run.** Every FAIL gets fixed or explicitly waived; every WARN is
   either fixed or you can say why it is fine. If the scene came from a build script, fix the
   script and rebuild - hand-patching the .blend gets overwritten on the next run. Re-run until
   no FAIL remains, and re-look at the images after the last fix.
7. **Report honestly** (format at the end).

Live session instead of a file (e.g. a blender-mcp `execute_blender_code` tool)? Prefer saving
and running headless. If you can't, run the analysis in-process - it restores frame and
selection and never saves:
```python
import runpy
runpy.run_path("<skill-dir>/scripts/blender_qc.py", run_name="__main__",
               init_globals={"QC_ARGV": ["--out", "/tmp/qc/qc.json"]})
```
(`render_views.py` takes `QC_ARGV` the same way and restores every render setting it touches.)

## Physics intent: when to relax the physics checks

Physics is verified by default because most scenes are meant to be believable, and a viewer
notices a mug sunk into a table or a crate hovering 10 cm over it even when they can't say why.
Relax it only when the user asked for it or the context makes physics irrelevant:

| Situation | Intent |
|---|---|
| Interiors, products, architecture, characters, anything "realistic"/"photoreal" | `realistic` (default) |
| User asks for floating islands, levitation, magic, dream/surreal looks, cartoon squash-and-stretch, exploded views | `stylized`, or waive just those objects |
| Space / zero-g, underwater drift, abstract motion graphics, logo reveals, UI/infographic 3D, particle art | `off` or `stylized` - gravity and support don't apply |
| Specific deliberate exceptions (a hovering drone, a seated figure sinking into a cushion, a book glued to a wall) | keep `realistic`, waive those objects |

`stylized` downgrades physics findings one level (FAIL→WARN, WARN→INFO); `off` skips them. Non-physics
checks (materials, camera, render, hygiene) always run. Waived findings stay in the report as
INFO with the waiver reason - never delete the evidence, only explain it.

Intent file (all keys optional):
```json
{
  "physics": "realistic",
  "target": "render",
  "ground": "auto",
  "subjects": ["Hero*", "Product"],
  "allow": {
    "floating": ["Drone*", "Island_*"],
    "intersect": [["Figure*", "Chair*"], "Rug"],
    "scale": ["Giant_Mushroom"],
    "animation": ["Ghost"],
    "stability": [], "camera": []
  },
  "ignore": ["QC_*", "Helper*"],
  "tolerances": {"contact_m": 0.005, "penetration_m": 0.005},
  "expect": {"fps": 24, "frame_range": [1, 120], "resolution": [1920, 1080], "camera": "Cam_Main"},
  "notes": "User asked for a floating island; levitation is intentional."
}
```
- `target`: `render` (default) | `realtime` | `export` | `print` - stricter topology/UV/normals for the last three.
- `ground`: `auto` (flat, low, large or named floor/ground/terrain), an object name/glob, or `none`.
- `subjects`: what the camera must show. Listing them turns framing/occlusion findings into FAILs.
- Build scripts can embed waivers on objects instead: `obj["qc_allow"] = "floating,intersect"`.

## Triage guide

Severity is a starting point; you own the judgement. Read the evidence numbers.

| Finding | Usual cause | Fix |
|---|---|---|
| `physics.floating` / `wall_gap` | z placed by guess; origin not at the base; `transform_apply` moved origins | Snap: compute world-bbox bottom vs support top, move by the difference. Wall items: flush to the wall surface |
| `physics.intersection` (FAIL > 2 cm) | placement by centre not by bounds; scaled after placing; stacked at origin | Move apart or up by `depth`; re-run - neighbours may now collide |
| `physics.side_supported`, `unstable` | object glued to a wall; centre of mass past the edge | Give it a support or move it inward |
| `physics.scale` / `unit_mismatch` | primitives left at 2 m; cm/m import (scale 0.01 or 100) | Scale to the real size in the message; apply scale |
| `anim.fall_eases_out` | default Bezier keys make a drop decelerate into the floor | Last key VECTOR/LINEAR handles, or ease-in only, or simulate it |
| `anim.passes_through`, `pop`, `euler_flip`, `foot_slide` | keys without collision awareness; euler wrap; root/stride mismatch | Re-key around the obstacle; `Euler.make_compatible`; foot locks. Deep character issues: the `blender-motion-state-inspection` skill |
| `sim.*` | starting overlap, MESH shape on active bodies, no Collision modifier, gravity vs `scale_length`, cache shorter than the shot | See `references/physics.md` → sim gotchas |
| `camera.*` | aimed at the origin; inside a wall; subject behind something; DOF focused at the 10 m default | `to_track_quat('-Z','Y')` toward the subject's bbox centre, then re-check the render |
| `material.*`, `image.missing` | 4.0+ socket renames left links unmade; data maps tagged sRGB; texture with no UVs | `references/blender-api-changes.md` |
| `objects.hidden_but_renders` | `hide_set(True)`/`hide_viewport` don't affect F12 | `hide_render = True`, or delete the helper |
| `transform.rotation_mode_ignored` | wrote `rotation_euler` on a quaternion-mode object (common after imports) | Set `rotation_mode` first, or write the quaternion |
| `render` findings (blank, black, magenta, NaN, fireflies) | no light / black world / missing texture / bad shader | Fix the cause, then look at the new render |

Things the audit cannot decide for you: whether the composition is good, whether the object is
the *right* object, whether a waiver is honest. Look at the images. If something looks wrong
and the audit is silent, trust your eyes and measure it (`qc.json` inventory, or a short bpy
query) - the checks are heuristics with known limits (`references/physics.md` → limits).

Do not game the audit: renaming objects to dodge name-based checks, hiding things, widening
tolerances, or waiving what the user would call a mistake makes the report a lie.

## Writing or fixing bpy for this scene

The audit catches results; these keep you from producing them. Read `references/headless-gotchas.md`
before writing non-trivial headless bpy, and `references/blender-api-changes.md` when targeting
Blender 4.x-5.x (check `bpy.app.version` - training data lags the API). The ones that bite most:
- Run scripts as `blender -b file.blend --python-exit-code 1 --python x.py -- args`: the .blend
  before `--python`, the exit-code flag before `--python` (else exceptions exit 0), args after `--`.
- `bpy.ops.object.transform_apply()` defaults to location=True **and** rotation=True - it moves
  origins to the world origin. Pass `location=False, rotation=False, scale=True` when you only mean scale.
- Operators act on everything selected: deselect all, select explicitly, set the active object
  (or use `context.temp_override`). A leftover selection is how props end up skinned to an armature.
- `matrix_world`/`dimensions` are stale until `view_layer.update()`; `frame_current = n` does not
  evaluate - use `frame_set(n)`; simulations only advance when frames are stepped in order.
- Hiding in the viewport does not hide in the render; unlinked `bpy.data.objects.new()` objects
  and 0-user data vanish on save.
- 5.x: EEVEE is `BLENDER_EEVEE` again (not `_NEXT`), `Action.fcurves` is gone (channelbags),
  `scene.node_tree` is gone (`compositing_node_group`), GN modifier inputs moved to
  `mod.properties.inputs.<id>.value` (5.2), Principled sockets use 4.0 names.

## Report to the user

```markdown
## QC: <PASS | PASS with waivers | FAIL> - <scene/file>
Checked: <n> objects, physics=<intent> (<why>), Blender <ver>, frames <a-b>, sim stepped <yes/no>
Fixed this round: <what changed, with before → after numbers>
Remaining: <each open FAIL/WARN and what it means for the user>
Waived (intentional): <object - check - reason>
Not verified: <e.g. no GPU so camera render skipped; time budget hit; drivers blocked>
Evidence: <paths to camera render + contact sheet>
```
Keep it factual. "Looks good" without numbers or images is the failure mode this skill exists to stop.

## Files

- `scripts/run_qc.py` - wrapper (system Python): finds Blender, runs both stages, summarises, exit code.
- `scripts/blender_qc.py` - analysis inside Blender: scene/file, objects, geometry, materials,
  images, lights, camera, static physics (contact graph, support, stability, scale), animation
  sampling, simulation stepping, inventory. Output `qc.json` + `qc.md`.
- `scripts/render_views.py` - camera render(s) with image stats + Workbench contact sheet.
- `references/physics.md` - what each physics check computes, thresholds, sim gotchas, real-world sizes, light units, limits.
- `references/headless-gotchas.md` - CLI, context, depsgraph, rendering and saving traps (verified on 5.2).
- `references/blender-api-changes.md` - old → new API for 4.0-5.2.
- `references/llm-failure-modes.md` - benchmark and field evidence behind the checks.
