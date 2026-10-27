# Blender Modeling Expert

## Patterns


---
  #### **Id**
topology-for-deformation
  #### **Name**
Topology for Deformation
  #### **Description**
    Edge loops must follow muscle flow and joint rotation axes. This isn't
    optional - it's physics.
    
  #### **When To Use**
Any mesh that will be rigged or deformed
  #### **Implementation**
    ## Edge Loop Placement Rules
    
    ### Joint Areas (Elbows, Knees, Fingers)
    - Minimum 3 edge loops at each joint
    - 1 loop at the pivot point (where bone rotates)
    - 1 loop on each side for falloff
    - For 180-degree bends, add 2 more loops (5 total)
    
    ```
    BAD (2 loops):        GOOD (3 loops):       BEST (5 loops for full bend):
    ═══════════════       ═══════════════       ═══════════════════════════
        │     │               │  │  │                 │ │ │ │ │
        │     │               │  │  │                 │ │ │ │ │
    ═══════════════       ═══════════════       ═══════════════════════════
    (pinches badly)       (clean bend)          (180° bend without artifacts)
    ```
    
    ### Face Topology
    - Eye loops: Concentric circles around the eye socket (minimum 2)
    - Mouth loops: Horizontal loops following the lips (minimum 3)
    - Nasolabial fold: Edge flow from nose to mouth corner
    - Never let edge loops terminate at the face - always flow to ears/neck
    
    ### Muscle Direction
    ```
    Bicep:    Loops perpendicular to arm length (allow bulge)
    Forearm:  Loops follow twist rotation axis
    Chest:    Loops follow pectoral muscle shape
    Back:     Loops follow latissimus dorsi fan shape
    ```
    
    ### Pole Placement
    - 5-poles (5 edges meeting) create tension - place in low-deformation areas
    - 3-poles (3 edges meeting) are rare - usually indicate problems
    - Ideal locations: center of cheek, back of head, back of hand
    - NEVER place poles: at joints, on lips, around eyes
    
    ### Blender Tools for Edge Flow
    ```
    Loop Cut and Slide:     Ctrl+R
    Edge Slide:             G G
    Select Edge Loop:       Alt+Click
    Select Edge Ring:       Ctrl+Alt+Click
    Dissolve Edge Loop:     Ctrl+X (Dissolve Edges keeps the surface)
    Grid Fill:              Face > Grid Fill (clean quad caps)
    Edge Flow add-on:       Set Flow to relax loops along curvature
    ```
    
  #### **Examples**
    
---
      ###### **Situation**
Character elbow setup
      ###### **Solution**
        ```
        # Elbow loop structure (cross-section view)
        
        Upper arm:
        ════════════════════╗
                            ║ ← Loop 1 (holding loop)
        ────────────────────╢
                            ║ ← Loop 2 (pivot - at joint)
        ────────────────────╢
                            ║ ← Loop 3 (holding loop)
        ════════════════════╝
        Forearm continues...
        
        # The pivot loop should be EXACTLY where the bone joint is
        # In Blender: Select loop, Shift+S > Cursor to Selected, then position bone there
        ```
        

---
  #### **Id**
modular-asset-workflow
  #### **Name**
Modular Asset Workflow
  #### **Description**
    Build assets from reusable, tileable components that snap together without
    visible seams. Essential for environment art and level design.
    
  #### **When To Use**
Environment props, architectural elements, game levels
  #### **Implementation**
    ## Grid-Based Modeling in Blender
    
    ### Establish Grid Units
    ```
    Scene Properties > Units:
    - Unit System:   Metric
    - Unit Scale:    1.0  (1 Blender unit = 1 meter)
    - Length:        Meters (or Centimeters for display only)
    
    Snapping (Shift+Tab to toggle):
    - Snap To:       Increment (enable "Absolute Grid Snap")
    - Grid subdivisions: 1, 0.5, 0.25, 0.125
    
    Set units from the START - never rescale a finished modular kit
    ```
    
    ### Modular Piece Types
    ```
    Wall pieces:      4m x 3m (width x height)
    Floor tiles:      4m x 4m
    Corner pieces:    Match wall dimensions
    Trim pieces:      4m length, variable height
    Props:            Fit within grid or explicit measurements
    ```
    
    ### Origin (Pivot) Standards
    ```
    Walls:            Bottom-center of the piece
    Floors:           Center of the piece (for rotation)
    Corners:          At the corner vertex
    Props:            Bottom-center or contact point with ground
    Doors/Windows:    Center of the opening
    
    Setting origin in Blender:
    1. Edit Mode: select the target vertex/edge/face
    2. Shift+S > Cursor to Selected
    3. Object Mode: Object > Set Origin > Origin to 3D Cursor
    ```
    
    ### Seamless Tiling Rules
    1. Edge vertices MUST align to grid
    2. Matching edges need IDENTICAL vertex count
    3. UV seams should be at connection points
    4. Normal direction must be consistent across all pieces
    
    ### Previewing Tiling
    ```
    - Use Array modifiers (Relative Offset 1.0) to preview repeats
    - Use Collection Instances (Shift+A > Collection Instance) to assemble
      test layouts without duplicating mesh data
    ```
    
    ### Vertex Welding at Connections
    ```python
    # Blender Python example - weld modular pieces
    import bpy
    
    def weld_modular_pieces(objects, threshold=0.001):
        """Weld vertices at modular connection points"""
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = objects[0]
        bpy.ops.object.join()
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=threshold)
        bpy.ops.object.mode_set(mode='OBJECT')
    ```
    

---
  #### **Id**
lod-creation-strategy
  #### **Name**
LOD Creation Strategy
  #### **Description**
    Create efficient Level of Detail meshes in Blender that maintain silhouette
    and reduce triangle counts without visual popping.
    
  #### **When To Use**
Any game asset, especially those instanced multiple times
  #### **Implementation**
    ## LOD Reduction Targets
    
    ### Standard LOD Chain
    ```
    LOD0: 100% (base mesh)
    LOD1: 50%  (first reduction - maintain silhouette)
    LOD2: 25%  (medium distance - simplify internal detail)
    LOD3: 12%  (far distance - basic shape only)
    LOD4: 5%   (impostor distance - optional billboard)
    ```
    
    ### What to Remove at Each LOD
    
    **LOD1 (50%)**
    - Internal edge loops that don't affect silhouette
    - Bevels on edges not visible at distance
    - Small extrusions < 5% of object size
    - Subdivisions in flat areas
    
    **LOD2 (25%)**
    - Most bevels except major edges
    - Secondary shapes
    - Internal geometry completely
    - Reduce circular segments (32 → 16 → 8)
    
    **LOD3 (12%)**
    - All bevels
    - Tertiary shapes
    - Circular segments to minimum (8 → 6 → 4)
    - Merge separate meshes into single shapes
    
    ### Preservation Priority
    ```
    1. Silhouette edges (NEVER remove)
    2. Contact points with other objects
    3. Major surface breaks
    4. Character-recognizable features (eyes, hands)
    5. Everything else
    ```
    
    ### Decimate Modifier Modes
    ```
    Collapse:      Ratio-based reduction (general purpose)
                   - Enable Symmetry for mirrored meshes
                   - Enable Triangulate for predictable results
                   - Use a Vertex Group to protect silhouette areas
    Un-Subdivide:  Reverses grid-like subdivision (good for subdivided quads)
    Planar:        Dissolves coplanar faces by angle (great for hard surface)
    ```
    
    ### Manual vs Automatic LOD
    ```
    USE DECIMATE MODIFIER:
    - Props with no deformation
    - Environment meshes
    - Static decorations
    
    USE MANUAL (dissolve loops, lower modifier segment counts):
    - Characters (preserve edge loops)
    - Weapons (maintain profile)
    - Vehicles (preserve functional silhouette)
    - Hero props (anything in close-up cutscenes)
    
    TIP: If the asset is built with Bevel/Subdivision/Array modifiers,
    lower their segment/level counts per LOD instead of decimating.
    ```
    
    ### Generating a LOD Chain (bpy)
    ```python
    import bpy
    
    def make_lods(obj, ratios=(0.5, 0.25, 0.12)):
        """Duplicate obj into _LOD1.._LODn copies with a Decimate modifier"""
        base = obj.name
        obj.name = f"{base}_LOD0"
        collection = obj.users_collection[0]
        for i, ratio in enumerate(ratios, start=1):
            lod = obj.copy()
            lod.data = obj.data.copy()
            lod.name = f"{base}_LOD{i}"
            collection.objects.link(lod)
            mod = lod.modifiers.new(name="Decimate", type='DECIMATE')
            mod.decimate_type = 'COLLAPSE'
            mod.ratio = ratio
            mod.use_collapse_triangulate = True
    ```
    

