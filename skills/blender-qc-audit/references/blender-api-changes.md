# Blender Python API changes 4.0 → 5.2 that generated code still gets wrong

Check `bpy.app.version` first; write version guards where code must span versions. Access
sockets and enums **by name**, never by index (indices shift between releases).
Marks: [5.2] verified locally on 5.2.3; [docs] release notes
(`https://developer.blender.org/docs/release_notes/<ver>/python_api/`).

| Area | Old (what LLMs write) | Current | Since |
|---|---|---|---|
| Principled BSDF | `inputs["Specular"]` | `"Specular IOR Level"` | 4.0 [5.2] |
| | `"Emission"` | `"Emission Color"` - and **`"Emission Strength"` defaults to 0**, so set both | 4.0 [5.2] |
| | `"Transmission"` / `"Subsurface"` / `"Clearcoat"` / `"Sheen"` | `"Transmission Weight"` / `"Subsurface Weight"` / `"Coat Weight"` (+ Coat Roughness/IOR/Tint/Normal) / `"Sheen Weight"` | 4.0 [5.2] |
| | `"Subsurface Color"` | removed - use Base Color | 4.0 |
| | `"Specular Tint"` float | colour | 4.0 |
| | `inputs[5]` etc. | index meaning changed (5.2 has `"Thin Wall"` early in the list) | [5.2] |
| Material / World | `mat.use_nodes = True` | always on; deprecated no-op (DeprecationWarning, removal in 6.0). New materials already have Principled + Output | 5.0 [5.2] |
| EEVEE material | `blend_method`, `shadow_method` | `surface_render_method`, (shadows per light/object) | 4.2 |
| Render engine | `'BLENDER_EEVEE_NEXT'` | `'BLENDER_EEVEE'` (5.0+); `_NEXT` only valid 4.2-4.5 | 5.0 [5.2] |
| EEVEE settings | `use_bloom`, `use_ssr`, `use_soft_shadows`, `use_gtao` | removed (bloom → compositor Glare; raytracing options) | 4.2-5.0 |
| Compositor | `scene.use_nodes = True; scene.node_tree` | `tree = bpy.data.node_groups.new(n, "CompositorNodeTree"); scene.compositing_node_group = tree` + Group Output | 5.0 [5.2] |
| Compositor | Render Layers `"Z"`, `"IndexMA"`, `"DiffCol"`; output `"RGBA"` | `"Depth"`, `"Material Index"`, `"Diffuse Color"`; `"Color"` | 5.0 |
| File Output node | `base_path`, `file_slots`, `layer_slots` | `directory`, `file_name`, `file_output_items` | 5.0 |
| Video output | `file_format = 'FFMPEG'` directly | `image_settings.media_type = 'VIDEO'` first | 5.0 [5.2] |
| Animation | `action.fcurves`, `action.groups`, `action.id_root` | `bpy_extras.anim_utils.action_get_channelbag_for_slot(action, slot).fcurves` / `action_ensure_channelbag_for_slot`; `channelbag.fcurves.ensure(...)` | removed 5.0 (slots 4.4) [5.2] |
| Animation | `ad.action = act` and done | also `ad.action_slot = act.slots[0]` if not auto-assigned (else nothing animates). `keyframe_insert` handles slots for you | 4.4 [5.2] |
| Animation | `fcurves.new(..., action_group=)` | `group_name=` | 4.4 |
| Geometry Nodes modifier | `mod["Socket_2"] = 5.0` | `mod.properties.inputs.Socket_2.value = 5.0` (`.type="ATTRIBUTE"`, `.attribute_name`); identifiers from `interface_socket.identifier` | 5.2 [5.2] |
| Node groups | `tree.inputs.new(...)` / `tree.outputs` | `tree.interface.new_socket(name, in_out='INPUT', socket_type='NodeSocketFloat')`; iterate `tree.interface.items_tree` | 4.0 [5.2] |
| Mesh smoothing | `mesh.use_auto_smooth`, `auto_smooth_angle`, `calc_normals_split()` | `bpy.ops.object.shade_smooth_by_angle(angle=…)`, `shade_auto_smooth()` (adds a modifier), `mesh.set_sharp_from_angle(angle=…)`, `mesh.corner_normals` | 4.1 [5.2] |
| Mesh attributes | `edge.bevel_weight`, `edge.crease`, face maps, `calc_normals()` | attributes `bevel_weight_edge/vert`, `crease_edge/vert`; face maps removed | 4.0 |
| Colour attributes | `mesh.vertex_colors.new()` | `mesh.color_attributes.new(name, 'FLOAT_COLOR', 'POINT')` (`vertex_colors` still exists, makes BYTE corner colours) | 3.2+ [5.2] |
| Operators | `bpy.ops.x({"object": o})` override dict | `with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o]): bpy.ops.x()` | removed 4.0 [5.2] |
| OBJ / PLY / STL | `bpy.ops.import_scene.obj`, `export_scene.obj(use_selection=True)`, `import_mesh.stl` | `bpy.ops.wm.obj_import/obj_export(export_selected_objects=True, forward_axis=, up_axis=, apply_modifiers=)`, `wm.ply_*`, `wm.stl_*` | 4.0-4.2 [5.2] |
| Collada | `wm.collada_import/export` | absent in 5.2 | ≤5.2 [5.2] |
| Images as planes | `addon_enable('io_import_images_as_planes')` | core `bpy.ops.image.import_as_mesh_planes` | 4.2 [5.2] |
| Add-ons | `bl_info` | extensions + `blender_manifest.toml` | 4.2 |
| Drawing | `import bgl`; `image.bindcode` | `gpu` module; `gpu.texture.from_image`; headless needs `gpu.init()` (5.2) | 5.0 / 5.2 [5.2] |
| ID vs RNA props | `scene['cycles']`, `del obj['addon_prop']` | `scene.cycles.*`; `obj.property_unset('addon_prop')` | 5.0 [5.2] |
| Boolean modifier | `solver = 'FAST'` | `'FLOAT'` | 5.0 |
| Armature | `bone.select`, bone layers, `bone_groups` | pose/edit bone selection; bone collections | 5.0 / 4.0 |
| Light probes | `'CUBEMAP'/'PLANAR'/'GRID'` | `'SPHERE'/'PLANE'/'VOLUME'` | 4.1 |
| Python | 3.10/3.11 | 3.13 (bpy PyPI wheel pins `==3.13.*`) | 5.1 |
| Operator subclasses | custom `__init__` without super | must call `super().__init__(*args, **kwargs)` | 4.4 |
| Math | `Matrix * Matrix`, `Matrix * Vector` | `@` (the `*` form is element-wise and silently wrong for matrices) | 2.8 [5.2] |

Colour management names in 5.2: view transforms `Standard, AgX, Filmic, Filmic Log, Khronos PBR
Neutral, ACES 1.3, ACES 2.0, False Color, Raw`. Look names carry the view-transform prefix and
are only valid after that transform is set: with AgX, `None, AgX - Punchy, AgX - Greyscale,
AgX - Very High Contrast, AgX - High Contrast, AgX - Medium High Contrast, …`; a bare `Punchy`
or `High Contrast` raises. Set `view_transform` first, then `look`. Colour spaces: `sRGB`,
`Linear Rec.709`, `Non-Color`. [5.2]

When unsure, probe instead of guessing:
```bash
blender -b --factory-startup --python-expr "import bpy; m=bpy.data.materials.new('t'); \
print([i.name for i in m.node_tree.nodes['Principled BSDF'].inputs])"
```
