# Physics verification: what the audit computes, thresholds, gotchas, limits

## Contents
1. Contact model (touching vs intersecting vs floating)
2. Support graph, wall mounts, stability
3. Real-world scale
4. Animation physics
5. Simulation stepping (rigid body, cloth, soft body, fluids, GN)
6. Lights and cameras in physical units
7. Limits - when the numbers lie

All distances are reported in metres (`scene.unit_settings.scale_length` is applied). Geometry is
the **evaluated** mesh (modifiers applied) in **world space**; instances from geometry nodes /
collection instances are expanded (first 400). Volume-only materials (haze, fog) and emission-only
cards/backdrops are not treated as solids.

## 1. Contact model

For every pair whose bounding boxes come within the contact tolerance:

- **Intersect test**: world-space BVH triangle overlap. Then a **depth** estimate:
  - closed (watertight) other object: sample points of the overlapping triangles (vertices +
    centroids), ray-parity inside test (two skewed rays, both must agree), depth = distance to
    exit along the axis of least bbox overlap - the direction you would push it out. This gives a
    true 3 cm for a mug sunk 3 cm into a 4 cm table top (nearest-surface distance would say 1 cm).
  - open other object (planes, single-sided walls, imported meshes with split vertices): two-sided
    signed distance; depth = the smaller of the two crossing depths, so normal direction doesn't matter.
- **Contact**: overlap with depth ≤ penetration tolerance, or no overlap but surfaces within the
  contact tolerance. Distance uses points sampled across triangle *faces*, not just vertices -
  two rotated low-poly boxes 2 mm apart have no vertex near the other's face.
- **Enclosed**: no surface crossing but one object's centre is inside the other (hidden inside).
- **Coplanar same-facing faces** ≥ 1 cm² → z-fighting warning (a rug plane exactly on a floor).
  Opposite-facing coplanar faces are a clean contact (a box resting on a floor).

Tolerances (defaults, override with `intent.tolerances`):
- contact: `min(5 mm, 10% of the smaller object's largest size)`, floor 0.5 mm
- penetration: `min(5 mm, 10% of the smaller object's thinnest size)`, floor 1 mm; soft or
  compressible names (rug, cushion, bed, sofa, cloth, grass, snow, figure/body…) allow 3 cm.

Severity of an intersection between different assets:
- FAIL: depth > 2 cm, or > 50% of the thinner object's extent along the push-out axis (when that
  extent ≥ 1 cm). Soft pairs FAIL above 6 cm. Embedded in walls/architecture FAIL above 5 cm.
- WARN: anything above tolerance but below those.
- Parts of the **same asset** (same parent hierarchy, or name prefix like `Table_Top`/`Table_Leg_1`)
  are reported once per asset as INFO "modelled joins" (WARN if only name-grouped and > 2 cm).
  Two copies (`Chair.001`, `Chair.002`) are never the same asset.
- Architecture vs architecture (walls, baseboards, window/door frames) = INFO.

Why per object, not volume-weighted: volume weighting (as some scene-generation papers do) hides
small props clipping through big ones, which is exactly what viewers notice.

## 2. Support graph, wall mounts, stability

- Contact/intersect/enclosed relations form a graph. The **ground** set = flat, large, low objects
  or names like floor/ground/terrain (or `intent.ground`), plus room shells (an object whose bbox
  holds most others). With no ground, the lowest object cluster is the base.