---
  #### **Id**
hard-surface-workflow
  #### **Name**
Hard Surface Modeling Workflow
  #### **Description**
    Non-destructive hard surface modeling using booleans, bevels, and modifiers
    that maintain editability throughout production.
    
  #### **When To Use**
Mechanical objects, weapons, vehicles, architecture, props
  #### **Implementation**
    ## Non-Destructive Modifier Stack
    
    ### Modifier Order (CRITICAL)
    ```
    1. Mirror (if symmetrical)
    2. Array (if repeating)
    3. Boolean (cutters live in separate collection)
    4. Bevel (weight-based, not angle-based)
    5. Weighted Normal (for shading)
    6. Triangulate (export only - keep disabled)
    7. Subdivision (optional, for curved surfaces)
    ```
    
    ### Boolean Best Practices
    ```
    CUTTER SETUP:
    - Keep cutters in hidden collection named "Cutters" or "Bool_Cuts"
    - Name cutters: ObjectName_Cut_Description (e.g., Gun_Cut_MagWell)
    - Set cutter Viewport Display to Wire or Bounds
    - Cutters should be slightly larger than the cut
    - Use Exact solver, not Fast (Fast creates artifacts)
    
    AVOIDING BOOLEAN ARTIFACTS:
    - Ensure cutters have clean topology (no n-gons)
    - Cutter edges should not align with base mesh edges
    - Cutter should fully penetrate (no partial intersections)
    - After boolean, check for non-manifold geometry
      (Select > Select All by Trait > Non Manifold)
    ```
    
    ### Bevel Weight Workflow
    ```python
    # Instead of auto-smooth angle, use bevel weights
    # Edit Mode: Ctrl+E > Edge Bevel Weight, Shift+E for Crease
    # (Blender 4.0+ stores these as the "bevel_weight_edge" / "crease_edge" attributes)
    
    Edge Types:
    - Sharp edges:     Bevel Weight = 1.0, Crease = 1.0
    - Medium edges:    Bevel Weight = 0.5, Crease = 0.5
    - Soft edges:      Bevel Weight = 0.0, Crease = 0.0
    
    # Bevel modifier settings:
    Width:          0.02 (adjust to scale)
    Segments:       3 (for subdiv) or 2 (for game)
    Limit Method:   Weight
    Miter Outer:    Arc
    Harden Normals: ON
    ```
    
    ### Shading (Blender 4.1+)
    ```
    - Auto Smooth was removed in 4.1
    - Use Object > Shade Auto Smooth (adds a "Smooth by Angle" modifier)
      or Shade Smooth + Mark Sharp edges
    - Keep "Smooth by Angle" / Weighted Normal at the END of the stack
    ```
    
    ### Floating Geometry Technique
    ```
    For panel lines and surface details:
    1. Model detail as separate mesh
    2. Position slightly above surface (0.001 units)
    3. Shrinkwrap modifier to conform to surface
    4. Bake to normal map for game use
    
    Benefits:
    - Easy to edit/reposition
    - Clean normal map bakes
    - Works with curved surfaces
    ```
    

---
  #### **Id**
organic-sculpting-workflow
  #### **Name**
Organic Sculpting Workflow
  #### **Description**
    Efficient Sculpt Mode pipeline from blockout to final detail, with proper
    resolution management and retopology planning.
    
  #### **When To Use**
Characters, creatures, organic props, anything with complex forms
  #### **Implementation**
    ## Sculpting Phase Pipeline
    
    ### Phase 0: Blockout (Voxel Remesh / Dyntopo)
    ```
    Focus: Free-form shape exploration without topology constraints
    Tools: Voxel Remesh (Ctrl+R, set size with R), Dyntopo (Ctrl+D)
    
    - Voxel Remesh to merge separate blockout pieces into one mesh
    - Dyntopo for adding local detail/volume without stretching
    - Once forms are settled: retopologize or Voxel Remesh to an even
      base, then add a Multiresolution modifier
    ```
    
    ### Phase 1: Primary Forms (Multires Level 1-2)
    ```
    Focus: Overall silhouette and proportions
    Brushes: Grab, Snake Hook, Clay Strips, Elastic Deform
    Time:  30% of sculpting time
    
    Checkpoints:
    - [ ] Silhouette reads clearly from all angles
    - [ ] Major masses are established
    - [ ] Proportions match reference
    - [ ] No anatomy errors at this stage
    ```
    
    ### Phase 2: Secondary Forms (Multires Level 3-4)
    ```
    Focus: Muscle groups, major wrinkles, feature shapes
    Brushes: Clay Strips, Crease, Inflate, Draw Sharp
    Time:  40% of sculpting time
    
    Checkpoints:
    - [ ] Muscle anatomy is defined
    - [ ] Major skin folds established
    - [ ] Features (eyes, nose, mouth) shaped
    - [ ] Hands/feet blocked in
    ```
    
    ### Phase 3: Tertiary Detail (Multires Level 5-7)
    ```
    Focus: Skin pores, fine wrinkles, micro-detail
    Brushes: Draw, Layer, textured brushes (Texture panel), Pinch
    Time:  30% of sculpting time
    
    Checkpoints:
    - [ ] Pore detail consistent across surface
    - [ ] Fine wrinkles follow tension lines
    - [ ] No stretching or compression artifacts
    - [ ] Detail density matches final resolution
    ```
    
    ### Multiresolution Management
    ```
    - Add Multiresolution modifier; use Subdivide (Catmull-Clark) for organic,
      Simple for hard surface
    - Work at the lowest Sculpt level possible
    - Keep Viewport level lower than Sculpt level if performance suffers
    - Use "Apply Base" to push large changes down into the base mesh
    - Store alternate forms as Shape Keys on the base mesh before major changes
    - Use Mask (M brush / Alt+M to clear) and Hide (H / Alt+H) to isolate areas
    ```
    
    ### Face Set Strategy
    ```
    Group by: material zones, symmetry halves, detail areas
    Use for: masking, hiding, isolation, UV planning
    
    Shortcuts:
    - Ctrl+W:          Face Sets menu (e.g., from Edit Mode selection)
    - Alt+W:           Face Set Edit (grow/shrink)
    - H over a set:    Isolate that Face Set
    ```
    
    ### Retopology Planning During Sculpt
    ```
    While sculpting, note:
    - Where edge loops should go for animation
    - UV seam locations (hide in creases)
    - Material boundaries
    - Areas needing extra resolution
    
    Mark these using Face Sets or Color Attributes (Vertex/Color painting)
    ```
    

