# How LLM agents fail in Blender - evidence behind this skill

Compiled 2026-10-25 from papers, benchmarks, GitHub issues and forum reports. [primary] = read in
the source; [forum] = user report (anecdote); [inferred] = synthesis.

## Headline findings

1. **Execution loops fix crashes, not correctness.** 3DCodeBench (DeepMind/USC, 2026, Blender
   5.0, 12,963 instances): agent harnesses raise executability 0.747 → 0.973 while shape metrics
   don't move; ~85% of the weakest models' crashes were 4.x → 5.0 API drift; scripts that run
   still produce "disconnected or floating" parts. Best single-shot executability: Claude Opus 4.7
   0.910, GPT-5.5 0.906, Gemini 3.1 Pro 0.725. [primary] arXiv 2606.01057
2. **Image metrics and VLM judges miss physical errors.** BlenderGym (CVPR 2025) metrics did not
   penalise a ball left stuck in a basket; the best VLM verifier agrees with humans 0.66 vs 0.79
   human-human. 3DSRBench: GPT-4o 21.6% on orientation questions vs humans 97.7%. LL3M: VLM critics
   "may still struggle" with spatial artifacts. ⇒ geometric checks must be numeric. [primary]
3. **Camera/viewpoint is its own weak spot.** VIGA/BlenderBench: GPT-4o one-shot camera task
   0.58/5. A blender-mcp user: Claude couldn't fix "most of the scene not being seen from the
   camera". Fixed single views turn 3D checks into 2D guesses. [primary][forum]
4. **Agents declare success early.** In a 2-hour donut test the agent called a flawed render
   final (sprinkles through the plate, cup clipping the donut, overexposed, then a magenta wash)
   and mistook the reference image for its own render. [forum: MindStudio 2026]
5. **API drift is the #1 crash cause**: `Specular`→`Specular IOR Level`, `BLENDER_EEVEE_NEXT`,
   missing `"Principled BSDF"`/`"Emission"` keys, `action.fcurves`, `scene.node_tree`. When the
   error persists, coders "fix" it by **deleting the failing lines** (LL3M), silently dropping
   features. [primary][forum]

## Benchmarks at a glance

| Work | Task | Measures | Notable failures |
|---|---|---|---|
| BlenderGym (2504.01786) | 245 scene edits: placement, lighting, material, blend shape, geometry | photometric loss, CLIP, Chamfer | open models fail to execute in >75% of geometry/material tasks; hallucinated differences; irrelevant edits in long scripts; verifier position bias |
| BlenderLLM / CADBench (2412.14203) | 700 text→bpy | GPT-4o judge on 4 renders | no-image rate GPT-4o 21-29%, Claude 3.5 16-27%; spatial (position/contact) scores 0.47-0.71 |
| 3DCodeBench (2606.01057) | Infinigen categories in Blender 5.0 | executability, SigLIP, Chamfer | see above |
| CodeGen-3D (IEEE Access 2026) | 100 Objaverse prompts | error rate, CLIP, GPT-4o judge | 21-92% error for general LLMs; CLIP and judge disagree |
| LL3M (2508.08228) | multi-agent asset generation | errors per asset | deprecated sockets; deleting failing lines; disconnected legs/backrests/caps; wrong handle orientation |
| SceneCraft (2403.01248) | LLM → scene graph → Blender | constraint score | baseline lines boxes up instead of stacking; lamps float mid-air |
| VLMaterial (2501.18623) | image → shader nodes | valid = executes and render > 12 KB | blank renders common for small models |
| SceneWeaver / PhyScene / Holodeck / LayoutGPT / NaLA | layout generation | collision rate, out-of-bounds, floating (support graph), walkability | numbers not comparable across papers; volume-weighted collision hides small props |

## Failure taxonomy → where the audit catches it

| # | Failure | Symptom | Check |
|---|---|---|---|
| 1 | API drift / hallucinated API | KeyError on sockets, enum errors, AttributeError | run with `--python-exit-code 1`; `references/blender-api-changes.md`; material link checks |
| 2 | "Fix by deletion" / partial edit | features silently missing | request-conformance step against `inventory` |
| 3 | Operator context errors | `poll() failed` | `references/headless-gotchas.md` §2 |
| 4 | Floating objects | lamp mid-air, prop hovering | `physics.floating`, `wall_gap`, contact sheet |
| 5 | Interpenetration | sprinkles through plate, cup in donut | `physics.intersection`, `enclosed`, `anim.passes_through` |
| 6 | Out of bounds | furniture through walls | `intersection` with architecture, `below_ground` |
| 7 | Disconnected parts | chair legs not touching seat | same-asset floating components, contact sheet |
| 8 | Orientation / facing / rotation ignored | windshield sideways; rotation "succeeds" but nothing moves | `rotation_mode_ignored`; look at iso/top views; check facing vs camera in the render |
| 9 | Scale & proportion | 2 m cups, 4.5 m doors, 100× imports | `physics.scale`, `unit_mismatch` |
| 10 | Relations ("on", "left of", stacked) | line instead of stack, wrong side | inventory bboxes + `camera_view.screen_xy` |
| 11 | Camera framing | subject out of frame / behind wall / behind camera | `camera.*` + camera render |
| 12 | Exposure / blank renders | black, blown, magenta | `light.none`, render stats |
| 13 | Material not showing | default grey, magenta | `material.*`, `image.missing`, colour-space checks |
| 14 | Evaluated-state blindness | ignoring modifiers/instances | audit reads the evaluated depsgraph + instances |
| 15 | Topology | non-manifold, n-gons, inverted normals | `geometry.*` (strict for realtime/export/print) |
| 16 | Scene hygiene | stacked duplicates, hidden helpers that render, default cube, orphan materials | `objects.*`, `material.unused` |

## Process failures and the counter-habit

| Failure | Counter-habit |
|---|---|
| Declares done without verifying | "Done" only after a QC pass with no FAIL **and** a render newer than the last edit that you looked at |
| Treats "it ran" as "it's right" | Separate execution, geometry and semantics; the audit covers the second, your eyes + the inventory the third |
| Over-trusts screenshots | Numbers for geometry, images for semantics and composition |
| Judges one angle | Camera view + front/right/top/iso contact sheet; `--focus` for close-ups |
| Doesn't re-read state | Re-run the audit after every fix round; diff findings against the previous run |
| Loops of regressions | Fix in the source script; cap iterations; compare finding counts round to round |
| Confuses reference and render | Note every image's path and timestamp in the report |

## Selected user reports (paraphrased)

- blender-mcp #93: windshield fitted sideways, coordinate-system misuse. #110 / #26: missing node
  keys, EEVEE enum rejected, undefined `Vector`. #61: camera missing most of the scene. #56:
  rotating quaternion-mode imports reports success, nothing moves. #96: prints swallowed. #190
  (5.0): repeated material updates duplicate Output/BSDF nodes → default grey renders.
- BlenderArtists 2025: models loop on errors, "nothing seems to know about 4.X", fake confidence.
- HN 2025-26: triangle-soup output; agents stall at primitives; requests for render→critique loops.

Coverage gaps during research: Reddit was unreachable; no user incident reports were found for
deleted user data or everything-at-origin (those checks rest on docs and the failure mechanics).