- Any connected component not reaching the ground **floats**. Reported with the gap to the surface
  below (downward rays) and the nearest surface within 2 cm.
  - FAIL by default; WARN if the gap ≤ 1 cm (and < half the object's height), if something is
    within 2 cm (near miss), or if the name suggests something airborne (cloud, bird, balloon…).
  - If it hangs within 5 cm of a vertical wall surface → `wall_gap` WARN (wall-mounted item with
    no fixing modelled).
  - Animated or simulated objects are skipped here (checked over time instead).
- **Side-supported**: a small (< 0.6 m) object in the grounded graph whose contacts are all
  beside/above it, not under it, and not part of the same asset and not a wall-mount type (frame,
  clock, shelf, sconce…) → WARN: it would fall unless glued.
- **Stability**: for objects resting on supports below, contact points within tolerance form a
  footprint (2D convex hull). Centre of mass (uniform density; volume-weighted for closed meshes)
  outside the footprint by > 3% of size → WARN "would tip over". Verified against real sims
  during research: geometry-COM tip predictions matched Bullet when origins were at the COM.

## 3. Real-world scale

Name-based: the head noun of the asset name (`Coffee_Cup` → cup, `Table_Top`+legs → table via the
group; `desk_top` alone is a *part* and is skipped) is matched against a table of generous ranges:

| Object | Metric | Range |
|---|---|---|
| door | height | 1.8-2.6 m (interior leaf ~2.0-2.1) |
| table, desk | height | 0.3-1.15 m (dining 0.71-0.76, desk 0.72-0.75) |
| chair, stool | height | 0.4-1.3 m (seat 0.43-0.48) |
| sofa/couch | length | 1.2-3.6 m |
| bed | length | 1.3-2.5 m |
| person/character/figure | largest | 0.9-2.2 m (adult 1.5-1.95) |
| mug/cup | largest | 5-20 cm (mug ~9-11 cm tall) |
| bottle / book / laptop / phone | largest | 8-50 / 8-50 / 25-45 / 10-20 cm |
| car / truck/bus | length | 2.5-6.5 / 4-20 m |
| tree / building | height | 1.5-70 / 2.5-900 m |
| counter | height | 0.8-1.15 m (EU 0.85-0.95, US 0.914) |
| lamp / window / plate / ball / vinyl LP | … | see `SIZE_TABLE` in `blender_qc.py` |

Outside the range → WARN; off by > 3× → FAIL; several objects off by > 20× in the same direction →
`unit_mismatch` FAIL (cm/m import or `scale_length`). Ratios between objects matter too (seat ~0.25-
0.32 m below table top, character ~0.85-0.95 of door height) - eyeball those in the contact sheet.

## 4. Animation physics

Sampled with `frame_set` across the frame range (≤ 120 samples) for keyframed / constrained /
driven objects (simulated objects are handled in §5):
- **Pop / teleport**: speed > 5 m/s and > 8× the median speed in one step.
- **Rotation snap**: > 60° between samples and > 5× the median; plus **euler flips** read from the
  rotation F-curve keys (|Δ| > ~171° within 3 frames) - integer frames can look fine while motion
  blur and subframes spin.
- **Falls**: for each monotonic descent ≥ 0.3 m (or ≥ half the object height):
  - `fall_eases_out` WARN if the last quarter is markedly slower than the peak - a falling object
    hits at its fastest; default Bezier keys decelerate into the floor (the classic "floaty" drop).
  - `fall_constant_speed` INFO if it never accelerates; `fall_timing` INFO if the duration is
    outside 0.4-2.5× of free fall `t = sqrt(2h/g)`.
- **Passes through**: the moving object's transformed mesh vs static objects at ~25 sampled frames
  (pairs that already intersect at rest are reported once, statically).
- **Never touches**: an animated object that touches nothing in any sample (unless enclosed in
  another object, e.g. blobs in a lava lamp, or airborne by name).
- **Skinned characters**: the mesh object never moves, so evaluated vertices are sampled: dips
  below the ground (FAIL) or never within 3 cm of it (WARN "hovers"). Foot bones (`foot`, `toe`,
  `heel`, `ball`) that move > 5 cm in total while planted → `foot_slide`. For deeper character
  work use the `blender-motion-state-inspection` skill.

Thresholds for judging by eye: 1-2 cm ground penetration is visible; planted feet should move
< 0.5 cm/frame; rigid-body free fall reads ~2.5% below 9.81 because of default damping.

## 5. Simulation stepping

The audit steps frames **in order** from `frame_start` (up to `--sim-frames`, default 250) and
runs before the animation pass, because frame jumps leave stale cache entries. Findings:
- **Pre-sim lint**: gravity in m/s² after unit scale (Blender does *not* rescale gravity with
  `scale_length`); `time_scale` ≠ 1 (apparent g × time_scale²); cache shorter than the scene;
  MESH collision shape on active bodies (slow, unstable, rests `collision_margin` - 4 cm by
  default - above surfaces); animated scale on an active body (sinks/floats); origin far from the
  geometry centre (**Bullet uses the origin as the centre of mass** - the body tumbles wrongly;
  `origin_set(type='ORIGIN_CENTER_OF_VOLUME')`); density outside 5-25000 kg/m³ (water 1000, wood
  500-900, steel 7850; all-default 1 kg masses noted); bodies < 2 cm (stacks of 1 cm cubes collapse
  at default 10 substeps/10 iterations - need ~100 of each); starting interpenetration (two
  cubes overlapping 0.5 m ended 39.6 m apart in testing); cloth/soft body with no Collision
  modifier anywhere (falls through everything); unbaked fluid domains (render empty headless).
- **Stepping results**: `sim.explosion` - speed exceeds what gravity allows for the drop so far
  (`1.3·sqrt(2·g·drop) + 3 m/s`); `fell_through` - ends below the ground (tunnelling: keep
  `speed / (fps × substeps)` under half the thinnest collider; never use zero-thickness planes for
  fast objects); `left_scene`; `not_settled` (INFO); final-state penetration; cloth exploded
  (> 3× size), cloth/soft body below ground, soft body collapsed (< 50% height - default soft
  bodies have no goal or stiffness and pancake).
- Baked caches are read as-is (that is what renders) with a reminder that bakes are not
  invalidated by edits. Unapplied scale on rigid bodies did **not** reproduce as a problem in
  testing (INFO only); it still matters for cloth settings, MESH shapes and exports.

## 6. Lights and cameras in physical units

- Point/spot/area `energy` is **radiant watts**, not bulb watts: an 800 lm LED bulb ≈ 2.1 W, a
  1000 lm bulb ≈ 2.9 W, a candle ≈ 0.05 W (manual table). A "1000 W" point light is a stadium lamp.
  Sun strength is irradiance W/m²: clear sky ~1000 (needs about -8.3 EV of exposure), artists
  commonly use 1-10 at EV 0. Either convention is fine; **mixing them** (1000 W/m² sun with 10 W
  bulbs) gives wrong relative brightness - compare irradiance at the subject: E = P / (4π d²) for a
  point light, rendered L ≈ albedo · E / π.
- Defaults: `bpy.data.lights.new()` → energy 10 for every type (sun too); `light_add()` → 10 W
  point/spot/area, 1.0 sun. Camera: 50 mm, 36 mm sensor, clip 0.1-1000 m (5.2), DOF focus 10 m.
- The audit flags: no light source at all (FAIL), zero-energy lights, sun outside 0.05-50,
  > 100 kW lamps, lights inside closed opaque meshes; camera inside a mesh, subject out of
  frame / cropped / tiny / occluded (rays start past `clip_start`, against render-visible solids,
  ignoring glass and volumes), `clip_end` cutting geometry, DOF focus > 35% off every visible subject,
  horizon roll > 2°.

## 7. Limits - when the numbers lie

- **Name heuristics**: scale, soft-contact, wall-mount, airborne and architecture rules read object
  names. A table named `Cube.004` gets no scale check; a book named `Rug_Book` gets soft allowance.
  Name your objects meaningfully - it also makes reports readable.
- **Open/non-manifold meshes** (imported with split vertices, single planes) can't use the parity
  inside test; depth falls back to two-sided distance and enclosure isn't detected.
- **Thin or tiny geometry** below ~1 mm, hair/curves without bevel, point clouds and volumes are
  not checked physically.
- **Ground detection** assumes Z-up and a roughly flat floor; terrain should be named or set via
  `intent.ground`.
- **Intent is yours to set.** The audit cannot know that a hovering object is a magic effect;
  you can, from the user's request. Record waivers with a reason.
- **Time budget** (default 300 s) truncates pairwise checks on huge scenes - the report says so.
- **Sim checks** step at most `--sim-frames` frames; long sims may need a bake and a second pass
  at a later frame.