---
  #### **Id**
uv-unwrapping-strategy
  #### **Name**
UV Unwrapping Strategy
  #### **Description**
    Efficient UV layouts that maximize texture resolution while hiding seams
    and maintaining consistent texel density.
    
  #### **When To Use**
Any textured 3D model
  #### **Implementation**
    ## Texel Density Standards
    
    ### Calculate Target Texel Density
    ```
    Formula: Texel Density = Texture Resolution / World Size
    
    AAA Game Standards:
    - Hero characters:    10.24 px/cm (1024px per meter)
    - NPCs:               5.12 px/cm  (512px per meter)
    - Large props:        5.12 px/cm
    - Environment:        2.56 px/cm
    - Distant background: 1.28 px/cm
    
    Mobile Standards:
    - All assets:         2.56-5.12 px/cm
    ```
    
    ### Texel Density Checker
    ```python
    # Add-on: "Texel Density Checker" by mrven
    # Or calculate manually:
    
    def check_texel_density(obj, texture_size):
        """Check if UV density is consistent"""
        mesh = obj.data
        uv_layer = mesh.uv_layers.active.data
    
        densities = []
        for poly in mesh.polygons:
            # Calculate 3D area
            world_area = poly.area
    
            # Calculate UV area
            uv_verts = [uv_layer[loop_idx].uv for loop_idx in poly.loop_indices]
            uv_area = calculate_polygon_area(uv_verts)
    
            # Texel density
            density = (texture_size * math.sqrt(uv_area)) / math.sqrt(world_area)
            densities.append(density)
    
        return min(densities), max(densities), sum(densities)/len(densities)
    ```
    
    ### Blender UV Toolkit
    ```
    Mark Seam:              Edge Mode > Ctrl+E > Mark Seam (or UV > Mark Seam)
    Unwrap:                 U > Unwrap (Angle Based for organic, Conformal for hard surface)
    Live Unwrap:            UV Editor > UV > Live Unwrap (re-unwraps as you edit seams)
    Smart UV Project:       Prototyping / blockout ONLY
    Average Islands Scale:  UV Editor > Ctrl+A (equalizes texel density)
    Pack Islands:           UV Editor > Ctrl+P (set Margin to match padding below)
    Straighten islands:     UV Squares add-on or Follow Active Quads
    Stretch display:        UV Editor Overlays > Display Stretch
    ```
    
    ### Seam Placement Rules
    ```
    HIDE SEAMS IN:
    - Natural creases (armpit, groin, behind ears)
    - Material boundaries (skin to cloth)
    - Back of objects (where camera rarely sees)
    - Underside of props
    - Inside of mouths/eyelids
    
    AVOID SEAMS ON:
    - Face front (especially across nose/lips)
    - Visible flat surfaces
    - Areas with stretching patterns
    - Across areas with continuous detail
    ```
    
    ### UV Island Organization
    ```
    Layout Strategy:
    1. Group related islands together (all face islands, all body islands)
    2. Orient islands consistently (same "up" direction)
    3. Straight edges should be axis-aligned
    4. Mirror matching islands when possible
    5. Leave 2-4 pixel padding between islands
    
    Padding Formula:
    - 256px texture:  2px padding minimum
    - 512px texture:  4px padding minimum
    - 1024px texture: 8px padding minimum
    - 2048px texture: 16px padding minimum
    - 4096px texture: 32px padding minimum
    ```
    
    ### UDIM Workflow (Film/High-End)
    ```
    When to use UDIMs:
    - Texture resolution > 8K needed
    - Multiple texture sets on one mesh
    - Film/VFX production
    
    In Blender: create a Tiled image in the Image Editor (New Image > Tiled),
    add tiles, then move islands into tile spaces in the UV Editor.
    
    UDIM Layout:
    1001: Face
    1002: Head back/neck
    1003: Torso front
    1004: Torso back
    1005-1006: Arms
    1007-1008: Legs
    1009-1010: Hands (one per hand)
    ```
    

---
  #### **Id**
high-to-low-baking
  #### **Name**
High to Low Poly Baking
  #### **Description**
    Transfer detail from sculpts to game-ready meshes through normal, AO, and
    curvature map baking in Cycles with proper cage setup.
    
  #### **When To Use**
Any game asset derived from high-poly source
  #### **Implementation**
    ## Baking Setup Checklist
    
    ### Pre-Bake Requirements
    ```
    HIGH POLY:
    - [ ] All transforms applied (Ctrl+A)
    - [ ] Normals facing outward (Shift+N recalculate)
    - [ ] No holes or open edges
    - [ ] Shading set correctly (Shade Smooth / Mark Sharp)
    - [ ] Named with _high suffix
    
    LOW POLY:
    - [ ] All transforms applied
    - [ ] UVs unwrapped with proper padding
    - [ ] No overlapping UVs (for unique maps)
    - [ ] Named with _low suffix
    - [ ] Matches high poly in world position
    - [ ] Material has an Image Texture node with the target image, selected (active)
    - [ ] Normal map image set to Non-Color
    
    CAGE (optional but recommended):
    - [ ] Duplicate of low poly, slightly inflated
    - [ ] Named with _cage suffix
    - [ ] No intersections with high poly
    ```
    
    ### Cage Creation
    ```
    Method 1: Cage Object (Most Control)
    1. Duplicate low poly (Shift+D), keep identical topology
    2. Apply Displace modifier with constant offset (or Alt+S Shrink/Fatten)
    3. Manually adjust problem areas
    4. Bake panel: enable Cage, pick it as Cage Object
    
    Method 2: Extrusion (Faster)
    1. Bake panel: leave Cage off, set Extrusion
    2. Start small (e.g., 0.01-0.05 m), adjust per-mesh
    
    Cage Rules:
    - Must fully encompass high poly
    - Should not intersect high poly
    - Larger cage = more bake margin for error
    - Too large = ray misses, artifacts
    ```
    
    ### Baking Settings (Cycles)
    ```
    Render Engine:    Cycles (GPU if available)
    Samples:          64 (production) / 16 (preview) - matters for AO, not Normal
    
    Bake Panel (Render Properties > Bake):
    - Selected to Active: ON (select high, then Shift-select low as active)
    - Extrusion / Cage:   see Cage Creation
    - Max Ray Distance:   0 (auto) or slightly larger than extrusion
    - Margin:             Match UV padding in pixels, Type: Adjacent Faces
    - Output Size:        Set by the target image (2K, 4K)
    
    Normal Map:
    - Space: Tangent
    - Swizzle: +X +Y +Z (OpenGL, Blender default - used by Unity, Godot)
    - Swizzle: +X -Y +Z (DirectX - flip green for Unreal)
    
    AO Map:
    - Bake Type: Ambient Occlusion
    - Increase samples (128+) for clean results
    
    REMEMBER: Baked images live only in memory - Image > Save As after baking!
    ```
    
    ### Common Baking Artifacts and Fixes
    ```
    PROBLEM: Wavy/wobbly normals
    CAUSE: Low poly normals not matching high poly
    FIX: Set low poly to smooth shading, Mark Sharp at UV seams
    
    PROBLEM: Black areas in bake
    CAUSE: Cage too tight, rays missing high poly
    FIX: Inflate cage, increase Extrusion / Max Ray Distance
    
    PROBLEM: "Skirt" artifacts at edges
    CAUSE: Rays hitting wrong surface
    FIX: Add geometry to low poly to separate surfaces
    
    PROBLEM: Seams visible on normal map
    CAUSE: UV seam on curved surface
    FIX: Move seam to sharp edge, or split mesh at seam
    
    PROBLEM: Gradient across flat surface
    CAUSE: Averaged normals on low poly
    FIX: Mark Sharp on 90-degree corners (and seam them)
    
    PROBLEM: Bake writes to the wrong image / "No active image found"
    CAUSE: Image Texture node not active in the low poly's material
    FIX: Click the target Image Texture node so it's highlighted, then bake
    ```
    

---
  #### **Id**
retopology-workflow
  #### **Name**
Retopology Best Practices
  #### **Description**
    Create optimized, animation-ready topology from sculpts using Blender's
    manual and semi-automatic retopology tools.
    
  #### **When To Use**
After sculpting, for game/animation-ready mesh creation
  #### **Implementation**
    ## Retopology Target Budgets
    
    ### Character Poly Budgets (Triangles)
    ```
    AAA Current-Gen (2024):
    - Hero character:     80,000 - 150,000
    - Main NPCs:          30,000 - 60,000
    - Background NPCs:    10,000 - 20,000
    - Creatures (large):  50,000 - 100,000
    
    Mobile/VR:
    - Main character:     5,000 - 15,000
    - NPCs:               2,000 - 5,000
    
    Film/Cinematic:
    - No real limit, but animation-friendly topology
    ```
    
    ### Body Part Distribution (Hero Character)
    ```
    Head/Face:    25-30%  (most expression detail)
    Torso:        20-25%  (deformation areas)
    Arms:         15-20%  (elbow/wrist detail)
    Hands:        15-20%  (finger articulation)
    Legs:         15-20%  (knee/ankle detail)
    ```
    
    ### Manual Retopo Workflow
    ```
    Setup:
    1. Add a new mesh over the sculpt, apply a Shrinkwrap modifier targeting the sculpt
    2. Snapping: Snap To "Face Project", enable "Project Individual Elements"
    3. Overlays (Edit Mode): enable "Retopology" so the new mesh draws on top
    4. Enable X-mirror (Mesh Symmetry) or a Mirror modifier with Clipping
    5. Use the Poly Build tool or the RetopoFlow add-on
    
    Process:
    1. Start with main edge loops (eye, mouth, joints)
    2. Connect loops with quad fills (Grid Fill, Bridge Edge Loops)
    3. Work from high-detail areas outward
    4. Check topology against animation requirements
    5. Final pass: optimize unnecessary geometry
    
    Shrinkwrap Settings:
    - Wrap Method: Nearest Surface Point
    - Snap Mode: Above Surface
    - Offset: 0.001 (small gap prevents z-fighting)
    ```
    
    ### Semi-Automatic Tools
    ```
    Remesh (built-in, Object Data > Remesh):
    - Voxel: even triangulated-quad density, good sculpt base - NOT final topology
    - QuadriFlow: all-quad result, decent for props and quick previews
    
    Quad Remesher (paid Blender add-on):
    - Best automatic edge flow available in Blender
    - Can guide with marked edges, Face Sets, and density vertex painting
    - Still needs manual work at joints
    
    When to Use Automatic:
    - Props and hard surface (no deformation)
    - Quick previews
    - Background assets
    
    When to Use Manual:
    - Face topology (always)
    - Joint areas (elbows, knees, fingers)
    - Anything with shape keys
    ```
    

---
  #### **Id**
export-pipeline
  #### **Name**
Export Pipeline Standards
  #### **Description**
    Standardized Blender export workflow for common targets and formats,
    avoiding the most common export issues.
    
  #### **When To Use**
When exporting assets out of Blender
  #### **Implementation**
    ## Pre-Export Checklist
    
    ### Universal Requirements
    ```
    - [ ] All transforms applied (Ctrl+A > All Transforms)
    - [ ] Scale is 1.0, 1.0, 1.0
    - [ ] Origin point is correct (usually bottom-center)
    - [ ] Normals are facing outward (Overlays > Face Orientation: all blue)
    - [ ] No n-gons (Select > Select All by Trait > Faces by Sides > 4, Greater Than)
    - [ ] No non-manifold geometry (Select > Select All by Trait > Non Manifold)
    - [ ] No floating vertices (Mesh > Clean Up > Delete Loose)
    - [ ] Named correctly (no spaces, no special characters)
    ```
    
    ### Format Selection
    ```
    FBX:
    - Best for: Unreal Engine, Unity (with animation)
    - Pros: Industry standard, widely supported
    - Cons: Proprietary format, axis/scale quirks
    
    glTF/GLB:
    - Best for: Web, Godot, cross-platform
    - Pros: Open standard, PBR material support (Principled BSDF maps cleanly)
    - Cons: Less animation support than FBX
    
    OBJ:
    - Best for: Static meshes, quick transfer
    - Pros: Universal support, simple format
    - Cons: No animation, no hierarchy
    
    USD:
    - Best for: Film/VFX, complex scenes
    - Pros: Industry standard for film, non-destructive
    - Cons: Complex, not all game engines support
    ```
    
    ### FBX Export Settings
    ```
    Include:
    - Limit to:         Selected Objects (avoid exporting cutters, lights, cameras)
    - Object Types:     Mesh (+ Armature if rigged)
    
    Transform:
    - Scale:            1.0
    - Apply Scalings:   FBX All
    - Forward / Up:     See target presets below
    
    Geometry:
    - Smoothing:        Face (exports sharp edges as smoothing)
    - Apply Modifiers:  ON
    - Triangulate:      ON (for game engines)
    - Tangent Space:    ON
    
    Armature:
    - Add Leaf Bones:   OFF (usually)
    - Primary Bone Axis: Y
    - Secondary Bone Axis: X
    
    Animation:
    - Bake Animation:   ON
    - NLA Strips:       OFF (export each action separately)
    ```
    
    ### Target Presets (Blender-side settings)
    
    #### Unreal Engine (FBX)
    ```
    - Scale: 1.0 (Unit Scale 1.0, Apply Scalings: FBX All)
    - Forward: -Y Forward
    - Up: Z Up
    - Collision meshes: name UCX_<MeshName>_## in the same export
    ```
    
    #### Unity (FBX)
    ```
    - Scale: 1.0 (Apply Scalings: FBX All)
    - Forward: -Z Forward
    - Up: Y Up
    - Enable "Apply Transform" (experimental) to avoid -90° X rotation
    ```
    
    #### Godot / Web (glTF)
    ```
    Preferred: glTF 2.0 (.glb)
    
    glTF Settings:
    - Format: glTF Binary (.glb)
    - Include: Selected Objects only
    - Transform: +Y Up
    - Geometry: Apply Modifiers, UVs, Normals
    - Compression: Draco (for web)
    ```
    
    ### Scripted Export (bpy)
    ```python
    import bpy
    
    def export_fbx(filepath):
        bpy.ops.export_scene.fbx(
            filepath=filepath,
            use_selection=True,
            apply_scale_options='FBX_SCALE_ALL',
            use_mesh_modifiers=True,
            mesh_smooth_type='FACE',
            use_tspace=True,
            add_leaf_bones=False,
        )
    
    def export_glb(filepath):
        bpy.ops.export_scene.gltf(
            filepath=filepath,
            export_format='GLB',
            use_selection=True,
            export_apply=True,
            export_yup=True,
        )
    ```
    

---
  #### **Id**
naming-conventions
  #### **Name**
Asset Naming Conventions
  #### **Description**
    Industry-standard naming for Blender objects, collections, and exported
    files, ensuring clarity in large productions and compatibility with version control.
    
  #### **When To Use**
Always - from project start
  #### **Implementation**
    ## Naming Structure
    
    ### General Format
    ```
    [Prefix]_[AssetName]_[Variant]_[LOD/Type]
    
    Examples:
    SM_Chair_Wood_LOD0          (Static Mesh)
    SK_Character_Hero_LOD1      (Skeletal / rigged Mesh)
    T_Chair_Wood_D              (Texture - Diffuse)
    M_Chair_Wood                (Material)
    ```
    
    ### Prefixes by Type
    ```
    SM_     Static Mesh
    SK_     Skeletal Mesh (mesh parented to an Armature)
    UCX_    Convex collision mesh (exported alongside SM_)
    T_      Texture
    M_      Material
    A_      Action (animation)
    ```
    
    ### Blender-Specific Suffixes
    ```
    _high   High poly bake source
    _low    Low poly bake target
    _cage   Bake cage
    _Cut_   Boolean cutter (e.g., Gun_Cut_MagWell)
    ```
    
    ### Texture Suffixes
    ```
    _D      Diffuse / Albedo / Base Color
    _N      Normal Map
    _R      Roughness
    _M      Metallic
    _AO     Ambient Occlusion
    _H      Height / Displacement
    _E      Emissive
    _O      Opacity / Alpha
    _ARM    Packed: AO, Roughness, Metallic (RGB)
    _ORM    Packed: Occlusion, Roughness, Metallic (RGB)
    ```
    
    ### LOD Naming
    ```
    _LOD0   Base mesh (highest quality)
    _LOD1   First reduction
    _LOD2   Second reduction
    _LOD3   Third reduction
    _LOD4   Lowest quality / impostor
    ```
    
    ### Version Control Friendly Names
    ```
    DO:
    - Use underscores, not spaces
    - Use PascalCase or camelCase
    - Keep names under 63 characters (Blender's datablock name limit)
    - Use numbers for variants (Chair_01, Chair_02)
    - Rename mesh data to match its object (avoid "Cube.001" data blocks)
    
    DON'T:
    - Spaces in names (Chair Wood ❌)
    - Special characters (&, %, #, etc.)
    - Very long names
    - Ambiguous names (Final, Final2, FinalFinal)
    - Leave Blender's auto ".001" suffixes on exported objects
    ```
    
    ### Collection Structure (inside the .blend)
    ```
    Scene Collection
    ├── SM_Chair          (export collection - only final meshes)
    ├── Bake
    │   ├── Chair_high
    │   ├── Chair_low
    │   └── Chair_cage
    ├── Cutters           (hidden, excluded from render/export)
    └── Reference         (images, scale references)
    ```
    
    ### Folder Structure
    ```
    Project/
    ├── Characters/
    │   ├── Hero/
    │   │   ├── Hero.blend
    │   │   ├── Textures/
    │   │   └── Export/
    │   └── NPCs/
    ├── Props/
    │   ├── Furniture/
    │   └── Weapons/
    ├── Environment/
    │   ├── Modular/
    │   └── Unique/
    └── Library/          (shared materials/node groups via Asset Browser)
    ```
    

---
  #### **Id**
high-performance-bpy-scripting
  #### **Name**
High-Performance bpy Scripting & Scene Instancing
  #### **Description**
    Build and mutate meshes, instances, and materials using Blender's low-level
    RNA Data API (`bpy.data`, `bmesh`, `foreach_set`) instead of `bpy.ops` loops,
    avoiding $O(N^2)$ dependency-graph stalls and memory bloat.
    
  #### **When To Use**
Whenever generating or modifying scenes via Python (`bpy`) or Blender MCP
  #### **Implementation**
    ## Data API First (Never Loop `bpy.ops`)
    
    ### Fast Mesh Creation with `from_pydata` & `foreach_set`
    ```python
    import bpy
    import numpy as np
    
    def create_mesh_object(name, verts, faces, collection=None):
        """Create a mesh object via Data API without triggering UI operators"""
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, [], faces)
        mesh.validate(verbose=False)
        mesh.update()
        
        obj = bpy.data.objects.new(name, mesh)
        col = collection or bpy.context.collection
        col.objects.link(obj)
        return obj
    
    def set_vertices_fast(mesh, coords_np):
        """Bulk-copy (N, 3) float32 NumPy coordinates into a mesh in C"""
        flat = np.asarray(coords_np, dtype=np.float32).ravel()
        mesh.vertices.foreach_set("co", flat)
        mesh.update()
    ```
    
    ### Shared-Mesh Instancing vs. Collection Instances
    ```python
    def spawn_linked_instances(base_mesh, transforms, base_name="Prop", collection=None):
        """
        Spawn N objects sharing ONE Mesh datablock (Linked Duplicates).
        Zero geometry duplication in RAM/VRAM; updates view_layer only once.
        """
        col = collection or bpy.context.collection
        created = []
        for i, (loc, rot_euler, scale) in enumerate(transforms):
            obj = bpy.data.objects.new(f"{base_name}_{i:04d}", base_mesh)
            obj.location = loc
            obj.rotation_euler = rot_euler
            obj.scale = scale
            col.objects.link(obj)
            created.append(obj)
        bpy.context.view_layer.update()
        return created
    
    def spawn_collection_instance(source_collection, name, location=(0, 0, 0), parent_col=None):
        """Instantiate an entire multi-object assembly as a lightweight Empty instance"""
        inst = bpy.data.objects.new(name, None)
        inst.instance_type = 'COLLECTION'
        inst.instance_collection = source_collection
        inst.location = location
        (parent_col or bpy.context.collection).objects.link(inst)
        return inst
    ```
    
    ### Idempotent Material & Image Caching (No `.001` Bloat)
    ```python
    def get_or_create_material(name, builder_fn=None):
        """Reuse existing material by name instead of spawning Material.001..999"""
        mat = bpy.data.materials.get(name)
        if mat is None:
            mat = bpy.data.materials.new(name=name)
            mat.use_nodes = True
            if builder_fn is not None:
                builder_fn(mat)
        return mat
    
    def load_image_cached(filepath, non_color=False):
        """Load image once and enforce Non-Color for data maps"""
        img = bpy.data.images.load(filepath, check_existing=True)
        img.colorspace_settings.name = 'Non-Color' if non_color else 'sRGB'
        return img
    ```
    
    ### Recursive Orphan Cleanup
    ```python
    def purge_orphans():
        """Free all unused Meshes, Materials, Images, and NodeGroups from RAM"""
        for datablock_collection in (
            bpy.data.meshes,
            bpy.data.materials,
            bpy.data.images,
            bpy.data.node_groups,
            bpy.data.curves,
        ):
            orphans = [db for db in datablock_collection if db.users == 0]
            if orphans:
                bpy.data.batch_remove(orphans)
    ```
    

---
  #### **Id**
physically-plausible-materials-and-lighting
  #### **Name**
Physically Plausible PBR Materials, Micro-Bevels & Render Setup (Blender 4.x–5.x)
  #### **Description**
    Eliminate the "synthetic CG look" and Cycles/EEVEE rendering anomalies by
    enforcing PBR albedo/roughness bounds, Blender 4.0–5.x Principled BSDF v2
    sockets, Non-Color data maps, micro-beveled edges, AgX tone mapping, and
    optimized GPU render settings.
    
  #### **When To Use**
Every scene intended for viewport presentation, look-dev, or final rendering
  #### **Implementation**
    ## Physically Plausible Material & Scene Rules
    
    ### PBR Value Guardrails
    ```
    Base Color (Linear RGB):
    - NEVER use pure 0.0 or pure 1.0 (breaks energy conservation & bounce light)
    - Darkest real surfaces (charcoal, tire rubber, matte black): 0.03 - 0.05
    - Brightest real surfaces (fresh snow, titanium white paint): 0.80 - 0.85
    
    Roughness:
    - NEVER use 0.00 (even mirrors/glass have 0.02 - 0.05 micro-roughness)
    - Add subtle variation (Noise Texture -> ColorRamp -> +/- 0.05 roughness)
    
    Metallic:
    - Strictly binary: 0.0 (dielectric) or 1.0 (raw metal)
    
    Micro-Bevels:
    - Every visible hard-surface object MUST have a Bevel modifier
      (width 1mm-5mm, 2-3 segments, Harden Normals ON) or Shader Bevel node.
    ```
    
    ### Blender 4.0–5.x Principled BSDF v2 Builder
    ```python
    import bpy
    import math
    
    def create_pbr_material(
        name,
        base_color=(0.5, 0.5, 0.5, 1.0),
        metallic=0.0,
        roughness=0.4,
        ior=1.5,
        coat_weight=0.0,
        coat_roughness=0.05,
        transmission_weight=0.0,
        emission_color=(0.0, 0.0, 0.0, 1.0),
        emission_strength=0.0,
    ):
        """Create a Blender 4.0-5.x compliant Principled BSDF v2 material with clamped PBR bounds"""
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name=name)
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = nt.nodes.get("Principled BSDF") or nt.nodes.new("ShaderNodeBsdfPrincipled")
        
        # Clamp dielectric albedo to physically plausible [0.03, 0.85]
        r, g, b, a = base_color
        if metallic < 0.5:
            r = max(0.03, min(0.85, r))
            g = max(0.03, min(0.85, g))
            b = max(0.03, min(0.85, b))
        bsdf.inputs["Base Color"].default_value = (r, g, b, a)
        bsdf.inputs["Metallic"].default_value = 1.0 if metallic >= 0.5 else 0.0
        bsdf.inputs["Roughness"].default_value = max(0.02, min(0.98, roughness))
        bsdf.inputs["IOR"].default_value = ior
        bsdf.inputs["Coat Weight"].default_value = coat_weight
        bsdf.inputs["Coat Roughness"].default_value = coat_roughness
        bsdf.inputs["Transmission Weight"].default_value = transmission_weight
        bsdf.inputs["Emission Color"].default_value = emission_color
        bsdf.inputs["Emission Strength"].default_value = emission_strength
        
        if transmission_weight > 0.0 and hasattr(mat, "surface_render_method"):
            mat.surface_render_method = 'DITHERED'
            mat.use_raytrace_refraction = True
            
        return mat
    
    def add_micro_bevel_and_smooth(obj, width=0.003, segments=2, angle_deg=30.0):
        """Give hard-surface meshes realistic edge highlights and clean shading"""
        if obj.type != 'MESH':
            return
        bev = next((m for m in obj.modifiers if m.type == 'BEVEL'), None)
        if bev is None:
            bev = obj.modifiers.new(name="Bevel", type='BEVEL')
        bev.width = width
        bev.segments = segments
        bev.limit_method = 'ANGLE'
        bev.angle_limit = math.radians(angle_deg)
        bev.miter_outer = 'MITER_ARC'
        bev.harden_normals = True
        
        wn = next((m for m in obj.modifiers if m.type == 'WEIGHTED_NORMAL'), None)
        if wn is None:
            wn = obj.modifiers.new(name="WeightedNormal", type='WEIGHTED_NORMAL')
        wn.keep_sharp = True
        
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle_deg), keep_sharp_edges=True)
    ```
    
    ### Production Render & Color Management Configuration
    ```python
    def configure_production_render(scene=None, engine='CYCLES', quality='PRODUCTION'):
        """Configure AgX color management, Simplify guardrails, and Cycles/EEVEE Next"""
        scene = scene or bpy.context.scene
        
        # 1. Color Management: AgX prevents highlight clipping and hue skew
        scene.view_settings.view_transform = 'AgX'
        scene.view_settings.look = 'AgX - Medium High Contrast'
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
        
        # 2. Global Subdivision & Texture Guardrails
        scene.render.use_simplify = True
        scene.render.simplify_subdivision = 2
        scene.render.simplify_subdivision_render = 3
        
        if engine == 'CYCLES':
            scene.render.engine = 'CYCLES'
            c = scene.cycles
            c.device = 'GPU'
            c.use_adaptive_sampling = True
            c.adaptive_threshold = 0.01 if quality == 'PRODUCTION' else 0.05
            c.samples = 512 if quality == 'PRODUCTION' else 64
            c.adaptive_min_samples = 32 if quality == 'PRODUCTION' else 16
            c.use_denoising = True
            c.use_light_tree = True
            c.sample_clamp_indirect = 10.0
            c.caustics_reflective = False
            c.caustics_refractive = False
            c.max_bounces = 8
            c.diffuse_bounces = 3
            c.glossy_bounces = 4
            c.transmission_bounces = 8
            c.volume_bounces = 0
            scene.render.use_persistent_data = True
        else:
            scene.render.engine = 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'
            scene.eevee.use_raytracing = True
            scene.eevee.taa_render_samples = 64 if quality == 'PRODUCTION' else 16
    ```
    

---
  #### **Id**
agent-scene-audit-and-visual-verification
  #### **Name**
Programmatic Scene Audit & Multi-Angle Visual Verification
  #### **Description**
    Catch "silently successful" script bugs before finishing: floating or
    sinking objects, mesh interpenetration, unapplied non-uniform scale,
    extreme camera clipping, out-of-frame subjects, missing UVs, wrong
    texture colorspaces, and polygon budget blowouts.
    
  #### **When To Use**
Mandatory after creating or modifying any scene via Python or Blender MCP
  #### **Implementation**
    ## Automated Scene Audit Script (`audit_scene`)
    
    ```python
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from bpy_extras.object_utils import world_to_camera_view
    
    def get_world_bbox(obj, depsgraph):
        eval_obj = obj.evaluated_get(depsgraph)
        corners = [eval_obj.matrix_world @ Vector(c) for c in eval_obj.bound_box]
        xs = [p.x for p in corners]
        ys = [p.y for p in corners]
        zs = [p.z for p in corners]
        return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))
    
    def snap_object_to_ground(obj, ground_z=0.0):
        """Translate object vertically so its evaluated lowest point sits_on ground_z"""
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        bmin, _ = get_world_bbox(obj, depsgraph)
        obj.location.z += (ground_z - bmin.z)
        bpy.context.view_layer.update()
    
    def audit_scene(ground_z=0.0, check_intersections=True, tri_budget=2_000_000):
        """
        Run a comprehensive geometric, material, camera, and performance audit.
        Returns a dict of warnings/errors that the agent MUST fix before finishing.
        """
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        scene = bpy.context.scene
        issues = []
        
        mesh_objs = [
            o for o in scene.objects
            if o.type == 'MESH' and not o.hide_render and not o.hide_get()
        ]
        
        total_eval_tris = 0
        bboxes = {}
        bvhs = {}
        
        for obj in mesh_objs:
            # 1. Non-uniform or zero scale with active modifiers
            sx, sy, sz = obj.scale
            if any(abs(s) < 1e-4 for s in (sx, sy, sz)):
                issues.append(f"[CRITICAL] {obj.name}: near-zero scale {tuple(obj.scale)}")
            elif (abs(sx - sy) > 1e-3 or abs(sy - sz) > 1e-3) and len(obj.modifiers) > 0:
                issues.append(f"[HIGH] {obj.name}: non-uniform scale {tuple(round(s,3) for s in obj.scale)} with modifiers (distorts bevels/normals)")
            
            # 2. Evaluated triangle count & Subsurf check
            eval_obj = obj.evaluated_get(depsgraph)
            eval_mesh = eval_obj.to_mesh()
            eval_mesh.calc_loop_triangles()
            tris = len(eval_mesh.loop_triangles)
            total_eval_tris += tris
            eval_obj.to_mesh_clear()
            
            for mod in obj.modifiers:
                if mod.type == 'SUBSURF' and (mod.levels > 3 or mod.render_levels > 4):
                    issues.append(f"[HIGH] {obj.name}: excessive Subsurf levels ({mod.levels}/{mod.render_levels})")
            
            # 3. World bounding box & ground contact
            bmin, bmax = get_world_bbox(obj, depsgraph)
            bboxes[obj.name] = (bmin, bmax)
            if bmin.z < ground_z - 0.02:
                issues.append(f"[MEDIUM] {obj.name}: sinks below ground_z={ground_z} (min_z={bmin.z:.3f}m)")
            
            if check_intersections and 0 < tris < 100_000:
                bvhs[obj.name] = BVHTree.FromObject(eval_obj, depsgraph)
                
        if total_eval_tris > tri_budget:
            issues.append(f"[HIGH] Scene evaluated triangles ({total_eval_tris:,}) exceed budget ({tri_budget:,})")
            
        # 4. Pairwise AABB + BVH intersection check
        if check_intersections:
            names = list(bvhs.keys())
            for i in range(len(names)):
                for j in range(i + 1, len(names)):
                    na, nb = names[i], names[j]
                    min_a, max_a = bboxes[na]
                    min_b, max_b = bboxes[nb]
                    eps = 0.002
                    if (min_a.x + eps < max_b.x and max_a.x - eps > min_b.x and
                        min_a.y + eps < max_b.y and max_a.y - eps > min_b.y and
                        min_a.z + eps < max_b.z and max_a.z - eps > min_b.z):
                        overlaps = bvhs[na].overlap(bvhs[nb])
                        if len(overlaps) > 25:
                            issues.append(f"[MEDIUM] Mesh interpenetration between '{na}' and '{nb}' ({len(overlaps)} overlapping face pairs)")
                            
        # 5. Material & Colorspace audit
        data_map_keywords = ('normal', 'nrm', '_n.', 'rough', 'rgh', '_r.', 'metal', 'ao', 'disp', 'height', 'orm', 'arm')
        for mat in bpy.data.materials:
            if not mat.use_nodes or mat.users == 0:
                continue
            for node in mat.node_tree.nodes:
                if node.type == 'BSDF_PRINCIPLED':
                    bc = node.inputs["Base Color"].default_value
                    if not node.inputs["Base Color"].is_linked:
                        lum = max(bc[0], bc[1], bc[2])
                        if lum > 0.92 or lum < 0.015:
                            issues.append(f"[MEDIUM] Material '{mat.name}': implausible Base Color {tuple(round(c,3) for c in bc[:3])} (keep in 0.03..0.85)")
                elif node.type == 'TEX_IMAGE' and node.image:
                    img_name = (node.image.name + " " + node.image.filepath).lower()
                    if any(k in img_name for k in data_map_keywords):
                        if node.image.colorspace_settings.name == 'sRGB':
                            issues.append(f"[CRITICAL] Image '{node.image.name}' in '{mat.name}' is a data map but set to sRGB (must be 'Non-Color')")
                            
        # 6. Camera & Framing audit
        cam = scene.camera
        if cam is None:
            issues.append("[HIGH] Scene has no active camera (scene.camera is None)")
        else:
            ratio = cam.data.clip_end / max(cam.data.clip_start, 1e-9)
            if ratio > 100_000:
                issues.append(f"[HIGH] Camera '{cam.name}' clip_end/clip_start ratio is {ratio:,.0f} (>100k causes Z-fighting)")
            in_frame = 0
            for obj in mesh_objs:
                bmin, bmax = bboxes[obj.name]
                center = (bmin + bmax) * 0.5
                co2d = world_to_camera_view(scene, cam, center)
                if 0.0 <= co2d.x <= 1.0 and 0.0 <= co2d.y <= 1.0 and co2d.z > 0:
                    in_frame += 1
            if mesh_objs and in_frame == 0:
                issues.append("[CRITICAL] Zero mesh objects have their center inside the active camera frustum!")
                
        # 7. Lighting audit
        lights = [o for o in scene.objects if o.type == 'LIGHT' and not o.hide_render]
        world_has_light = bool(scene.world and scene.world.use_nodes)
        if not lights and not world_has_light:
            issues.append("[CRITICAL] Scene has no active lights and no World shader (render will be pitch black)")
            
        return {
            "mesh_object_count": len(mesh_objs),
            "evaluated_triangles": total_eval_tris,
            "issue_count": len(issues),
            "issues": issues,
        }
    ```
    

## Anti-Patterns


---
  #### **Id**
n-gon-modeling
  #### **Name**
Modeling with N-gons
  #### **Description**
    Leaving n-gons (polygons with more than 4 sides) in production geometry.
    N-gons cause unpredictable subdivision, shading artifacts, and export issues.
    
  #### **Why Bad**
    - Subdivision surfaces create artifacts at n-gon boundaries
    - Exporters and importers triangulate n-gons unpredictably
    - Causes shading discontinuities
    - Can break physics/collision generation
    - Animation deformation becomes unpredictable
    
  #### **What To Do Instead**
    Always model with quads. Use triangles only where necessary (poles,
    terminating edge loops). Convert n-gons to quads before any export.
    
    In Blender: Select All → Mesh → Clean Up → Split Non-Planar Faces,
    then Mesh → Face → Triangulate Faces → Poke Faces to create better topology.
    
---
  #### **Id**
unapplied-transforms
  #### **Name**
Exporting with Unapplied Transforms
  #### **Description**
    Exporting models without applying scale, rotation, and location transforms.
    This causes scaling and orientation issues after export.
    
  #### **Why Bad**
    - Object may appear at wrong scale after export
    - Rotation values affect animation and physics
    - Parent/child relationships break
    - Baking produces incorrect results
    - Modifiers (Bevel, Solidify, Array) behave differently on scaled objects
    
  #### **What To Do Instead**
    Before ANY export: Ctrl+A → All Transforms. Verify in the N-panel that
    scale is 1,1,1 and rotation is 0,0,0.
    
---
  #### **Id**
overlapping-uvs-baking
  #### **Name**
Overlapping UVs for Unique Bakes
  #### **Description**
    Using overlapping/mirrored UVs when baking unique maps (normal, AO, etc.).
    Overlapping UVs work for tiling textures but cause baking artifacts.
    
  #### **Why Bad**
    - Multiple surfaces bake to same UV space
    - Normal map shows averaged/corrupted data
    - AO shows incorrect shadowing
    - Impossible to paint unique details
    
  #### **What To Do Instead**
    For baking: use a non-overlapping UV Map (add a second UV Map in
    Object Data > UV Maps and make it active for the bake).
    For final texture: can use optimized UVs with mirroring.
    Both UV Maps are exported with FBX/glTF.
    
---
  #### **Id**
bad-boolean-cleanup
  #### **Name**
Poor Boolean Cleanup
  #### **Description**
    Leaving boolean operations without cleaning up the resulting geometry,
    leading to n-gons, overlapping faces, and non-manifold edges.
    
  #### **Why Bad**
    - Creates n-gons that must be fixed later
    - Can create non-manifold geometry
    - Causes shading issues
    - Makes topology unusable for animation
    - Subdivision creates artifacts
    
  #### **What To Do Instead**
    After boolean operations:
    1. Check for n-gons and triangulate/quad-ify
    2. Merge vertices by distance (M → By Distance)
    3. Check for non-manifold geometry
    4. Verify all normals are correct
    
    Better: Use the Exact boolean solver and plan cuts to avoid cleanup.
    
---
  #### **Id**
texel-density-inconsistency
  #### **Name**
Inconsistent Texel Density
  #### **Description**
    UV islands with wildly different texel densities, causing some surfaces
    to appear blurry while others are sharp.
    
  #### **Why Bad**
    - Visual inconsistency is immediately noticeable
    - Important surfaces may be under-detailed
    - Unimportant surfaces waste texture space
    - Makes the asset look unprofessional
    
  #### **What To Do Instead**
    1. Set a target texel density for the project
    2. Use the Texel Density Checker add-on
    3. Adjust UV island scale to match density (Average Islands Scale, Ctrl+A in UV Editor)
    4. Intentionally vary density only for hero vs background areas
    
---
  #### **Id**
modeling-at-wrong-scale
  #### **Name**
Modeling at Wrong Scale
  #### **Description**
    Creating models at arbitrary scale instead of real-world units, causing
    issues when combining assets.
    
  #### **Why Bad**
    - Assets don't fit together
    - Physics behaves incorrectly
    - Lighting/shadows look wrong
    - Texture density becomes unpredictable
    - Modular pieces don't snap
    
  #### **What To Do Instead**
    Set up your scene with correct units from the START:
    - Scene Properties → Units → Metric, Unit Scale 1.0
    - Model at 1 unit = 1 meter
    - Use reference objects (standard door = 2.1m height, 0.9m width)
    
---
  #### **Id**
dense-topology-everywhere
  #### **Name**
Dense Topology Where Not Needed
  #### **Description**
    Adding the same topology density everywhere regardless of visibility,
    deformation needs, or silhouette importance.
    
  #### **Why Bad**
    - Wastes performance budget
    - Makes editing harder
    - Increases file size
    - Slows down rendering
    - Makes rigging more difficult
    
  #### **What To Do Instead**
    Distribute polygons based on:
    1. Deformation needs (more at joints)
    2. Silhouette importance (more at edges)
    3. Camera proximity (more on hero areas)
    4. Detail requirements (more where normal maps can't fake it)

---
  #### **Id**
bpy-ops-in-loops
  #### **Name**
Calling `bpy.ops` Inside Loops
  #### **Description**
    Spawning, duplicating, transforming, or modifying hundreds of objects by
    calling `bpy.ops.*` inside a `for` loop.
    
  #### **Why Bad**
    - Every `bpy.ops` call triggers a full dependency-graph update and undo step
    - Turns $O(N)$ work into $O(N^2)$ viewport stalls or MCP socket timeouts
    - Fails with `RuntimeError: Operator poll() failed` in headless/background mode
    
  #### **What To Do Instead**
    Build the `Mesh` datablock once via `bpy.data.meshes.new()` + `from_pydata()`,
    create objects with `bpy.data.objects.new(name, shared_mesh)`, link them to
    `collection.objects.link(obj)`, and call `bpy.context.view_layer.update()`
    once after the loop.
    
---
  #### **Id**
unbeveled-razor-edges
  #### **Name**
Razor-Sharp 90° Hard-Surface Edges
  #### **Description**
    Leaving raw primitives and boolean cuts with mathematically sharp 90° edges
    and zero bevel.
    
  #### **Why Bad**
    - Edges catch zero specular light, making objects look flat and unmistakably CG
    - Normal maps cannot bake edge highlights from a 0-width edge
    - Violates real-world manufacturing physics
    
  #### **What To Do Instead**
    Add a `BEVEL` modifier (`width = 0.001..0.005`, `segments = 2..3`,
    `limit_method = 'ANGLE'` or `'WEIGHT'`, `harden_normals = True`) followed by
    `WEIGHTED_NORMAL` and `shade_smooth_by_angle`.
    
---
  #### **Id**
srgb-on-noncolor-data
  #### **Name**
Leaving Data Maps (Normal / Roughness / Metallic / Displacement) on `sRGB`
  #### **Description**
    Loading Normal, Roughness, Metallic, AO, ORM, or Height textures without
    switching `image.colorspace_settings.name` from `'sRGB'` to `'Non-Color'`.
    
  #### **Why Bad**
    - Applies a ~2.2 gamma curve to mathematical vector/float data
    - Tilts normal map vectors by ~26°, producing dark directional seams
    - Crushes mid-tone roughness and shifts 0.5 displacement midpoints to ~0.214
    
  #### **What To Do Instead**
    Immediately after `bpy.data.images.load(path)`, set
    `img.colorspace_settings.name = 'Non-Color'` for every non-albedo/non-emission map.
    
---
  #### **Id**
pure-black-or-white-albedo
  #### **Name**
Physically Impossible `0.0` Black or `1.0` White Albedo
  #### **Description**
    Setting Principled BSDF `Base Color` to pure white `(1, 1, 1, 1)` or pure
    black `(0, 0, 0, 1)`.
    
  #### **Why Bad**
    - `1.0` reflects 100% of light on every bounce, blowing out highlights,
      flattening contact shadows, and spawning Cycles fireflies
    - `0.0` absorbs 100% of light, killing all surface shading and bounce light
    
  #### **What To Do Instead**
    Keep dielectric linear albedo within **`[0.03, 0.85]`** (charcoal/asphalt
    `0.03–0.05`, fresh snow/white paint `0.80–0.85`). Keep roughness in `[0.02, 0.98]`.
    
---
  #### **Id**
blind-generation-without-visual-audit
  #### **Name**
Blind Script Generation Without Bounding-Box & Visual Audit
  #### **Description**
    Assuming a `bpy` script succeeded because it exited with return code `0`,
    without checking world-space bounding boxes, BVH overlaps, or a rendered frame.
    
  #### **Why Bad**
    - Over 70% of agent 3D errors are silent spatial bugs (floating objects,
      buried geometry, interpenetrating props, radians-vs-degrees rotation bugs,
      or cameras pointing at empty space)
    
  #### **What To Do Instead**
    Always run `audit_scene()` (world BBox ground check, BVH overlap check,
    camera frustum check) and render a diagnostic viewport/Cycles preview from
    at least 2 angles to verify before finishing.
