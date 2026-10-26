"""blender_qc.py - read-only QC audit of a Blender scene (Blender 4.2 - 5.x).

Runs INSIDE Blender. It never saves the file and restores frame/selection.

Headless (preferred - audits what is on disk):
    blender -b scene.blend --factory-startup --python-exit-code 1 \
        --python blender_qc.py -- --out qc.json --md qc.md [--intent intent.json]

Live session (e.g. an MCP "execute code" tool):
    import runpy
    runpy.run_path("/path/to/blender_qc.py", run_name="__main__",
                   init_globals={"QC_ARGV": ["--out", "/tmp/qc.json"]})

Options (all optional):
    --out PATH          JSON report path (default: <blend dir>/qc_out/qc.json or ./qc.json)
    --md PATH           Markdown summary path (default: next to JSON)
    --intent PATH       JSON intent / waiver file (see references/intent.md)
    --physics MODE      realistic | stylized | off   (overrides intent)
    --simulate MODE     auto | on | off  - step rigid body / cloth sims (default auto)
    --sim-frames N      max frames to simulate (default 250)
    --anim-samples N    max animation frames to sample (default 120)
    --time-budget S     soft time budget for expensive checks (default 300)
    --fail-exit         exit code 2 when FAIL findings exist (headless only)
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import math
import os
import re
import sys
import time
import traceback

import bpy
import bmesh  # noqa: F401  (kept for users extending checks)
import numpy as np
from mathutils import Matrix, Vector
from mathutils import geometry as mgeo
from mathutils.bvhtree import BVHTree

QC_VERSION = "1.0.0"
GEOM_TYPES = {"MESH", "CURVE", "SURFACE", "META", "FONT"}
SEV_ORDER = {"FAIL": 0, "WARN": 1, "INFO": 2}

# Objects that are allowed to float / have no support (name keywords).
AIRBORNE_WORDS = {
    "cloud", "sky", "sun", "moon", "star", "planet", "bird", "balloon", "drone", "aircraft",
    "airplane", "helicopter", "butterfly", "firefly", "smoke", "fog", "mist", "dust", "spark",
    "particle", "ufo", "satellite", "kite", "bubble", "snowflake", "raindrop", "fly", "bee",
    "hologram", "halo", "glow", "flare", "volume", "haze", "godray",
}
# Things normally fixed to walls / ceilings rather than resting on something below.
MOUNT_WORDS = {
    "frame", "picture", "painting", "poster", "clock", "shelf", "sconce", "mirror", "tv",
    "television", "sign", "window", "door", "curtain", "hook", "light", "lamp", "fan",
    "chandelier", "pendant", "bracket", "rail", "rod", "blind", "vent", "switch", "socket",
    "outlet", "speaker", "cabinet", "board", "plaque", "flag", "banner", "wall", "ceiling",
    "beam", "pipe", "cable", "wire", "rope", "chain", "hinge", "handle", "knob",
}
# Soft / compressible materials: a few cm of overlap is a believable contact.
SOFT_WORDS = {
    "rug", "carpet", "mat", "cushion", "pillow", "mattress", "blanket", "duvet", "towel",
    "cloth", "fabric", "grass", "snow", "sand", "mud", "water", "foam", "bed", "sofa",
    "couch", "beanbag", "moss", "leaf", "leaves", "hair", "fur", "cape", "curtain", "sheet",
    "figure", "person", "human", "character", "body", "man", "woman", "skin", "dress",
}
ARCH_WORDS = {
    "floor", "ground", "terrain", "landscape", "wall", "walls", "ceiling", "roof", "room",
    "sky", "skydome", "dome", "backdrop", "cyclorama", "environment", "world", "plane",
    "baseboard", "skirting", "interior", "shell", "window", "door", "doorway", "sill", "jamb",
    "lintel", "molding", "moulding", "trim", "cornice", "column", "pillar", "stair", "stairs",
    "railing", "banister", "fireplace", "mantel", "facade", "architecture", "building",
}
CARD_WORDS = {"backdrop", "card", "bg", "background", "matte", "skydome", "sky", "hdri", "billboard",
              "cyclorama", "plate"}
# Tokens that name a component of a larger object (scale is judged on the whole asset).
PART_WORDS = {
    "leg", "legs", "top", "bottom", "base", "seat", "back", "backrest", "arm", "armrest", "shade",
    "pole", "stem", "stand", "foot", "feet", "handle", "knob", "lid", "cap", "frame", "panel",
    "slab", "drawer", "body", "blob", "label", "screen", "bezel", "rim", "spout", "strap", "wheel",
    "tire", "tyre", "axle", "hinge", "rod", "rail", "post", "plinth", "platter", "tonearm", "lip",
    "trim", "edge", "side", "head", "neck", "string", "button", "led", "bulb", "socket", "cord",
    "cable", "wire", "chain", "hook", "bracket", "mount", "support", "brace", "crossbar", "apron",
    "stretcher", "skirt", "sill", "jamb", "pane", "sash", "glass", "door", "shelf", "cushion",
    "pillow", "front", "face", "tip", "half", "piece", "part", "detail", "decal", "sticker",
}
GENERIC_WORDS = {"prop", "props", "obj", "object", "mesh", "geo", "geom", "sm", "set", "asset",
                 "mdl", "model", "item", "grp", "group", "node", "new", "copy", "final", "root",
                 "empty", "rig", "ctrl", "low", "high", "lod", "proxy", "inst", "instance", "col"}
SIDE_WORDS = {"left", "right", "upper", "lower", "inner", "outer", "north", "south", "east", "west",
              "mid", "middle", "center", "centre", "main", "small", "large", "big", "tall", "short"}
INDEX_RE = re.compile(r"^(?:[a-z]{0,2}\d+[a-z]?|[a-z])$")
GROUND_WORDS = {"floor", "ground", "terrain", "landscape", "plane", "grass", "lawn", "road",
                "street", "pavement", "earth", "soil", "desert", "seabed", "field"}

# Typical real-world sizes (metres). metric: height=z extent, max=largest extent,
# length=largest horizontal extent. Deliberately generous ranges; heuristics, not law.
SIZE_TABLE = [
    ({"door"}, "height", 1.8, 2.6),
    ({"table", "desk"}, "height", 0.3, 1.15),
    ({"chair", "stool", "armchair"}, "height", 0.4, 1.3),
    ({"sofa", "couch"}, "length", 1.2, 3.6),
    ({"bed"}, "length", 1.3, 2.5),
    ({"person", "human", "man", "woman", "character", "figure", "body", "people"}, "max", 0.9, 2.2),
    ({"mug", "cup", "teacup"}, "max", 0.05, 0.2),
    ({"bottle"}, "max", 0.08, 0.5),
    ({"book"}, "max", 0.08, 0.5),
    ({"laptop"}, "max", 0.25, 0.45),
    ({"phone", "smartphone"}, "max", 0.1, 0.2),
    ({"car", "sedan", "suv", "hatchback"}, "length", 2.5, 6.5),
    ({"truck", "bus", "lorry"}, "length", 4.0, 20.0),
    ({"tree"}, "height", 1.5, 70.0),
    ({"house", "building", "tower", "skyscraper"}, "height", 2.5, 900.0),
    ({"lamp"}, "height", 0.15, 2.3),
    ({"window"}, "max", 0.3, 4.0),
    ({"apple", "orange", "peach", "lemon"}, "max", 0.04, 0.13),
    ({"ball", "football", "basketball", "soccerball"}, "max", 0.02, 0.35),
    ({"plate", "dish", "bowl"}, "max", 0.08, 0.4),
    ({"fridge", "refrigerator"}, "height", 1.2, 2.1),
    ({"tv", "television", "monitor"}, "max", 0.3, 2.6),
    ({"bookshelf", "bookcase", "shelving"}, "height", 0.5, 2.7),
    ({"counter", "countertop"}, "height", 0.8, 1.15),
    ({"cat", "kitten"}, "max", 0.2, 0.8),
    ({"dog", "puppy"}, "max", 0.2, 1.3),
    ({"horse"}, "height", 1.1, 2.1),
    ({"bicycle", "bike"}, "length", 1.2, 2.0),
    ({"guitar"}, "max", 0.8, 1.15),
    ({"piano"}, "max", 1.2, 2.9),
    ({"pencil", "pen"}, "max", 0.1, 0.2),
    ({"vinyl", "lp", "record"}, "max", 0.17, 0.32),
    ({"pillow", "cushion"}, "max", 0.25, 0.9),
    ({"vase"}, "max", 0.08, 0.9),
    ({"candle"}, "max", 0.03, 0.45),
    ({"keyboard"}, "max", 0.25, 1.5),
    ({"rug", "carpet"}, "max", 0.4, 7.0),
]


# --------------------------------------------------------------------------- helpers

def V(p):
    return Vector((float(p[0]), float(p[1]), float(p[2])))


def tokens(name: str) -> list[str]:
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    toks = [t.lower() for t in re.split(r"[^A-Za-z0-9]+", name) if t]
    out = []
    for t in toks:
        if t.isdigit():
            continue
        out.append(t)
        if len(t) > 3 and t.endswith("s"):
            out.append(t[:-1])
    return out


def core_tokens(name: str) -> list[str]:
    """Ordered lowercase name tokens with index-like tokens (01, n03, a) removed."""
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name.split(">")[0])
    toks = [t.lower() for t in re.split(r"[^A-Za-z0-9]+", name) if t]
    return [t for t in toks if not INDEX_RE.match(t)]


def same_asset(n1: str, n2: str) -> bool:
    """'Table_Top' & 'Table_Leg_1' -> True; 'Chair.001' & 'Chair.002' -> False (two copies);
    'prop__book_n01' & 'prop__shelf_02' -> False (only a generic prefix in common)."""
    t1, t2 = core_tokens(n1), core_tokens(n2)
    if not t1 or not t2 or t1 == t2:
        return False
    common = []
    for x, y in zip(t1, t2):
        if x != y:
            break
        common.append(x)
    return any(t not in GENERIC_WORDS for t in common)


def head_noun(tok: list[str]) -> str | None:
    """Last meaningful token, or None when the name ends in a part word ('desk_top')."""
    tok = [t for t in tok if t not in GENERIC_WORDS and t not in SIDE_WORDS]
    if not tok or (tok[-1] in PART_WORDS and len(tok) > 1):
        return None
    return tok[-1]


def has_word(name: str, words: set[str]) -> bool:
    return any(t in words for t in tokens(name))


def fmt_m(x: float) -> str:
    x = float(x)
    if abs(x) < 0.01:
        return f"{x * 1000:.1f} mm"
    if abs(x) < 1.0:
        return f"{x * 100:.1f} cm"
    return f"{x:.2f} m"


def mat_np(m: Matrix) -> np.ndarray:
    return np.array([list(r) for r in m], dtype=np.float64)


def lum(rgb) -> float:
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def finite_matrix(m) -> bool:
    return all(math.isfinite(v) for row in m for v in row)


# --------------------------------------------------------------------------- intent

class Intent:
    def __init__(self, data: dict | None, physics_override: str | None):
        d = data or {}
        self.raw = d
        self.physics = (physics_override or d.get("physics") or "realistic").lower()
        if self.physics not in {"realistic", "stylized", "off"}:
            self.physics = "realistic"
        self.target = (d.get("target") or "render").lower()  # render|realtime|print|export
        self.ground = d.get("ground", "auto")
        self.subjects = list(d.get("subjects") or [])
        self.ignore = list(d.get("ignore") or [])
        allow = d.get("allow") or {}
        self.allow = {k: allow.get(k) or [] for k in
                      ("floating", "intersect", "scale", "animation", "stability", "camera")}
        tol = d.get("tolerances") or {}
        self.contact_m = float(tol.get("contact_m", 0.005))
        self.penetration_m = float(tol.get("penetration_m", 0.005))
        self.expect = d.get("expect") or {}
        self.notes = d.get("notes", "")

    def ignored(self, name: str) -> bool:
        return any(fnmatch.fnmatchcase(name, p) for p in self.ignore)

    def _obj_prop_allows(self, name: str, kind: str) -> bool:
        ob = bpy.data.objects.get(name.split(">")[0])
        if ob is None:
            return False
        val = str(ob.get("qc_allow", "")).lower()
        return bool(val) and (kind in val or "all" in val)

    def waiver(self, kind: str, names: list[str]) -> str | None:
        pats = self.allow.get(kind, [])
        if kind == "intersect" and len(names) >= 2:
            a, b = names[0], names[1]
            for p in pats:
                if isinstance(p, (list, tuple)) and len(p) == 2:
                    pa, pb = p
                    if (fnmatch.fnmatchcase(a, pa) and fnmatch.fnmatchcase(b, pb)) or \
                       (fnmatch.fnmatchcase(a, pb) and fnmatch.fnmatchcase(b, pa)):
                        return f"intent.allow.intersect {p}"
                elif isinstance(p, str) and (fnmatch.fnmatchcase(a, p) or fnmatch.fnmatchcase(b, p)):
                    return f"intent.allow.intersect '{p}'"
            if self._obj_prop_allows(a, "intersect") or self._obj_prop_allows(b, "intersect"):
                return "object property qc_allow"
            return None
        for n in names:
            for p in pats:
                if isinstance(p, str) and fnmatch.fnmatchcase(n, p):
                    return f"intent.allow.{kind} '{p}'"
            if self._obj_prop_allows(n, kind):
                return "object property qc_allow"
        return None


# --------------------------------------------------------------------------- report

class Report:
    def __init__(self, intent: Intent):
        self.intent = intent
        self.findings: list[dict] = []
        self.checks: list[dict] = []
        self.skipped: list[str] = []

    def add(self, fid, sev, cat, msg, objects=(), evidence=None, fix=None,
            physics=False, waive=None):
        if physics:
            if self.intent.physics == "off":
                return
            if self.intent.physics == "stylized":
                sev = {"FAIL": "WARN", "WARN": "INFO"}.get(sev, sev)
        objects = [str(o) for o in objects]
        waived = self.intent.waiver(waive, objects) if waive else None
        if waived:
            sev = "INFO"
        self.findings.append({
            "id": fid, "severity": sev, "category": cat, "message": msg,
            "objects": objects[:25], "evidence": evidence or {}, "fix": fix,
            "waived": waived,
        })

    def run(self, name, fn, *args):
        t0 = time.time()
        try:
            fn(*args)
            status = "ok"
        except Exception as exc:  # a check must never kill the audit
            status = "error"
            self.add("qc.check_error", "WARN", "qc",
                     f"Check '{name}' crashed - its area is NOT verified: {exc}",
                     evidence={"traceback": traceback.format_exc()[-1500:]})
        self.checks.append({"check": name, "status": status, "seconds": round(time.time() - t0, 3)})


# --------------------------------------------------------------------------- scene model

class Entry:
    """World-space triangle soup for one renderable object or instance."""

    def __init__(self, name, ob, local, tris, M, inst=False, nverts_orig=0):
        self.name = name
        self.ob = ob
        self.local = local
        self.tris = tris
        self.inst = inst
        self.closed = _closed(tris)
        self.local_volume = _signed_volume(local, tris)
        self.container = False
        self.ground = False
        self.arch = has_word(name, ARCH_WORDS)
        self.soft = has_word(name, SOFT_WORDS)
        self.volume = False        # volume-only material (haze, fog): not a solid
        self.card = has_word(name, CARD_WORDS)  # emission-only backdrop / sky card
        self.transmissive = False  # glass, alpha < 1: light and sight pass through
        self.group = None
        self.nverts = nverts_orig or len(local)
        self.set_matrix(M)

    def set_matrix(self, M: np.ndarray):
        self.M = M
        self.W = self.local @ M[:3, :3].T + M[:3, 3]
        self.bmin = self.W.min(axis=0)
        self.bmax = self.W.max(axis=0)
        self.dims = self.bmax - self.bmin
        self._bvh = None

    def moved(self, M):
        e = Entry.__new__(Entry)
        e.__dict__.update(self.__dict__)
        e.set_matrix(M)
        return e

    @property
    def bvh(self) -> BVHTree:
        if self._bvh is None:
            self._bvh = BVHTree.FromPolygons(self.W.tolist(), self.tris.tolist(),
                                             all_triangles=True, epsilon=0.0)
        return self._bvh

    def com(self) -> np.ndarray:
        W, T = self.W, self.tris
        v0, v1, v2 = W[T[:, 0]], W[T[:, 1]], W[T[:, 2]]
        if self.closed:
            vol = np.einsum("ij,ij->i", v0, np.cross(v1, v2)) / 6.0
            tot = vol.sum()
            if abs(tot) > 1e-12:
                return ((v0 + v1 + v2) / 4.0 * vol[:, None]).sum(axis=0) / tot
        area = np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1)
        if area.sum() > 0:
            return ((v0 + v1 + v2) / 3.0 * area[:, None]).sum(axis=0) / area.sum()
        return W.mean(axis=0)


def _closed(tris: np.ndarray) -> bool:
    if len(tris) < 4:
        return False
    e = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    e.sort(axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return bool((counts == 2).all())


def _signed_volume(co: np.ndarray, tris: np.ndarray) -> float:
    if len(tris) == 0:
        return 0.0
    v0, v1, v2 = co[tris[:, 0]], co[tris[:, 1]], co[tris[:, 2]]
    return float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)


def fcurves_of(idb) -> list:
    """F-curves of an ID's assigned action (works with 4.4+ slotted actions; Action.fcurves is gone in 5.0)."""
    ad = getattr(idb, "animation_data", None)
    if not ad or not ad.action:
        return []
    act = ad.action
    if hasattr(act, "fcurves"):
        return list(act.fcurves)
    try:
        from bpy_extras.anim_utils import action_get_channelbag_for_slot
        cb = action_get_channelbag_for_slot(act, ad.action_slot)
        return list(cb.fcurves) if cb else []
    except Exception:
        return []


def material_kind(ob) -> dict:
    """Classify an object's materials: volume-only, emission-only, transmissive."""
    mats = [s.material for s in getattr(ob, "material_slots", []) if s.material]
    if not mats:
        return {"volume": False, "emissive_only": False, "transmissive": False}
    vol = emi = trans = 0
    for m in mats:
        nt = getattr(m, "node_tree", None)
        if nt is None:
            continue
        out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None) or \
            next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
        if out is None:
            continue
        surf, volu = out.inputs["Surface"], out.inputs["Volume"]
        if volu.is_linked and not surf.is_linked:
            vol += 1
            continue
        if not surf.is_linked:
            continue
        types = {n.type for n in nt.nodes}
        if surf.links[0].from_node.type in {"EMISSION", "HOLDOUT"} or (
                types & {"EMISSION"} and not types & {"BSDF_PRINCIPLED", "BSDF_DIFFUSE", "BSDF_GLOSSY"}):
            emi += 1
        if types & {"BSDF_GLASS", "BSDF_TRANSPARENT", "BSDF_REFRACTION", "BSDF_TRANSLUCENT"}:
            trans += 1
        for n in nt.nodes:
            if n.type == "BSDF_PRINCIPLED":
                tw, al = n.inputs.get("Transmission Weight"), n.inputs.get("Alpha")
                if (tw is not None and (tw.is_linked or tw.default_value > 0.3)) or \
                        (al is not None and (al.is_linked or al.default_value < 0.7)):
                    trans += 1
                    break
    return {"volume": vol == len(mats), "emissive_only": emi == len(mats), "transmissive": trans > 0}


def mesh_arrays(ob_eval):
    """(local co Nx3, tris Mx3, uv_count, mesh stats dict) from an evaluated object."""
    me = ob_eval.to_mesh()
    try:
        n = len(me.vertices)
        co = np.empty(n * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(n, 3).astype(np.float64)
        me.calc_loop_triangles()
        t = len(me.loop_triangles)
        tri = np.empty(t * 3, dtype=np.int32)
        me.loop_triangles.foreach_get("vertices", tri)
        tri = tri.reshape(t, 3)
        stats = mesh_stats(me, co) if n <= 300_000 else {"skipped": f"{n} verts > 300k"}
        stats["uv_layers"] = len(me.uv_layers)
        stats["verts"] = n
        stats["faces"] = len(me.polygons)
        stats["tris"] = t
        return co, tri, stats
    finally:
        ob_eval.to_mesh_clear()


def mesh_stats(me, co: np.ndarray) -> dict:
    ne = len(me.edges)
    ev = np.empty(ne * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(ne, 2)
    # faces per edge
    np_ = len(me.polygons)
    loop_edges = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("edge_index", loop_edges)
    face_count = np.bincount(loop_edges, minlength=ne) if ne else np.zeros(0, dtype=np.int64)
    boundary = int((face_count == 1).sum())
    wire = int((face_count == 0).sum())
    over = int((face_count > 2).sum())
    used = np.zeros(len(co), dtype=bool)
    if ne:
        used[ev.ravel()] = True
    loose_verts = int((~used).sum())
    sizes = np.empty(np_, dtype=np.int32)
    me.polygons.foreach_get("loop_total", sizes)
    areas = np.empty(np_, dtype=np.float32)
    me.polygons.foreach_get("area", areas)
    ext = float(np.ptp(co, axis=0).max()) if len(co) else 0.0
    degenerate = int((areas <= (ext * 1e-6) ** 2).sum()) if np_ else 0
    # inconsistent winding: a manifold edge whose two faces traverse it the same direction
    inconsistent = 0
    if np_ and ne:
        lv = np.empty(len(me.loops), dtype=np.int32)
        me.loops.foreach_get("vertex_index", lv)
        starts = np.empty(np_, dtype=np.int32)
        me.polygons.foreach_get("loop_start", starts)
        nxt = np.arange(len(lv)) + 1
        ends = np.repeat(starts + sizes, sizes)
        nxt = np.where(nxt == ends, np.repeat(starts, sizes), nxt)
        a, b = lv, lv[nxt]
        direction = (a < b).astype(np.int8) * 2 - 1
        manifold = face_count[loop_edges] == 2
        s = np.zeros(ne, dtype=np.int32)
        np.add.at(s, loop_edges[manifold], direction[manifold])
        inconsistent = int((np.abs(s[face_count == 2]) == 2).sum())
    dup = 0
    if len(co) and ext > 0:
        q = np.round(co / (ext * 1e-6 + 1e-9)).astype(np.int64)
        dup = int(len(q) - len(np.unique(q, axis=0)))
    return {"boundary_edges": boundary, "wire_edges": wire, "nonmanifold_edges": over,
            "loose_verts": loose_verts, "ngons": int((sizes > 4).sum()) if np_ else 0,
            "degenerate_faces": degenerate, "inconsistent_edges": inconsistent,
            "duplicate_verts": dup, "nan": bool(not np.isfinite(co).all())}


# --------------------------------------------------------------------------- audit

class Audit:
    def __init__(self, args, intent: Intent):
        self.args = args
        self.intent = intent
        self.rep = Report(intent)
        self.scene = bpy.context.scene
        self.vl = bpy.context.view_layer
        self.dg = bpy.context.evaluated_depsgraph_get()
        self.U = self.scene.unit_settings.scale_length or 1.0  # BU * U = metres
        self.t0 = time.time()
        self.entries: list[Entry] = []
        self.by_name: dict[str, Entry] = {}
        self.mesh_info: dict[str, dict] = {}
        self.relations: dict[tuple[int, int], dict] = {}
        self.groups: list[list[int]] = []
        self.inventory: list[dict] = []
        self.render_cols = self._collection_render_map()
        self.moving: set[int] = set()
        self.scene_size = 1.0
        self.scene_min = self.scene_max = np.zeros(3)
        self.supported: set[int] = set()
        self.animated: set[str] = set()   # keyframed / constrained / driven objects
        self.dynamic: set[str] = set()    # active rigid bodies, cloth, soft bodies
        self.hier_groups: set[int] = set()

    def detect_dynamic(self):
        sc = self.scene
        rbw = sc.rigidbody_world
        if rbw and rbw.collection:
            for o in rbw.collection.objects:
                if o.rigid_body and o.rigid_body.type == "ACTIVE" and not o.rigid_body.kinematic:
                    self.dynamic.add(o.name)
        for o in sc.objects:
            if any(md.type in {"CLOTH", "SOFT_BODY"} for md in getattr(o, "modifiers", [])):
                self.dynamic.add(o.name)

        def anim(ob, depth=0):
            if ob is None or depth > 32:
                return False
            ad = ob.animation_data
            if ad and (ad.action or len(ad.drivers) or len(ad.nla_tracks)):
                return True
            if any(c.type in {"FOLLOW_PATH", "CHILD_OF", "COPY_LOCATION", "COPY_TRANSFORMS",
                              "TRACK_TO", "DAMPED_TRACK", "PIVOT", "CLAMP_TO"} and not c.mute
                   for c in ob.constraints):
                return True
            for md in getattr(ob, "modifiers", []):
                if md.type == "ARMATURE" and md.object is not None and anim(md.object, depth + 1):
                    return True
            return anim(ob.parent, depth + 1)
        for o in sc.objects:
            if anim(o):
                self.animated.add(o.name)

    def is_dynamic(self, e: "Entry") -> bool:
        return e.name in self.animated or e.name in self.dynamic

    # ---- units / tolerances
    def m(self, bu: float) -> float:
        return float(bu) * self.U

    def bu(self, metres: float) -> float:
        return float(metres) / self.U

    def over_budget(self) -> bool:
        return time.time() - self.t0 > self.args.time_budget

    def ctol(self, a: Entry, b: Entry) -> float:
        size = min(float(a.dims.max()), float(b.dims.max()))
        return min(self.bu(self.intent.contact_m), max(self.bu(0.0005), 0.1 * size))

    def ptol(self, a: Entry, b: Entry) -> float:
        da = [d for d in a.dims if d > 1e-9] or [a.dims.max()]
        db = [d for d in b.dims if d > 1e-9] or [b.dims.max()]
        size = min(min(da), min(db))
        tol = min(self.bu(self.intent.penetration_m), max(self.bu(0.001), 0.1 * size))
        if a.soft or b.soft:
            tol = max(tol, self.bu(0.03))
        return tol

    # ---- visibility
    def _collection_render_map(self) -> dict:
        res = {}

        def walk(lc, ok):
            ok = ok and not lc.exclude and not lc.collection.hide_render
            res[lc.collection.name] = res.get(lc.collection.name, False) or ok
            for c in lc.children:
                walk(c, ok)
        walk(self.vl.layer_collection, True)
        return res

    def renders(self, ob) -> bool:
        if ob.hide_render:
            return False
        if ob.parent and ob.parent.instance_type in {"VERTS", "FACES"}:
            return False
        return any(self.render_cols.get(c.name, False) for c in ob.users_collection)

    # ---- build
    def build_entries(self):
        scene, dg = self.scene, self.dg
        for ob in scene.objects:
            if ob.type not in GEOM_TYPES or self.intent.ignored(ob.name):
                continue
            if not self.renders(ob):
                continue
            if not finite_matrix(ob.matrix_world):
                continue  # reported by transforms check
            try:
                try:
                    co, tri, stats = mesh_arrays(ob.evaluated_get(dg))
                except Exception:
                    if ob.type != "MESH":
                        raise
                    co, tri, stats = mesh_arrays(ob)  # viewport-disabled: original data, no modifiers
            except Exception as exc:
                self.rep.add("geometry.eval_failed", "WARN", "geometry",
                             f"Could not evaluate '{ob.name}' to a mesh: {exc}", [ob.name])
                continue
            self.mesh_info[ob.name] = stats
            if len(tri) == 0 or not np.isfinite(co).all():
                continue
            M = mat_np(ob.evaluated_get(dg).matrix_world)
            e = Entry(ob.name, ob, co, tri, M, nverts_orig=len(co))
            mk = material_kind(ob)
            e.volume, e.transmissive = mk["volume"], mk["transmissive"]
            e.card = e.card or mk["emissive_only"]
            self._add_entry(e)
        # Instances (geometry nodes / collection instances).
        cache, count, skipped = {}, 0, 0
        for inst in dg.object_instances:
            if not inst.is_instance:
                continue
            obj = inst.object
            if obj.type not in GEOM_TYPES:
                continue
            parent = inst.parent.name if inst.parent else "?"
            if self.intent.ignored(parent) or self.intent.ignored(obj.name):
                continue
            if count >= 400:
                skipped += 1
                continue
            key = obj.original.name if obj.original else obj.name
            if key == parent:
                continue  # curve/text objects expose their own evaluated mesh as an instance
            if key not in cache:
                try:
                    co, tri, _ = mesh_arrays(obj)
                except Exception:
                    co, tri = np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32)
                cache[key] = (co, tri)
            co, tri = cache[key]
            if len(tri) == 0:
                continue
            count += 1
            M = mat_np(inst.matrix_world.copy())
            self._add_entry(Entry(f"{parent}>{key}#{count}", None, co, tri, M, inst=True))
        if skipped:
            self.rep.add("physics.instances_skipped", "INFO", "physics",
                         f"{skipped} instances beyond the first 400 were not checked individually.",
                         evidence={"skipped": skipped})

    def _add_entry(self, e: Entry):
        self.by_name[e.name] = e
        self.entries.append(e)

    def classify(self):
        ents = self.entries
        if not ents:
            return
        bmin = np.array([e.bmin for e in ents])
        bmax = np.array([e.bmax for e in ents])
        centers = (bmin + bmax) / 2
        smin, smax = bmin.min(0), bmax.max(0)
        self.scene_min, self.scene_max = smin, smax
        self.scene_size = float(np.linalg.norm(smax - smin)) or 1.0
        # containers: bbox holds most other objects' centres (room shells, sky domes)
        if len(ents) >= 4:
            for i, e in enumerate(ents):
                if e.volume or e.card:
                    continue
                inside = np.all((centers >= e.bmin - 1e-6) & (centers <= e.bmax + 1e-6), axis=1)
                inside[i] = False
                if inside.sum() >= 0.6 * (len(ents) - 1):
                    e.container = True
        # ground
        g = self.intent.ground
        if isinstance(g, str) and g not in ("auto", "none") and g:
            for e in ents:
                if fnmatch.fnmatchcase(e.name, g) or e.name == g:
                    e.ground = True
        elif g == "auto":
            xy_area = max(float((smax[0] - smin[0]) * (smax[1] - smin[1])), 1e-12)
            for e in ents:
                if e.volume or e.card:
                    continue
                flat = e.dims[2] <= 0.05 * max(e.dims[0], e.dims[1]) + 1e-9
                big = float(e.dims[0] * e.dims[1]) >= 0.25 * xy_area
                low = e.bmax[2] <= smin[2] + 0.1 * (smax[2] - smin[2]) + 1e-6
                named = has_word(e.name, GROUND_WORDS) and float(e.dims[0] * e.dims[1]) >= 0.05 * xy_area
                if (flat and big and low) or (named and low):
                    e.ground = True
            if not any(e.ground or e.container for e in ents):
                self.rep.add("physics.no_ground", "INFO", "physics",
                             "No ground/floor surface detected; support checks treat the lowest "
                             "object cluster as the base. Set intent.ground if this is wrong.",
                             physics=True)

    # ---- pair relations
    def candidate_pairs(self):
        ents = self.entries
        n = len(ents)
        if n < 2:
            return []
        if n > 3000:
            self.rep.add("physics.pairs_skipped", "INFO", "physics",
                         f"{n} entries - pairwise contact checks skipped (cap 3000).")
            return []
        pad = self.bu(self.intent.contact_m)
        bmin = np.array([e.bmin for e in ents]) - pad
        bmax = np.array([e.bmax for e in ents]) + pad
        ov = np.all((bmin[:, None, :] <= bmax[None, :, :]) & (bmin[None, :, :] <= bmax[:, None, :]), axis=2)
        skip = np.array([e.volume or e.card for e in ents])
        ov[skip, :] = False
        ov[:, skip] = False
        iu = np.triu_indices(n, 1)
        mask = ov[iu]
        return list(zip(iu[0][mask].tolist(), iu[1][mask].tolist()))

    def _parity_inside(self, e: Entry, p: Vector) -> bool:
        eps = 1e-6 * self.scene_size + 1e-7
        votes = 0
        for d in (Vector((0.1234, 0.0567, 0.9907)).normalized(),
                  Vector((-0.577, 0.611, 0.541)).normalized()):
            o, hits = p.copy(), 0
            for _ in range(64):
                loc, _n, _i, _dist = e.bvh.ray_cast(o, d)
                if loc is None:
                    break
                hits += 1
                o = loc + d * eps
            votes += hits % 2
        return votes == 2

    def _depth(self, a: Entry, b: Entry, tri_ids) -> float:
        ids = np.unique(np.asarray(tri_ids, dtype=np.int64))
        if len(ids) > 200:
            ids = ids[np.linspace(0, len(ids) - 1, 200).astype(np.int64)]
        tri = a.tris[ids]
        pts = np.concatenate([a.W[np.unique(tri.ravel())], a.W[tri].mean(axis=1)])
        if b.closed and not b.container:
            # Push-out depth along the axis of least bbox overlap (towards a's side):
            # nearest-surface distance underestimates when a sinks past the middle of a thin b.
            ov = np.minimum(a.bmax, b.bmax) - np.maximum(a.bmin, b.bmin)
            ax = int(np.argmin(ov))
            sgn = 1.0 if (a.bmin[ax] + a.bmax[ax]) >= (b.bmin[ax] + b.bmax[ax]) else -1.0
            d_sep = Vector([sgn if k == ax else 0.0 for k in range(3)])
            d = 0.0
            for p in pts:
                pv = V(p)
                if self._parity_inside(b, pv):
                    loc, _n, _i, dist = b.bvh.ray_cast(pv, d_sep)
                    if loc is None:
                        loc, _n, _i, dist = b.bvh.find_nearest(pv)
                    if loc is not None:
                        d = max(d, min(dist, float(ov[ax])))
            return d
        pos = neg = 0.0
        for p in pts:
            pv = V(p)
            loc, nrm, _i, dist = b.bvh.find_nearest(pv)
            if loc is None or dist < 1e-12:
                continue
            c = (pv - loc).dot(nrm) / dist
            if c > 0.5:
                pos = max(pos, dist)
            elif c < -0.5:
                neg = max(neg, dist)
        return min(pos, neg)

    @staticmethod
    def _surface_points(e: Entry, lo, hi, spacing: float, cap: int = 500) -> np.ndarray:
        """Points on e's triangles inside [lo, hi] (vertices alone miss face-to-face gaps
        between rotated low-poly boxes)."""
        T = e.W[e.tris]
        sel = np.all((T.min(axis=1) <= hi) & (T.max(axis=1) >= lo), axis=1)
        T = T[sel]
        if len(T) == 0:
            return np.zeros((0, 3))
        if len(T) > 4000:
            T = T[np.linspace(0, len(T) - 1, 4000).astype(np.int64)]
        edge = np.linalg.norm(T[:, [1, 2, 0]] - T, axis=2).max(axis=1)
        nsub = np.clip(np.ceil(edge / max(spacing, 1e-9)), 1, 10).astype(np.int64)
        pts = [T.reshape(-1, 3), T.mean(axis=1)]
        for k in np.unique(nsub):
            if k <= 1:
                continue
            bc = np.array([(i / k, j / k, 1 - (i + j) / k) for i in range(k + 1) for j in range(k + 1 - i)])
            pts.append(np.einsum("bk,tkd->tbd", bc, T[nsub == k]).reshape(-1, 3))
        P = np.concatenate(pts)
        P = P[np.all((P >= lo) & (P <= hi), axis=1)]
        if len(P) > cap:
            P = P[np.linspace(0, len(P) - 1, cap).astype(np.int64)]
        return P

    def _min_dist(self, a: Entry, b: Entry, ctol: float) -> float:
        """Smallest sampled surface distance, early-exiting once within ctol."""
        lo = np.maximum(a.bmin, b.bmin) - ctol
        hi = np.minimum(a.bmax, b.bmax) + ctol
        spacing = max(ctol * 2, float((hi - lo).max()) / 12)
        best = math.inf
        for src, dst in ((a, b), (b, a)):
            for p in self._surface_points(src, lo, hi, spacing):
                loc, _n, _i, dist = dst.bvh.find_nearest(V(p), ctol * 1.001)
                if loc is not None and dist < best:
                    best = dist
                    if best <= ctol:
                        return best
        return best

    def relate(self, a: Entry, b: Entry) -> dict:
        ctol, ptol = self.ctol(a, b), self.ptol(a, b)
        gap_axes = np.maximum(a.bmin - b.bmax, b.bmin - a.bmax)
        if (gap_axes > ctol).any():
            return {"kind": "separate", "gap": float(gap_axes.max())}
        pairs = a.bvh.overlap(b.bvh)
        if pairs:
            if len(pairs) > 600:
                pairs = pairs[:: max(1, len(pairs) // 600)]
            depth = max(self._depth(a, b, [i for i, _ in pairs]),
                        self._depth(b, a, [j for _, j in pairs]))
            cop, cop_area = 0, 0.0
            for i, j in pairs[:300]:
                ta, tb = a.W[a.tris[i]], b.W[b.tris[j]]
                na = np.cross(ta[1] - ta[0], ta[2] - ta[0])
                nb = np.cross(tb[1] - tb[0], tb[2] - tb[0])
                la, lb = np.linalg.norm(na), np.linalg.norm(nb)
                if la < 1e-14 or lb < 1e-14:
                    continue
                na, nb = na / la, nb / lb
                if na.dot(nb) > 0.9995 and abs((ta.mean(0) - tb[0]).dot(nb)) < 1e-5 * self.scene_size:
                    cop += 1
                    cop_area += min(la, lb) / 2
            ov = np.minimum(a.bmax, b.bmax) - np.maximum(a.bmin, b.bmin)
            ax = int(np.argmin(ov))
            return {"kind": "intersect" if depth > ptol else "contact", "depth": depth,
                    "axis": "xyz"[ax], "axis_extent": float(min(a.dims[ax], b.dims[ax])),
                    "tri_pairs": len(pairs), "coplanar_same_facing": cop, "coplanar_area": cop_area,
                    "ptol": ptol}
        dist = self._min_dist(a, b, ctol)
        if dist <= ctol:
            return {"kind": "contact", "gap": dist}
        dist = float(gap_axes.max()) if not math.isfinite(dist) else dist
        for x, y in ((a, b), (b, a)):
            if y.closed and not y.container and np.all(x.bmin >= y.bmin) and np.all(x.bmax <= y.bmax):
                if self._parity_inside(y, V(x.W.mean(axis=0))):
                    return {"kind": "enclosed", "inner": x.name, "outer": y.name}
        return {"kind": "separate", "gap": dist}

    def build_relations(self):
        ents = self.entries
        pairs = self.candidate_pairs()
        for k, (i, j) in enumerate(pairs):
            if k % 200 == 0 and self.over_budget():
                self.rep.add("qc.time_budget", "WARN", "qc",
                             f"Time budget hit after {k}/{len(pairs)} object pairs; contact/"
                             "intersection results are partial. Re-run with --time-budget higher.")
                break
            a, b = ents[i], ents[j]
            if a.inst and b.inst and a.name.split(">")[0] == b.name.split(">")[0] and len(pairs) > 5000:
                continue
            self.relations[(i, j)] = self.relate(a, b)

    # ---- groups (multi-part assets)
    def build_groups(self):
        ents = self.entries
        parent = list(range(len(ents)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[ry] = rx

        roots = {}
        hier = set()
        for i, e in enumerate(ents):
            r = None
            if e.ob is not None:
                o = e.ob
                while o.parent is not None:
                    o = o.parent
                if o is not e.ob:
                    r = "root:" + o.name
            elif e.inst:
                r = "inst:" + e.name.split(">")[0]
            if r:
                hier.add(i)
                if r in roots:
                    union(roots[r], i)
                else:
                    roots[r] = i
            elif e.ob is not None and e.ob.children:
                hier.add(i)
        for (i, j), rel in self.relations.items():
            if rel["kind"] in ("contact", "intersect", "enclosed") and same_asset(ents[i].name, ents[j].name):
                union(i, j)
        comp = {}
        for i in range(len(ents)):
            comp.setdefault(find(i), []).append(i)
        self.groups = list(comp.values())
        for gi, members in enumerate(self.groups):
            for i in members:
                ents[i].group = gi
            if len(members) > 1 and all(i in hier for i in members):
                self.hier_groups.add(gi)

    def group_tokens(self, members) -> list[str]:
        """Common leading name tokens of a group (or the root object's tokens)."""
        ents = self.entries
        for i in members:
            o = ents[i].ob
            if o is not None and o.parent is None and o.children and len(members) > 1:
                return core_tokens(o.name)
        toks = [core_tokens(ents[i].name) for i in members]
        common = []
        for col in zip(*toks):
            if len(set(col)) != 1:
                break
            common.append(col[0])
        return common

    def group_label(self, members) -> str:
        ents = self.entries
        if len(members) == 1:
            return ents[members[0]].name
        common = [t for t in self.group_tokens(members) if t not in GENERIC_WORDS]
        if common:
            return f"{'_'.join(common)} ({len(members)} parts)"
        for i in members:
            if ents[i].ob is not None and ents[i].ob.parent is None and ents[i].ob.children:
                return f"{ents[i].name} (+{len(members) - 1})"
        return f"{ents[members[0]].name} (+{len(members) - 1})"

    # ------------------------------------------------------------------ checks: file & scene
    def check_file(self):
        rep, sc = self.rep, self.scene
        if not bpy.data.filepath:
            rep.add("file.unsaved", "WARN", "file",
                    "Scene was never saved: relative paths (//) cannot resolve and nothing on disk "
                    "matches what you built.", fix="bpy.ops.wm.save_as_mainfile(filepath=...)")
        elif bpy.data.is_dirty:
            rep.add("file.dirty", "WARN", "file",
                    "Unsaved changes: the .blend on disk differs from the audited state.",
                    fix="Save before rendering/handing off.")
        if getattr(bpy.app, "autoexec_fail", False):
            rep.add("file.autoexec_blocked", "WARN", "file",
                    "Python drivers/scripts were blocked (auto-run disabled) - animation driven by "
                    "them is NOT evaluated in this audit.",
                    evidence={"message": getattr(bpy.app, "autoexec_fail_message", "")},
                    fix="Re-run with --enable-autoexec (run_qc.py --autoexec) if the file is trusted.")
        for lib in bpy.data.libraries:
            p = bpy.path.abspath(lib.filepath)
            if not os.path.exists(p):
                rep.add("file.missing_library", "FAIL", "file",
                        f"Linked library missing: {lib.filepath}", [lib.name])
        us = sc.unit_settings
        if abs((us.scale_length or 1.0) - 1.0) > 1e-6:
            rep.add("scene.unit_scale", "WARN", "scene",
                    f"unit_settings.scale_length = {us.scale_length}: 1 Blender unit = "
                    f"{us.scale_length} m. Physics, light falloff and imports assume 1.0.",
                    fix="Keep scale_length 1.0 and model at real size unless you have a reason.")
        if us.system == "NONE":
            rep.add("scene.unit_system", "INFO", "scene", "Unit system is NONE (unitless).")
        exp = self.intent.expect
        r = sc.render
        if exp.get("fps") and abs(r.fps / r.fps_base - float(exp["fps"])) > 1e-3:
            rep.add("scene.expect_fps", "FAIL", "scene",
                    f"fps is {r.fps / r.fps_base:.3f}, expected {exp['fps']}.")
        if exp.get("frame_range") and [sc.frame_start, sc.frame_end] != list(exp["frame_range"]):
            rep.add("scene.expect_frames", "FAIL", "scene",
                    f"frame range {sc.frame_start}-{sc.frame_end}, expected {exp['frame_range']}.")
        if exp.get("resolution"):
            want = list(exp["resolution"])
            got = [r.resolution_x, r.resolution_y]
            if got != want:
                rep.add("scene.expect_resolution", "FAIL", "scene", f"resolution {got}, expected {want}.")
        if exp.get("engine") and r.engine != exp["engine"]:
            rep.add("scene.expect_engine", "FAIL", "scene", f"engine {r.engine}, expected {exp['engine']}.")
        if exp.get("camera") and (sc.camera is None or sc.camera.name != exp["camera"]):
            rep.add("scene.expect_camera", "FAIL", "scene",
                    f"active camera {sc.camera.name if sc.camera else None}, expected {exp['camera']}.")
        if r.resolution_percentage != 100:
            rep.add("render.resolution_pct", "INFO", "render",
                    f"resolution_percentage = {r.resolution_percentage}% "
                    f"(final output {r.resolution_x * r.resolution_percentage // 100}x"
                    f"{r.resolution_y * r.resolution_percentage // 100}).")
        if r.engine == "CYCLES":
            cy = sc.cycles
            if cy.samples < 16:
                rep.add("render.low_samples", "INFO", "render", f"Cycles samples = {cy.samples}.")
            if cy.device == "CPU":
                rep.add("render.cycles_cpu", "INFO", "render",
                        "Cycles device is CPU (GPU must be enabled in Preferences, which "
                        "--factory-startup resets).")
        vs = sc.view_settings
        if abs(vs.exposure) > 3:
            rep.add("render.exposure", "WARN", "render", f"Color management exposure {vs.exposure:+.1f} stops.")
        if r.filepath.startswith("/tmp") or r.filepath == "":
            rep.add("render.output_path", "INFO", "render",
                    f"Render output path is '{r.filepath}' (default) - set an explicit path.")
        if r.film_transparent:
            rep.add("render.film_transparent", "INFO", "render",
                    "film_transparent is on: background renders as alpha 0 (PNG RGBA needed).")

    # ------------------------------------------------------------------ checks: objects
    def check_objects(self):
        rep, sc = self.rep, self.scene
        scene_objs = set(sc.objects)
        orphan_objs = [o.name for o in bpy.data.objects if not o.users_collection and o.users == 0]
        unlinked = [o.name for o in bpy.data.objects
                    if o not in scene_objs and not o.users_collection and o.type in GEOM_TYPES]
        if unlinked:
            rep.add("objects.unlinked", "WARN", "objects",
                    f"{len(unlinked)} object(s) exist in bpy.data but are linked to no collection - "
                    "they are invisible and will be purged on save.", unlinked,
                    fix="collection.objects.link(obj) - creating with bpy.data.objects.new() does not link it.")
        del orphan_objs
        bool_cutters = set()
        for o in sc.objects:
            for md in getattr(o, "modifiers", []):
                if md.type == "BOOLEAN" and getattr(md, "object", None) is not None:
                    bool_cutters.add(md.object.name)
        sig = {}
        for o in sc.objects:
            if self.intent.ignored(o.name):
                continue
            mw = o.matrix_world
            if not finite_matrix(mw):
                rep.add("transform.nan", "FAIL", "transform", f"'{o.name}' has NaN/inf transform.", [o.name])
                continue
            s = o.matrix_world.to_scale()
            if any(abs(c) < 1e-8 for c in s):
                rep.add("transform.zero_scale", "FAIL", "transform",
                        f"'{o.name}' has a zero scale axis {tuple(round(c, 4) for c in s)} (invisible/degenerate).",
                        [o.name])
            rm = o.rotation_mode
            if rm == "QUATERNION" and any(abs(a) > 1e-6 for a in o.rotation_euler) and \
                    o.rotation_quaternion.angle < 1e-6:
                rep.add("transform.rotation_mode_ignored", "WARN", "transform",
                        f"'{o.name}' has rotation_euler set but rotation_mode is QUATERNION - the euler "
                        "values are ignored, the object is not rotated.", [o.name],
                        fix="Set rotation_quaternion, or obj.rotation_mode = 'XYZ' before rotation_euler.")
            elif rm in {"XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"} and \
                    o.rotation_quaternion.angle > 1e-6 and all(abs(a) < 1e-9 for a in o.rotation_euler):
                rep.add("transform.rotation_mode_ignored", "WARN", "transform",
                        f"'{o.name}' has rotation_quaternion set but rotation_mode is {rm} - ignored.",
                        [o.name], fix="obj.rotation_mode = 'QUATERNION' or set rotation_euler.")
            if o.type not in GEOM_TYPES:
                continue
            renders = self.renders(o)
            if o.matrix_world.determinant() < 0:
                rep.add("transform.negative_scale", "WARN" if self.intent.target != "render" else "INFO",
                        "transform", f"'{o.name}' is mirrored by negative scale "
                        f"{tuple(round(c, 3) for c in o.scale)}; normals/physics/exports can flip.",
                        [o.name], fix="Apply scale (transform_apply) or mirror the mesh data instead.")
            if np.linalg.norm(np.array(mw.translation)) * self.U > 10_000:
                rep.add("transform.far", "WARN", "transform",
                        f"'{o.name}' is {fmt_m(np.linalg.norm(np.array(mw.translation)) * self.U)} from origin "
                        "(float precision jitter).", [o.name])
            hidden_vp = o.hide_get() or o.hide_viewport
            if hidden_vp and renders:
                rep.add("objects.hidden_but_renders", "WARN", "objects",
                        f"'{o.name}' is hidden in the viewport but WILL render (hide_render is False).",
                        [o.name], fix="Set obj.hide_render = True too, or delete the helper.")
            if o.name in bool_cutters and renders:
                rep.add("objects.boolean_cutter_renders", "WARN", "objects",
                        f"Boolean cutter '{o.name}' still renders (display_type only affects the viewport).",
                        [o.name], fix="cutter.hide_render = True (and hide_viewport if wanted).")
            elif renders and o.display_type in {"WIRE", "BOUNDS"}:
                rep.add("objects.wire_display_renders", "INFO", "objects",
                        f"'{o.name}' displays as {o.display_type} in the viewport but renders solid.", [o.name])
            if o.type == "MESH" and o.data and len(o.data.vertices) == 0 and not o.modifiers:
                rep.add("objects.empty_mesh", "WARN", "objects", f"'{o.name}' has an empty mesh.", [o.name])
            for md in getattr(o, "modifiers", []):
                if md.show_viewport and not md.show_render:
                    rep.add("modifier.render_disabled", "WARN", "modifier",
                            f"Modifier '{md.name}' on '{o.name}' is on in viewport but OFF in render.", [o.name])
                if md.type == "SUBSURF" and md.render_levels >= 4:
                    rep.add("modifier.subsurf_heavy", "INFO", "modifier",
                            f"Subdivision render_levels={md.render_levels} on '{o.name}'.", [o.name])
                if md.type == "ARMATURE":
                    self._check_armature_mod(o, md)
            if o.parent and o.parent.type == "ARMATURE" and o.parent_type == "ARMATURE" and \
                    not any(md.type == "ARMATURE" for md in o.modifiers):
                rep.add("rig.armature_parent_no_modifier", "INFO", "rig",
                        f"'{o.name}' has ARMATURE parent type but no Armature modifier.", [o.name])
            e = self.by_name.get(o.name)
            if o.type == "MESH" and renders and e is not None:
                key = (len(o.data.vertices), len(o.data.polygons),
                       tuple(np.round(np.concatenate([e.bmin, e.bmax]) / (self.scene_size * 1e-5), 0)))
                sig.setdefault(key, []).append(o.name)
        for names in sig.values():
            if len(names) > 1:
                rep.add("objects.stacked_duplicates", "WARN", "objects",
                        f"{len(names)} identical objects share the exact same transform (double "
                        f"geometry, z-fighting, inflated counts): {', '.join(names[:6])}", names,
                        fix="Delete the extras; usually a duplicate op or a re-run that did not clear the scene.")
        self._check_defaults()

    def _check_armature_mod(self, o, md):
        arm = md.object
        if arm is None:
            self.rep.add("rig.armature_missing", "WARN", "rig",
                         f"Armature modifier '{md.name}' on '{o.name}' has no armature object.", [o.name])
            return
        bones = {b.name for b in arm.data.bones if b.use_deform}
        groups = {g.name for g in o.vertex_groups}
        if md.use_vertex_groups and not (bones & groups) and not md.use_bone_envelopes:
            self.rep.add("rig.accidental_skin", "WARN", "rig",
                         f"'{o.name}' is deformed by armature '{arm.name}' but has no vertex group "
                         "matching a deform bone - often an accidental parent_set(ARMATURE_*) on "
                         "everything that was still selected.", [o.name, arm.name],
                         fix="Deselect all before parent_set; remove the Armature modifier from props.")

    def _check_defaults(self):
        sc = self.scene
        cube = bpy.data.objects.get("Cube")
        if cube and cube.name in sc.objects and cube.type == "MESH" and len(sc.objects) > 3:
            d = cube.dimensions
            if len(cube.data.vertices) == 8 and all(abs(x - 2.0) < 1e-4 for x in d) and \
                    cube.location.length < 1e-6:
                self.rep.add("objects.default_cube", "WARN", "objects",
                             "The startup 'Cube' (2 m, at origin) is still in the scene.", ["Cube"],
                             fix="Start scripts with read_factory_settings(use_empty=True) or delete it.")

    # ------------------------------------------------------------------ checks: geometry
    def check_geometry(self):
        rep, tgt = self.rep, self.intent.target
        strict = tgt in {"print", "realtime", "export"}
        for name, st in self.mesh_info.items():
            if "skipped" in st:
                continue
            if st.get("nan"):
                rep.add("geometry.nan", "FAIL", "geometry", f"'{name}' has NaN/inf vertex coordinates.", [name])
            e = self.by_name.get(name)
            if e is not None and e.closed and e.local_volume < 0 and abs(e.local_volume) > 1e-12:
                rep.add("geometry.inverted_normals", "FAIL" if strict else "WARN", "geometry",
                        f"'{name}' is a closed mesh whose normals point inward (negative volume).", [name],
                        fix="bmesh.ops.recalc_face_normals(bm, faces=bm.faces) or flip normals.")
            if st["inconsistent_edges"]:
                rep.add("geometry.inconsistent_normals", "WARN", "geometry",
                        f"'{name}': {st['inconsistent_edges']} edges join faces with opposite winding "
                        "(patchy shading, wrong backface culling).", [name],
                        fix="Recalculate normals outside.")
            nm = st["boundary_edges"] + st["nonmanifold_edges"]
            if nm and (strict or st["nonmanifold_edges"]):
                rep.add("geometry.non_manifold", "FAIL" if tgt == "print" else ("WARN" if strict else "INFO"),
                        "geometry", f"'{name}': {st['boundary_edges']} open edges, "
                        f"{st['nonmanifold_edges']} edges with >2 faces.", [name])
            if st["loose_verts"] or st["wire_edges"]:
                rep.add("geometry.loose", "WARN" if strict else "INFO", "geometry",
                        f"'{name}': {st['loose_verts']} loose verts, {st['wire_edges']} wire edges.", [name])
            if st["degenerate_faces"]:
                rep.add("geometry.degenerate", "WARN" if strict else "INFO", "geometry",
                        f"'{name}': {st['degenerate_faces']} zero-area faces.", [name])
            if st["duplicate_verts"]:
                rep.add("geometry.duplicate_verts", "WARN" if strict else "INFO", "geometry",
                        f"'{name}': {st['duplicate_verts']} duplicate vertices (merge by distance).", [name])
            if strict and st["ngons"]:
                rep.add("geometry.ngons", "INFO", "geometry", f"'{name}': {st['ngons']} n-gons.", [name])
            if strict and st["uv_layers"] == 0:
                rep.add("geometry.no_uv", "WARN", "geometry", f"'{name}' has no UV map.", [name])
            if st["verts"] > 1_000_000:
                rep.add("geometry.heavy", "INFO", "geometry", f"'{name}' has {st['verts']:,} vertices.", [name])
        total = sum(st.get("tris", 0) for st in self.mesh_info.values())
        if total > 20_000_000:
            rep.add("geometry.scene_heavy", "WARN", "geometry", f"Scene has {total:,} triangles.")

    # ------------------------------------------------------------------ checks: materials
    def check_materials(self):
        rep, sc = self.rep, self.scene
        used_by = {}
        for o in sc.objects:
            if o.type not in GEOM_TYPES or not self.renders(o):
                continue
            slots = getattr(o, "material_slots", [])
            if o.type == "MESH" and (not slots or all(s.material is None for s in slots)):
                rep.add("material.none", "INFO", "material",
                        f"'{o.name}' has no material (renders default grey).", [o.name])
            elif any(s.material is None for s in slots):
                rep.add("material.empty_slot", "WARN", "material",
                        f"'{o.name}' has empty material slot(s); faces using them render default.", [o.name])
            for s in slots:
                if s.material:
                    used_by.setdefault(s.material.name, []).append(o.name)
        for mat in bpy.data.materials:
            if mat.users == 0 and not mat.use_fake_user:
                rep.add("material.unused", "INFO", "material",
                        f"Material '{mat.name}' was created but is assigned to nothing (purged on save).",
                        [mat.name], fix="Append it to obj.data.materials if it was meant to be used.")
        mats = [bpy.data.materials[n] for n in used_by if n in bpy.data.materials]
        for mat in mats:
            nt = getattr(mat, "node_tree", None)
            if nt is None:
                continue
            objs = used_by.get(mat.name, [])
            outs = [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"]
            active = [n for n in outs if getattr(n, "is_active_output", True)] or outs
            if not outs:
                rep.add("material.no_output", "FAIL", "material",
                        f"Material '{mat.name}' has no Material Output node (renders black/invisible).",
                        [mat.name] + objs[:3])
            elif not any(n.inputs["Surface"].is_linked or n.inputs["Volume"].is_linked for n in active):
                rep.add("material.output_unlinked", "FAIL", "material",
                        f"Material '{mat.name}': nothing is connected to the Material Output Surface.",
                        [mat.name] + objs[:3])
            for link in nt.links:
                if not link.is_valid:
                    rep.add("material.invalid_link", "WARN", "material",
                            f"Material '{mat.name}' has an invalid (red) link "
                            f"{link.from_node.name} -> {link.to_node.name}.", [mat.name])
            self._check_texture_nodes(mat, nt, objs)
            for n in nt.nodes:
                if n.type == "BSDF_PRINCIPLED":
                    es = n.inputs.get("Emission Strength")
                    if es is not None and not es.is_linked and es.default_value > 50:
                        rep.add("material.emission_high", "INFO", "material",
                                f"'{mat.name}' Emission Strength {es.default_value:g}.", [mat.name])

    def _check_texture_nodes(self, mat, nt, objs):
        rep = self.rep
        data_inputs = {"Normal", "Roughness", "Metallic", "Specular IOR Level", "Height",
                       "Displacement", "Strength", "Distance", "Coat Normal", "Alpha",
                       "Transmission Weight", "Coat Weight", "Anisotropic"}
        for n in nt.nodes:
            if n.type != "TEX_IMAGE" or n.image is None:
                continue
            img = n.image
            for link in n.outputs["Color"].links:
                to = link.to_socket.name
                tnode = link.to_node.type
                cs = img.colorspace_settings.name
                if (to in data_inputs or tnode in {"NORMAL_MAP", "BUMP", "DISPLACEMENT"}) and cs == "sRGB":
                    rep.add("material.colorspace_data", "WARN", "material",
                            f"Image '{img.name}' feeds '{to}' ({link.to_node.name}) in '{mat.name}' but is "
                            "tagged sRGB - data maps must be Non-Color.", [mat.name],
                            fix=f"bpy.data.images['{img.name}'].colorspace_settings.name = 'Non-Color'")
                if to == "Base Color" and cs in {"Non-Color", "Raw"}:
                    rep.add("material.colorspace_color", "WARN", "material",
                            f"Image '{img.name}' feeds Base Color in '{mat.name}' but is Non-Color "
                            "(looks washed out).", [mat.name])
            vec = n.inputs.get("Vector")
            needs_uv = vec is None or not vec.is_linked or \
                (vec.links and vec.links[0].from_node.type in {"UVMAP", "TEX_COORD"} and
                 vec.links[0].from_socket.name == "UV")
            if needs_uv:
                for oname in objs:
                    ob = bpy.data.objects.get(oname)
                    if ob and ob.type == "MESH" and len(ob.data.uv_layers) == 0:
                        rep.add("material.texture_no_uv", "WARN", "material",
                                f"'{oname}' uses image '{img.name}' through UVs but has no UV map "
                                "(texture collapses to one colour).", [oname],
                                fix="Unwrap (smart_project) or use Generated/Object coordinates.")

    def check_images(self):
        rep = self.rep
        for img in bpy.data.images:
            if img.source not in {"FILE", "SEQUENCE", "MOVIE", "TILED"} or img.packed_file:
                continue
            path = bpy.path.abspath(img.filepath, library=img.library)
            if img.source == "TILED":
                continue
            if not path or not os.path.exists(path):
                sev = "FAIL" if img.users > 0 else "INFO"
                rep.add("image.missing", sev, "image",
                        f"Image '{img.name}' points to a missing file '{img.filepath}' "
                        "(renders magenta/pink).", [img.name],
                        fix="Fix the path, pack it (bpy.ops.file.pack_all) or remove the node.")
            elif bpy.data.filepath and os.path.isabs(img.filepath) and not img.filepath.startswith("//"):
                rep.add("image.absolute_path", "INFO", "image",
                        f"Image '{img.name}' uses an absolute path (breaks when the project moves).",
                        [img.name], fix="bpy.ops.file.make_paths_relative()")

    # ------------------------------------------------------------------ checks: lights & world
    def check_lighting(self):
        rep, sc = self.rep, self.scene
        lights = [o for o in sc.objects if o.type == "LIGHT" and self.renders(o)]
        world_lum = 0.0
        w = sc.world
        if w is not None:
            nt = getattr(w, "node_tree", None)
            bgs = [n for n in nt.nodes if n.type == "BACKGROUND"] if nt else []
            if bgs:
                for bg in bgs:
                    col = bg.inputs["Color"]
                    s = bg.inputs["Strength"]
                    c = 1.0 if col.is_linked else lum(col.default_value)
                    world_lum = max(world_lum, c * (1.0 if s.is_linked else s.default_value))
            else:
                world_lum = lum(w.color)
        emissive = []
        for mat in bpy.data.materials:
            nt = getattr(mat, "node_tree", None)
            if not nt or mat.users == 0:
                continue
            for n in nt.nodes:
                if n.type == "BSDF_PRINCIPLED":
                    s, c = n.inputs.get("Emission Strength"), n.inputs.get("Emission Color")
                    if s is not None and c is not None and (s.is_linked or s.default_value > 0) and \
                            (c.is_linked or lum(c.default_value) > 0):
                        emissive.append(mat.name)
                elif n.type == "EMISSION":
                    if n.inputs["Strength"].is_linked or n.inputs["Strength"].default_value > 0:
                        emissive.append(mat.name)
        live = [o for o in lights if o.data.energy > 0]
        for o in lights:
            if o.data.energy <= 0:
                rep.add("light.zero", "WARN", "light", f"Light '{o.name}' has energy {o.data.energy}.", [o.name])
            if o.data.type == "SUN" and (o.data.energy > 50 or o.data.energy < 0.05):
                rep.add("light.sun_strength", "INFO", "light",
                        f"Sun '{o.name}' strength {o.data.energy:g} W/m^2 (typical daylight 1-10 with AgX).",
                        [o.name])
            if o.data.type in {"POINT", "SPOT", "AREA"} and o.data.energy > 1e5:
                rep.add("light.extreme", "WARN", "light",
                        f"Light '{o.name}' energy {o.data.energy:g} W is extreme.", [o.name])
            loc = o.matrix_world.translation
            for e in self.entries:
                if e.closed and not e.container and not e.volume and np.all(np.array(loc) >= e.bmin) and \
                        np.all(np.array(loc) <= e.bmax) and self._parity_inside(e, loc.copy()):
                    if e.transmissive or e.card:
                        break  # glass / emissive shade: light gets out
                    rep.add("light.inside_mesh", "WARN", "light",
                            f"Light '{o.name}' sits inside closed mesh '{e.name}' - its light is blocked "
                            "unless that material transmits.", [o.name, e.name])
                    break
        self.light_summary = {"lights": len(lights), "lit": len(live), "world_luminance": round(world_lum, 4),
                              "emissive_materials": sorted(set(emissive))[:20]}
        if self.intent.target == "render" and not live and world_lum < 0.005 and not emissive:
            rep.add("light.none", "FAIL", "light",
                    "No light source: no lights with energy, world is black and no emissive materials - "
                    "the render will be black.", fix="Add a light or set a world colour/HDRI.")

    # ------------------------------------------------------------------ checks: camera
    def check_camera(self):
        rep, sc = self.rep, self.scene
        cam = sc.camera
        if cam is None:
            sev = "FAIL" if self.intent.target == "render" else "INFO"
            rep.add("camera.none", sev, "camera", "scene.camera is None - nothing to render from.",
                    fix="scene.camera = cam_obj")
            return
        dg = self.dg
        r = sc.render
        rx, ry = r.resolution_x, r.resolution_y
        P = mat_np(cam.calc_matrix_camera(dg, x=rx, y=ry, scale_x=r.pixel_aspect_x, scale_y=r.pixel_aspect_y))
        Vw = mat_np(cam.matrix_world.inverted())
        PV = P @ Vw
        cam_loc = cam.matrix_world.translation.copy()
        fwd = (cam.matrix_world.to_quaternion() @ Vector((0, 0, -1))).normalized()
        cd = cam.data

        def project(pts):
            h = np.c_[pts, np.ones(len(pts))] @ PV.T
            w = h[:, 3]
            with np.errstate(divide="ignore", invalid="ignore"):
                ndc = h[:, :2] / w[:, None]
            front = w > 1e-9
            inside = front & (np.abs(ndc) <= 1.0).all(axis=1)
            depth = (pts - np.array(cam_loc)) @ np.array(fwd)
            return ndc, front, inside, depth

        # camera inside geometry
        for e in self.entries:
            if e.closed and not e.container and not e.volume and np.all(np.array(cam_loc) >= e.bmin) and \
                    np.all(np.array(cam_loc) <= e.bmax) and self._parity_inside(e, cam_loc.copy()):
                rep.add("camera.inside_mesh", "FAIL", "camera",
                        f"Camera '{cam.name}' is inside closed mesh '{e.name}' - the view is blocked.",
                        [cam.name, e.name])
        # roll
        right = cam.matrix_world.to_quaternion() @ Vector((1, 0, 0))
        roll = math.degrees(math.asin(max(-1, min(1, right.z))))
        if abs(roll) > 2.0 and abs(fwd.z) < 0.95:
            rep.add("camera.roll", "INFO", "camera", f"Camera horizon is tilted {roll:+.1f} deg.", [cam.name])
        # subjects
        explicit = bool(self.intent.subjects)
        groups = []
        for gi, members in enumerate(self.groups):
            names = [self.entries[i].name for i in members]
            if explicit:
                if not any(fnmatch.fnmatchcase(n, p) for n in names for p in self.intent.subjects):
                    continue
            else:
                if all(self.entries[i].ground or self.entries[i].container or self.entries[i].arch or
                       self.entries[i].volume or self.entries[i].card for i in members):
                    continue
            groups.append((gi, members))
        if explicit:
            found = {p for p in self.intent.subjects
                     if any(fnmatch.fnmatchcase(e.name, p) for e in self.entries)}
            for p in self.intent.subjects:
                if p not in found:
                    rep.add("camera.subject_missing", "FAIL", "camera",
                            f"Subject pattern '{p}' matches no renderable object.", [p])
        visible_any = False
        far_depth = 0.0
        self.screen = {}
        for gi, members in groups:
            pts = np.concatenate([self.entries[i].W for i in members])
            if len(pts) > 600:
                pts = pts[np.linspace(0, len(pts) - 1, 600).astype(np.int64)]
            ndc, front, inside, depth = project(pts)
            frac = float(inside.mean())
            far_depth = max(far_depth, float(depth.max()))
            if front.any():
                lo = np.clip(ndc[front].min(0), -1, 1)
                hi = np.clip(ndc[front].max(0), -1, 1)
                coverage = float(np.prod(np.maximum(hi - lo, 0)) / 4.0)
                c = ndc[front].mean(0)
            else:
                coverage, c = 0.0, np.array([np.nan, np.nan])
            label = self.group_label(members)
            self.screen[gi] = {"in_frame": round(frac, 3), "coverage": round(coverage, 4),
                               "screen_xy": [round(float((c[0] + 1) / 2), 3), round(float((c[1] + 1) / 2), 3)]
                               if front.any() else None,
                               "depth_m": round(self.m(float(np.median(depth))), 3)}
            if frac > 0:
                visible_any = True
            sev_missing = "FAIL" if explicit else "INFO"
            if frac == 0.0:
                rep.add("camera.subject_out_of_frame", sev_missing, "camera",
                        f"'{label}' is completely outside the camera view"
                        f"{' (behind camera)' if not front.any() else ''}.",
                        [self.entries[i].name for i in members][:5], waive="camera")
            elif frac < 0.85 and (explicit or coverage > 0.02):
                rep.add("camera.subject_cropped", "WARN" if explicit else "INFO", "camera",
                        f"'{label}' is cropped: only {frac:.0%} of its points are in frame.",
                        [self.entries[i].name for i in members][:5], waive="camera")
            elif explicit and coverage < 0.01:
                rep.add("camera.subject_tiny", "WARN", "camera",
                        f"Subject '{label}' fills only {coverage:.2%} of the frame.",
                        [self.entries[i].name for i in members][:5], waive="camera")
            if frac > 0 and (explicit or coverage > 0.01):
                self._occlusion(cam_loc, members, label, explicit, pts[inside][:12], cd.clip_start)
        if groups and not visible_any:
            rep.add("camera.sees_nothing", "FAIL", "camera",
                    f"Camera '{cam.name}' sees none of the scene's objects (all outside frame or behind).",
                    [cam.name], fix="Aim with a Track To constraint or compute the look-at rotation; "
                    "verify by rendering.")
        if far_depth > cd.clip_end:
            rep.add("camera.clip_end", "WARN", "camera",
                    f"Geometry reaches {fmt_m(self.m(far_depth))} from the camera but clip_end is "
                    f"{fmt_m(self.m(cd.clip_end))} - distant parts are cut off.", [cam.name])
        hit = sc.ray_cast(dg, cam_loc, fwd)
        if hit[0] and (hit[1] - cam_loc).length < cd.clip_start:
            rep.add("camera.clip_start", "INFO", "camera",
                    f"'{hit[4].name}' is {fmt_m(self.m((hit[1] - cam_loc).length))} in front of the lens, "
                    f"inside clip_start {cd.clip_start:g} - it is cut out of the render (fine when shooting "
                    "through a doorway; a bug if the camera is buried in an object).", [cam.name, hit[4].name])
        if cd.dof.use_dof:
            fd = cd.dof.focus_distance
            if cd.dof.focus_object is not None:
                fd = (cd.dof.focus_object.matrix_world.translation - cam_loc).dot(fwd)
            near = [v["depth_m"] for v in self.screen.values() if v["in_frame"] > 0.3]
            if near and not any(abs(self.m(fd) - d) <= 0.35 * d for d in near):
                rep.add("camera.dof_focus", "WARN", "camera",
                        f"DOF focus at {fmt_m(self.m(fd))} but visible subjects are at "
                        f"{', '.join(fmt_m(d) for d in sorted(near)[:4])} - subjects will be blurred.", [cam.name])
        if cd.type == "PERSP" and (cd.lens < 10 or cd.lens > 400):
            rep.add("camera.lens", "INFO", "camera", f"Focal length {cd.lens:g} mm.", [cam.name])

    def _occlusion(self, cam_loc, members, label, explicit, pts, clip_start):
        """Ray-cast camera -> subject against render-visible solids (own BVHs: scene.ray_cast
        skips viewport-hidden objects and hits render-hidden ones)."""
        ents = self.entries
        names = {ents[i].name for i in members}
        pool = [e for e in ents if e.name in names or not (e.volume or e.transmissive)]
        bmin = np.array([e.bmin for e in pool])
        bmax = np.array([e.bmax for e in pool])
        cam = np.array(cam_loc)
        reach, blockers = 0, {}
        for p in pts:
            d = np.asarray(p) - cam
            dist = float(np.linalg.norm(d))
            if dist <= clip_start + 1e-9:
                continue
            dv = d / dist
            safe = np.where(np.abs(dv) < 1e-12, 1e-12, dv)
            t1, t2 = (bmin - cam) / safe, (bmax - cam) / safe
            tmin = np.minimum(t1, t2).max(axis=1)
            tmax = np.maximum(t1, t2).min(axis=1)
            cand = np.nonzero((tmax >= np.maximum(tmin, clip_start)) & (tmin <= dist))[0]
            start = V(cam + dv * clip_start)  # geometry before clip_start is not rendered
            hit_d, hit = math.inf, None
            for k in cand:
                loc, _n, _i, h = pool[k].bvh.ray_cast(start, V(dv), dist - clip_start)
                if loc is not None and h < hit_d:
                    hit_d, hit = h, pool[k].name
            if hit is None or hit in names or hit_d >= dist - clip_start - 1e-3 * dist:
                reach += 1
            else:
                blockers[hit] = blockers.get(hit, 0) + 1
        if len(pts) and reach == 0 and blockers:
            top = max(blockers, key=blockers.get)
            self.rep.add("camera.subject_occluded", "FAIL" if explicit else "WARN", "camera",
                         f"'{label}' is in frame but hidden behind '{top}' (no sample ray reaches it).",
                         sorted(names)[:5] + [top], waive="camera")

    # ------------------------------------------------------------------ checks: static physics
    def check_static_physics(self):
        rep, ents = self.rep, self.entries
        if not ents:
            return
        # 1. pairwise penetration / z-fighting / enclosure
        joins = {}
        for (i, j), rel in self.relations.items():
            a, b = ents[i], ents[j]
            same = a.group == b.group
            if rel["kind"] == "intersect":
                depth_m = self.m(rel["depth"])
                if same or (a.arch and b.arch):
                    key = a.group if same else "arch"
                    agg = joins.setdefault(key, {"n": 0, "max": 0.0, "pair": (a.name, b.name)})
                    agg["n"] += 1
                    if depth_m > agg["max"]:
                        agg["max"], agg["pair"] = depth_m, (a.name, b.name)
                    continue
                sev, why = self._intersection_severity(a, b, depth_m, self.m(rel.get("axis_extent", 0.0)))
                rep.add("physics.intersection", sev, "physics",
                        f"'{a.name}' and '{b.name}' interpenetrate by ~{fmt_m(depth_m)}"
                        f"{f' ({why})' if why else ''}.",
                        [a.name, b.name], evidence={"depth_m": round(depth_m, 4),
                                                    "tri_pairs": rel["tri_pairs"]},
                        fix="Move one so they only touch (snap bottom to the support's top), or "
                            "waive in intent.allow.intersect if intended.",
                        physics=True, waive="intersect")
            elif rel["kind"] == "enclosed":
                rep.add("physics.enclosed", "WARN", "physics",
                        f"'{rel['inner']}' is completely inside '{rel['outer']}' (hidden / misplaced).",
                        [rel["inner"], rel["outer"]], physics=True, waive="intersect")
            if rel.get("coplanar_same_facing", 0) >= 2 and not same and \
                    rel.get("coplanar_area", 0) * self.U ** 2 >= 1e-4:
                rep.add("render.z_fighting", "WARN", "render",
                        f"'{a.name}' and '{b.name}' share coplanar, same-facing faces "
                        f"(~{rel['coplanar_area'] * self.U ** 2 * 1e4:.0f} cm^2) - z-fighting flicker.",
                        [a.name, b.name], fix="Offset one surface ~1 mm along its normal or give it thickness.")
        for key, agg in joins.items():
            if key == "arch":
                label, hier = "architecture", True
            else:
                label, hier = self.group_label(self.groups[key]), key in self.hier_groups
            sev = "INFO" if (hier or agg["max"] <= 0.02) else "WARN"
            rep.add("physics.internal_intersection", sev, "physics",
                    f"{agg['n']} part pair(s) of '{label}' overlap (max {fmt_m(agg['max'])}: "
                    f"{agg['pair'][0]} x {agg['pair'][1]}) - treated as modelled joins"
                    + ("" if hier else "; grouped by name only, check they are really one object") + ".",
                    list(agg["pair"]), physics=True, waive="intersect")
        # 2. ground sinking
        grounds = [e for e in ents if e.ground]
        for e in ents:
            if e.ground or e.container or e.volume or e.card:
                continue
            for g in grounds:
                over = (e.bmin[:2] < g.bmax[:2]).all() and (e.bmax[:2] > g.bmin[:2]).all()
                if over and e.bmax[2] < g.bmax[2] - self.ptol(e, g):
                    rep.add("physics.below_ground", "FAIL", "physics",
                            f"'{e.name}' is entirely below the ground '{g.name}' "
                            f"(top {fmt_m(self.m(e.bmax[2]))} < ground {fmt_m(self.m(g.bmax[2]))}).",
                            [e.name, g.name], physics=True, waive="floating")
                    break
        # 3. support graph
        self._support_graph()
        # 4. scale realism
        self._scale_check()

    def _intersection_severity(self, a: Entry, b: Entry, depth_m: float, extent_m: float):
        # FAIL when > 2 cm, or when it swallows half of the thinner object along the push-out axis
        deep = depth_m > 0.02 or (extent_m >= 0.01 and depth_m > 0.5 * extent_m)
        if (a.arch and not a.ground) or (b.arch and not b.ground):
            return ("FAIL" if depth_m > 0.05 else "WARN"), "embedded in wall/architecture"
        if a.soft or b.soft:
            return ("FAIL" if depth_m > 0.06 else "WARN"), "soft-contact allowance"
        return ("FAIL" if deep else "WARN"), (None if deep else "shallow")

    def _support_graph(self):
        rep, ents = self.rep, self.entries
        n = len(ents)
        adj = [[] for _ in range(n)]
        for (i, j), rel in self.relations.items():
            if rel["kind"] in ("contact", "intersect", "enclosed"):
                adj[i].append(j)
                adj[j].append(i)
        solid = [i for i, e in enumerate(ents) if not (e.volume or e.card)]
        base = {i for i in solid if ents[i].ground or ents[i].container}
        if not base and solid:
            base = {min(solid, key=lambda i: ents[i].bmin[2])}
        seen = set()
        comps = []
        for s in solid:
            if s in seen:
                continue
            stack, comp = [s], []
            seen.add(s)
            while stack:
                x = stack.pop()
                comp.append(x)
                for y in adj[x]:
                    if y not in seen:
                        seen.add(y)
                        stack.append(y)
            comps.append(comp)
        self.supported = set()
        for comp in comps:
            if base & set(comp):
                self.supported.update(comp)
                continue
            names = [ents[i].name for i in comp]
            label = self.group_label(comp) if len(comp) > 1 else names[0]
            if any(self.is_dynamic(ents[i]) for i in comp):
                if any(ents[i].name in self.animated for i in comp):
                    rep.add("physics.airborne_animated", "INFO", "physics",
                            f"'{label}' is animated and airborne at frame {self.scene.frame_current}; "
                            "contact over time is checked in the animation pass.", names, physics=True)
                continue
            gap, below = self._gap_below(comp)
            wall_gap, wall = self._near_wall(comp)
            near_gap, near = self._near_any(comp, 0.02)
            airborne = any(has_word(nm, AIRBORNE_WORDS) for nm in names)
            height = max(float(ents[i].bmax[2]) for i in comp) - min(float(ents[i].bmin[2]) for i in comp)
            gap_m = self.m(gap) if below else None
            if wall is not None:
                rep.add("physics.wall_gap", "WARN", "physics",
                        f"'{label}' touches nothing; it hangs {fmt_m(self.m(wall_gap))} off '{wall}' with no "
                        "visible fixing (wall-mounted?).", names,
                        evidence={"wall_gap_m": round(self.m(wall_gap), 4)},
                        fix="Move it flush to the wall (or add a hook/bracket) - or waive if it is a "
                            "deliberate shadow gap.", physics=True, waive="floating")
                continue
            small = gap_m is not None and gap_m <= 0.01 and gap <= 0.5 * max(height, 1e-9)
            sev = "WARN" if (airborne or small or near is not None) else "FAIL"
            where = (f"{fmt_m(gap_m)} above '{below}'" if below else "with nothing beneath it")
            nearly = f"; nearest surface '{near}' is {fmt_m(self.m(near_gap))} away" if near else ""
            rep.add("physics.floating", sev, "physics",
                    f"'{label}' touches nothing and floats {where}{nearly}"
                    f"{' (name suggests an airborne object)' if airborne else ''}.",
                    names, evidence={"gap_m": round(gap_m, 4) if gap_m is not None else None, "below": below},
                    fix="Snap down: obj.location.z -= (obj_bottom - support_top) using world bboxes, "
                        "then re-run QC.", physics=True, waive="floating")
        # small objects held only from the side / above
        for i in self.supported:
            e = ents[i]
            if e.ground or e.container or e.arch or self.m(e.dims.max()) > 0.6 or self.is_dynamic(e):
                continue
            if has_word(e.name, MOUNT_WORDS) or has_word(e.name, AIRBORNE_WORDS):
                continue
            partners = [j for j in adj[i] if not (ents[j].volume or ents[j].card)]
            if not partners or any(ents[j].group == e.group for j in partners):
                continue  # attached parts of one asset hold each other
            below = [j for j in partners if ents[j].bmax[2] <= e.bmin[2] + 0.3 * e.dims[2] + self.ctol(e, ents[j])]
            if not below:
                rep.add("physics.side_supported", "WARN", "physics",
                        f"'{e.name}' has no support underneath - it only touches "
                        f"{', '.join(repr(ents[j].name) for j in partners[:3])} from the side/above "
                        "(would fall unless glued, hung or mounted).", [e.name],
                        physics=True, waive="floating")
            else:
                self._stability(e, [ents[j] for j in below])

    def _near_any(self, comp, reach_m: float):
        """Closest solid outside comp within reach (near-miss contacts)."""
        ents = self.entries
        cs = set(comp)
        reach = self.bu(reach_m)
        best, who = math.inf, None
        for i in comp:
            e = ents[i]
            for j, f in enumerate(ents):
                if j in cs or f.volume or f.card:
                    continue
                if (e.bmin > f.bmax + reach).any() or (f.bmin > e.bmax + reach).any():
                    continue
                lo, hi = np.maximum(e.bmin, f.bmin) - reach, np.minimum(e.bmax, f.bmax) + reach
                for p in self._surface_points(e, lo, hi, max(reach, float((hi - lo).max()) / 10), cap=200):
                    loc, _n, _k, dist = f.bvh.find_nearest(V(p), reach)
                    if loc is not None and dist < best:
                        best, who = dist, f.name
        return best, who

    def _near_wall(self, comp, reach_m: float = 0.05):
        """Nearest vertical architecture surface within reach (for wall-mounted items)."""
        ents = self.entries
        cs = set(comp)
        reach = self.bu(reach_m)
        best, who = math.inf, None
        for i in comp:
            e = ents[i]
            for j, w in enumerate(ents):
                if j in cs or not (w.arch or w.container) or w.ground or w.volume or w.card:
                    continue
                if (e.bmin > w.bmax + reach).any() or (w.bmin > e.bmax + reach).any():
                    continue
                for p in self._surface_points(e, e.bmin, e.bmax, float(e.dims.max()) / 6, cap=120):
                    loc, nrm, _k, dist = w.bvh.find_nearest(V(p), reach)
                    if loc is not None and abs(nrm.z) < 0.5 and dist < best:
                        best, who = dist, w.name
        return best, who

    def _gap_below(self, comp):
        ents = self.entries
        cs = set(comp)
        best, who = math.inf, None
        down = Vector((0, 0, -1))
        for i in comp:
            e = ents[i]
            idx = np.argsort(e.W[:, 2])[:24]
            for p in e.W[idx]:
                pv = V(p)
                for j, f in enumerate(ents):
                    if j in cs or f.volume or f.card or f.bmax[2] > pv.z + 1e-9 + 0.5 * e.dims[2]:
                        continue
                    if not (f.bmin[0] <= p[0] <= f.bmax[0] and f.bmin[1] <= p[1] <= f.bmax[1]):
                        continue
                    loc, _n, _k, dist = f.bvh.ray_cast(pv, down)
                    if loc is not None and dist < best:
                        best, who = dist, f.name
        return (best if who else 0.0), who

    def _stability(self, e: Entry, supports):
        if self.over_budget():
            return
        tol = max(self.ctol(e, s) for s in supports) * 2
        bottom = e.W[e.W[:, 2] <= e.bmin[2] + max(tol, 0.02 * e.dims[2])]
        if len(bottom) > 300:
            bottom = bottom[np.linspace(0, len(bottom) - 1, 300).astype(np.int64)]
        contacts = []
        for p in bottom:
            pv = V(p)
            for s in supports:
                loc, _n, _i, dist = s.bvh.find_nearest(pv, tol * 2)
                if loc is not None:
                    contacts.append((p[0], p[1]))
                    break
        if len(contacts) < 3:
            return
        pts = [(float(x), float(y)) for x, y in contacts]
        hull_idx = mgeo.convex_hull_2d(pts)
        hull = [pts[k] for k in hull_idx]
        if len(hull) < 3:
            return
        com = e.com()
        if not _point_in_convex(hull, (com[0], com[1])):
            dist = _dist_to_polygon(hull, (com[0], com[1]))
            if dist > 0.03 * max(e.dims[0], e.dims[1]):
                self.rep.add("physics.unstable", "WARN", "physics",
                             f"'{e.name}': centre of mass lies {fmt_m(self.m(dist))} outside its support "
                             "footprint - it would tip over.", [e.name],
                             evidence={"com": [round(float(c), 3) for c in com]},
                             physics=True, waive="stability")

    def _scale_check(self):
        rep, ents = self.rep, self.entries
        ratios = []
        for members in self.groups:
            names = [ents[i].name for i in members]
            if any(ents[i].card or ents[i].volume or ents[i].ground or ents[i].container for i in members):
                continue
            toks = self.group_tokens(members) if len(members) > 1 else core_tokens(names[0])
            head = head_noun(toks)
            if head is None:
                continue  # a part ('desk_top', 'lamp_shade') - judged with its asset, not alone
            words = {head, head[:-1] if len(head) > 3 and head.endswith("s") else head}
            bmin = np.min([ents[i].bmin for i in members], axis=0)
            bmax = np.max([ents[i].bmax for i in members], axis=0)
            dims = (bmax - bmin) * self.U
            for kw, metric, lo, hi in SIZE_TABLE:
                if not (kw & words):
                    continue
                val = {"height": dims[2], "max": dims.max(), "length": max(dims[0], dims[1])}[metric]
                if val <= 0:
                    break
                if val < lo or val > hi:
                    ratio = val / (lo if val < lo else hi)
                    ratios.append(ratio)
                    big = ratio > 3 or ratio < 1 / 3
                    rep.add("physics.scale", "FAIL" if big else "WARN", "physics",
                            f"'{self.group_label(members)}' {metric} is {fmt_m(val)}; a real "
                            f"{sorted(kw & words)[0]} is {fmt_m(lo)}-{fmt_m(hi)}.", names[:5],
                            evidence={"dims_m": [round(float(d), 3) for d in dims]},
                            fix="Scale to real-world size (or set intent.allow.scale if stylised).",
                            physics=True, waive="scale")
                break
        big = [r for r in ratios if r > 20]
        small = [r for r in ratios if r < 1 / 20]
        if len(big) >= 2 or len(small) >= 2:
            rep.add("physics.unit_mismatch", "FAIL", "physics",
                    f"Several objects are off by ~{np.median(big or small):.3g}x - likely a unit "
                    "error (cm vs m import, or scale_length).", physics=True)

    # ------------------------------------------------------------------ checks: animation
    def check_animation(self):
        sc, rep = self.scene, self.rep
        f0, f1 = sc.frame_start, sc.frame_end
        # action / slot sanity
        key_lo, key_hi = math.inf, -math.inf
        for idb in list(bpy.data.objects) + list(bpy.data.materials) + list(bpy.data.cameras) + \
                list(bpy.data.lights):
            ad = getattr(idb, "animation_data", None)
            if not ad or not ad.action:
                continue
            if hasattr(ad, "action_slot") and ad.action_slot is None and len(getattr(ad.action, "slots", [])):
                rep.add("anim.no_slot", "FAIL", "animation",
                        f"'{idb.name}' has action '{ad.action.name}' but no action slot assigned - "
                        "the animation does nothing (Blender 4.4+ slotted actions).", [idb.name],
                        fix="obj.animation_data.action_slot = action.slots[0] (or use keyframe_insert).")
            lo, hi = ad.action.frame_range
            key_lo, key_hi = min(key_lo, lo), max(key_hi, hi)
            for fc in fcurves_of(idb):
                if fc.data_path != "rotation_euler" or len(fc.keyframe_points) < 2:
                    continue
                kp = sorted((k.co[0], k.co[1]) for k in fc.keyframe_points)
                for (fa, va), (fb, vb) in zip(kp, kp[1:]):
                    if abs(vb - va) > math.pi * 0.95 and fb - fa <= 3:
                        rep.add("anim.euler_flip", "WARN", "animation",
                                f"'{idb.name}' rotation_euler[{fc.array_index}] jumps "
                                f"{math.degrees(vb - va):+.0f} deg between keys at frames {fa:g}-{fb:g} "
                                "(gimbal/euler flip: spins visibly, worse with motion blur).", [idb.name],
                                fix="Euler.make_compatible() on the keys, or the Graph Editor Euler filter.")
                        break
        if key_hi > -math.inf:
            if key_hi > f1 + 0.5:
                rep.add("anim.keys_after_end", "WARN", "animation",
                        f"Keyframes run to frame {key_hi:g} but frame_end is {f1} - the end is cut off.")
            if key_lo < f0 - 0.5:
                rep.add("anim.keys_before_start", "INFO", "animation",
                        f"Keyframes start at {key_lo:g} before frame_start {f0}.")
            if key_hi < f0 + 0.5 * (f1 - f0) and f1 - f0 > 48:
                rep.add("anim.range_long", "INFO", "animation",
                        f"Animation ends at frame {key_hi:g}; frames up to {f1} are static.")
        if f1 <= f0 or not self.entries:
            return
        n = min(self.args.anim_samples, f1 - f0 + 1)
        frames = sorted(set(np.linspace(f0, f1, n).round().astype(int).tolist()))
        if len(frames) < 3:
            return
        cur = sc.frame_current
        ents = self.entries
        real = [i for i, e in enumerate(ents) if e.ob is not None and e.name in self.animated
                and e.name not in self.dynamic]
        traj = {i: [] for i in real}
        feet = self._foot_bones()
        foot_traj = {k: [] for k in feet}
        try:
            for f in frames:
                sc.frame_set(f)
                for i in real:
                    traj[i].append(np.array(ents[i].ob.matrix_world))
                for (arm, bone) in feet:
                    pb = arm.pose.bones[bone]
                    foot_traj[(arm, bone)].append(np.array(arm.matrix_world @ pb.head))
        finally:
            sc.frame_set(cur)
        fps = sc.render.fps / sc.render.fps_base
        step = np.diff(frames)
        dt = step / fps
        g = 9.81 / self.U
        for i, Ms in traj.items():
            Ms = np.array(Ms)
            if np.abs(Ms - Ms[0]).max() < 1e-7:
                continue
            self.moving.add(i)
            e = ents[i]
            c_local = e.local.mean(axis=0)
            pos = np.einsum("fij,j->fi", Ms[:, :3, :3], c_local) + Ms[:, :3, 3]
            vel = np.linalg.norm(np.diff(pos, axis=0), axis=1) / dt
            if len(vel) >= 4:
                med = float(np.median(vel[vel > 1e-9])) if (vel > 1e-9).any() else 0.0
                spikes = [frames[k + 1] for k, v in enumerate(vel)
                          if v * self.U > 5.0 and v > 8 * max(med, 1e-9)]
                if spikes:
                    rep.add("anim.pop", "WARN", "animation",
                            f"'{e.name}' jumps abruptly near frame(s) {spikes[:6]} "
                            f"(peak {max(vel) * self.U:.1f} m/s vs median {med * self.U:.2f} m/s).",
                            [e.name], physics=True, waive="animation")
            rots = [Matrix(m[:3, :3].tolist()).to_quaternion() for m in Ms]
            ang = []
            for k in range(len(rots) - 1):
                a = math.degrees(rots[k].rotation_difference(rots[k + 1]).angle)
                ang.append(min(a, 360.0 - a))  # q and -q are the same rotation
            if ang:
                medang = float(np.median(ang))
                flips = [frames[k + 1] for k, a in enumerate(ang) if a > 60 and a > 5 * max(medang, 1e-6)]
                if flips:
                    rep.add("anim.rotation_flip", "WARN", "animation",
                            f"'{e.name}' rotation snaps >60 deg in one step near frame(s) {flips[:6]} "
                            "(euler flip / wrong interpolation?).", [e.name], waive="animation")
            self._fall_check(e, pos, frames, fps, g)
        if self.moving and not self.over_budget():
            self._moving_contacts(traj, frames)
        for (arm, bone), pts in foot_traj.items():
            self._foot_slide(arm, bone, np.array(pts), frames, fps)

    def _fall_check(self, e, pos, frames, fps, g):
        z = pos[:, 2]
        t = (np.array(frames) - frames[0]) / fps
        k = 0
        while k < len(z) - 3:
            if z[k + 1] >= z[k] - 1e-6:
                k += 1
                continue
            s = k
            while k < len(z) - 1 and z[k + 1] < z[k] - 1e-6:
                k += 1
            drop = (z[s] - z[k]) * self.U
            if drop < max(0.3, 0.5 * float(e.dims[2]) * self.U) or k - s < 4:
                continue
            zz, tt = z[s:k + 1], t[s:k + 1]
            vz = np.diff(zz) / np.diff(tt)
            seg_t = tt[-1] - tt[0]
            expected = math.sqrt(2 * drop / 9.81)
            last = vz[-max(2, len(vz) // 4):]
            first = vz[: max(2, len(vz) // 4)]
            if abs(last.mean()) < 0.7 * abs(vz).max():
                self.rep.add("anim.fall_eases_out", "WARN", "animation",
                             f"'{e.name}' slows down before landing at frame {frames[k]} (drop {fmt_m(drop)}): "
                             "a falling object hits at its fastest - default Bezier easing looks floaty.",
                             [e.name], evidence={"drop_m": round(drop, 3), "duration_s": round(seg_t, 3),
                                                 "free_fall_s": round(expected, 3)},
                             fix="Make the last key's handle linear/vector (or use ease-in only, or a rigid body).",
                             physics=True, waive="animation")
            elif abs(last.mean()) < 1.3 * abs(first.mean()) and seg_t > 0.25:
                self.rep.add("anim.fall_constant_speed", "INFO", "animation",
                             f"'{e.name}' falls {fmt_m(drop)} at roughly constant speed (no gravity "
                             f"acceleration); free fall would take {expected:.2f}s, it takes {seg_t:.2f}s.",
                             [e.name], physics=True, waive="animation")
            elif seg_t > 2.5 * expected or seg_t < 0.4 * expected:
                self.rep.add("anim.fall_timing", "INFO", "animation",
                             f"'{e.name}' falls {fmt_m(drop)} in {seg_t:.2f}s; free fall would take "
                             f"{expected:.2f}s.", [e.name], physics=True, waive="animation")

    def _moving_contacts(self, traj, frames):
        ents = self.entries
        sample = sorted(set(frames[:: max(1, len(frames) // 24)] + [frames[-1]]))
        idx = [frames.index(f) for f in sample]
        statics = [j for j in range(len(ents)) if j not in self.moving and not (ents[j].volume or ents[j].card)]
        hits = {}
        for i in self.moving:
            e = ents[i]
            if e.ob is not None and any(md.type == "ARMATURE" for md in e.ob.modifiers):
                continue  # deforming meshes handled by _deform_ground
            touched = False
            for k in idx:
                # world matrix sampled for this frame; local geometry is unchanged for rigid motion
                em = e.moved(np.array(traj[i][k]))
                for j in statics:
                    s = ents[j]
                    pad = self.ctol(em, s)
                    if (em.bmin > s.bmax + pad).any() or (s.bmin > em.bmax + pad).any():
                        continue
                    rel = self.relate(em, s)
                    if rel["kind"] in ("contact", "intersect"):
                        touched = True
                    if rel["kind"] == "intersect" and em.group != s.group:
                        hits.setdefault((e.name, s.name), []).append((frames[k], rel["depth"]))
            inside_other = any(
                f is not e and f.closed and not f.container and (e.bmin >= f.bmin).all() and (e.bmax <= f.bmax).all()
                for f in ents)
            if not touched and not inside_other and not has_word(e.name, AIRBORNE_WORDS) and not e.ground:
                self.rep.add("anim.never_touches", "WARN", "animation",
                             f"Animated '{e.name}' never touches anything in {len(idx)} sampled frames "
                             "(floating the whole shot?).", [e.name], physics=True, waive="floating")
            if self.over_budget():
                break
        static_hits = {frozenset((ents[i].name, ents[j].name)) for (i, j), r in self.relations.items()
                       if r["kind"] == "intersect"}
        for (a, b), lst in hits.items():
            if frozenset((a, b)) in static_hits and len(lst) >= len(idx) - 1:
                continue  # already reported as a static intersection; it never separates
            d = max(x[1] for x in lst)
            self.rep.add("anim.passes_through", "FAIL", "animation",
                         f"Animated '{a}' passes through '{b}' at frame(s) {[x[0] for x in lst][:6]} "
                         f"(up to {fmt_m(self.m(d))}).", [a, b], physics=True, waive="intersect")
        self._deform_ground(sample)

    def _deform_ground(self, sample):
        grounds = [e for e in self.entries if e.ground]
        if not grounds:
            return
        gtop = max(float(g.bmax[2]) for g in grounds)
        sc = self.scene
        cur = sc.frame_current
        chars = [e for e in self.entries if e.ob is not None and
                 any(md.type == "ARMATURE" and md.object is not None and md.object.animation_data
                     for md in e.ob.modifiers)][:6]
        try:
            for e in chars:
                lows = []
                for f in sample[:24]:
                    sc.frame_set(f)
                    dg = bpy.context.evaluated_depsgraph_get()
                    oe = e.ob.evaluated_get(dg)
                    co, _t, _s = mesh_arrays(oe)
                    W = co @ mat_np(oe.matrix_world)[:3, :3].T + mat_np(oe.matrix_world)[:3, 3]
                    lows.append((f, float(W[:, 2].min())))
                tol = self.bu(self.intent.penetration_m)
                sunk = [(f, z) for f, z in lows if z < gtop - max(tol, self.bu(0.01))]
                if sunk:
                    self.rep.add("anim.sinks_into_ground", "FAIL", "animation",
                                 f"'{e.name}' dips below the ground at frame(s) {[f for f, _ in sunk][:6]} "
                                 f"(lowest {fmt_m(self.m(min(z for _, z in sunk) - gtop))}).", [e.name],
                                 physics=True, waive="floating")
                if lows and all(z > gtop + self.bu(0.03) for _, z in lows):
                    self.rep.add("anim.hovers", "WARN", "animation",
                                 f"'{e.name}' never gets within 3 cm of the ground in sampled frames "
                                 f"(min gap {fmt_m(self.m(min(z for _, z in lows) - gtop))}).", [e.name],
                                 physics=True, waive="floating")
        finally:
            sc.frame_set(cur)

    def _foot_bones(self):
        out = []
        for o in self.scene.objects:
            if o.type != "ARMATURE" or not o.animation_data:
                continue
            for pb in o.pose.bones:
                t = tokens(pb.name)
                if any(w in t for w in ("foot", "toe", "ball", "heel")) or \
                        any(w in pb.name.lower() for w in ("foot", "toe")):
                    out.append((o, pb.name))
        return out[:8]

    def _foot_slide(self, arm, bone, pts, frames, fps):
        if len(pts) < 4:
            return
        z = pts[:, 2]
        floor = z.min()
        planted = z <= floor + self.bu(0.02)
        slide = 0.0
        for k in range(len(pts) - 1):
            if planted[k] and planted[k + 1] and frames[k + 1] - frames[k] <= 2:
                slide += float(np.linalg.norm(pts[k + 1, :2] - pts[k, :2]))
        if self.m(slide) > 0.05:
            self.rep.add("anim.foot_slide", "WARN", "animation",
                         f"'{arm.name}:{bone}' slides {fmt_m(self.m(slide))} while planted (foot skating).",
                         [arm.name], physics=True, waive="animation",
                         fix="Lock planted feet (IK/foot-lock) or match root speed to stride.")

    # ------------------------------------------------------------------ checks: simulation
    def check_simulation(self):
        sc, rep = self.scene, self.rep
        rbw = sc.rigidbody_world
        rb_objs = []
        if rbw and rbw.collection:
            rb_objs = [o for o in rbw.collection.objects if o.rigid_body]
        cloth = [o for o in sc.objects for md in o.modifiers if md.type in {"CLOTH", "SOFT_BODY"}]
        colliders = [o for o in sc.objects for md in o.modifiers if md.type == "COLLISION"]
        fluids = [o for o in sc.objects for md in o.modifiers if md.type == "FLUID"]
        gn_sim = [o.name for o in sc.objects for md in o.modifiers if md.type == "NODES" and md.node_group
                  and any(n.bl_idname == "GeometryNodeSimulationInput" for n in md.node_group.nodes)]
        if gn_sim:
            rep.add("sim.geometry_nodes", "INFO", "simulation",
                    f"Geometry Nodes simulation zones on {gn_sim[:5]} - bake them before rendering on a "
                    "farm/headless (frame jumps do not simulate).", gn_sim)
        for o in fluids:
            md = next(m for m in o.modifiers if m.type == "FLUID")
            if md.fluid_type == "DOMAIN":
                cd = bpy.path.abspath(md.domain_settings.cache_directory)
                if not os.path.isdir(cd) or not any(os.scandir(cd)):
                    rep.add("sim.fluid_unbaked", "WARN", "simulation",
                            f"Fluid domain '{o.name}' has no baked cache at '{cd}' - headless renders "
                            "show an empty domain.", [o.name], fix="Bake (bpy.ops.fluid.bake_all) first.")
        if rb_objs:
            g_m = [g * self.U for g in sc.gravity]  # scene.gravity is in scene units/s^2, not rescaled
            if abs(g_m[2] + 9.81) > 0.1 or abs(g_m[0]) + abs(g_m[1]) > 1e-3 or not sc.use_gravity:
                rep.add("sim.gravity", "WARN", "simulation",
                        f"Gravity is {tuple(round(g, 3) for g in g_m)} m/s^2 (use_gravity={sc.use_gravity}, "
                        f"scale_length={self.U}); Earth is (0, 0, -9.81). Blender does not rescale gravity "
                        "with unit scale - a cm-scale scene falls 100x too slowly.",
                        fix=f"scene.gravity = (0, 0, {-9.81 / self.U:g})", physics=True)
            if abs(rbw.time_scale - 1.0) > 1e-3:
                rep.add("sim.time_scale", "INFO", "simulation",
                        f"Rigid body time_scale {rbw.time_scale:g}: motion is {rbw.time_scale:g}x speed "
                        "(apparent g scales with time_scale^2) - fine only if slow/fast motion is intended.")
            if not rbw.enabled:
                rep.add("sim.rb_disabled", "WARN", "simulation", "Rigid body world is disabled.")
            pc = rbw.point_cache
            if pc.frame_end < sc.frame_end:
                rep.add("sim.cache_short", "WARN", "simulation",
                        f"Rigid body cache ends at {pc.frame_end} but the scene runs to {sc.frame_end} - "
                        "objects freeze after that.", fix="rigidbody_world.point_cache.frame_end = scene.frame_end")
            masses = []
            for o in rb_objs:
                rb = o.rigid_body
                s = o.scale
                if rb.type == "ACTIVE":
                    masses.append(rb.mass)
                    if max(abs(s.x), abs(s.y), abs(s.z)) - min(abs(s.x), abs(s.y), abs(s.z)) > 1e-4 or \
                            abs(abs(s.x) - 1) > 1e-4:
                        rep.add("sim.unapplied_scale", "INFO", "simulation",
                                f"Rigid body '{o.name}' has unapplied scale {tuple(round(c, 3) for c in s)} "
                                "(Bullet handles it, but margins/exports are easier with applied scale).",
                                [o.name], fix="transform_apply(location=False, rotation=False, scale=True)")
                    if rb.collision_shape == "MESH":
                        rep.add("sim.mesh_shape_active", "WARN", "simulation",
                                f"Active rigid body '{o.name}' uses MESH collision shape (slow, unstable, and it "
                                f"rests ~collision_margin = {rb.collision_margin:g} above surfaces). Use "
                                "CONVEX_HULL or a primitive.", [o.name])
                    if any(fc.data_path == "scale" for fc in fcurves_of(o)):
                        rep.add("sim.animated_scale", "WARN", "simulation",
                                f"Active rigid body '{o.name}' has animated scale - Bullet ignores it for "
                                "contacts, so it sinks into or floats over surfaces.", [o.name], physics=True)
                    e = self.by_name.get(o.name)
                    if e is not None:
                        com = e.com()
                        off = float(np.linalg.norm(com - np.array(o.matrix_world.translation)))
                        if off > 0.25 * float(e.dims.max()):
                            rep.add("sim.origin_off_center", "WARN", "simulation",
                                    f"Rigid body '{o.name}' origin is {fmt_m(self.m(off))} from its geometry "
                                    "centre - Bullet uses the origin as centre of mass, so it tumbles wrongly.",
                                    [o.name], fix="origin_set(type='ORIGIN_CENTER_OF_VOLUME') before simulating.",
                                    physics=True)
                    if e is not None and e.closed:
                        vol = abs(_signed_volume(e.W, e.tris)) * self.U ** 3
                        if vol > 1e-9:
                            dens = rb.mass / vol
                            if dens < 5 or dens > 25000:
                                rep.add("sim.density", "WARN", "simulation",
                                        f"'{o.name}' mass {rb.mass:g} kg over {vol:.4g} m^3 = {dens:.3g} kg/m^3 "
                                        "(water 1000, wood ~600, steel 7850).", [o.name], physics=True)
                        size = self.m(min(d for d in e.dims if d > 0))
                        if size < 0.02:
                            rep.add("sim.tiny", "WARN", "simulation",
                                    f"Rigid body '{o.name}' is {fmt_m(size)} thick - Bullet is unstable below "
                                    "~2 cm; raise substeps or scale the scene.", [o.name])
                        if rb.use_margin and rb.collision_margin > 0.1 * size / self.U:
                            rep.add("sim.margin", "WARN", "simulation",
                                    f"'{o.name}' collision margin {rb.collision_margin:g} is large for its size "
                                    "(visible gap at rest).", [o.name])
            if len(masses) >= 3 and all(abs(m - 1.0) < 1e-6 for m in masses):
                rep.add("sim.default_mass", "INFO", "simulation",
                        f"All {len(masses)} active rigid bodies have the default 1 kg mass.", physics=True)
            ids = {o.name for o in rb_objs}
            for (i, j), rel in self.relations.items():
                a, b = self.entries[i].name, self.entries[j].name
                if a in ids and b in ids and rel["kind"] in ("intersect", "enclosed"):
                    rep.add("sim.initial_overlap", "WARN", "simulation",
                            f"Rigid bodies '{a}' and '{b}' start interpenetrating - expect an explosive "
                            "separation on frame 1.", [a, b], physics=True)
        if cloth and not colliders:
            rep.add("sim.cloth_no_collider", "WARN", "simulation",
                    f"Cloth/soft body on {[o.name for o in cloth][:4]} but no object has a Collision "
                    "modifier - it will fall through everything.", [o.name for o in cloth][:4],
                    fix="Add a COLLISION modifier to floors/tables/bodies it should drape on.")
        mode = self.args.simulate
        if mode == "off" or (not rb_objs and not cloth):
            if mode == "on":
                self.rep.skipped.append("simulate: nothing to simulate")
            return
        self._run_sim(rb_objs, cloth)

    def _run_sim(self, rb_objs, cloth):
        sc, rep = self.scene, self.rep
        f0 = sc.frame_start
        f1 = min(sc.frame_end, f0 + self.args.sim_frames - 1)
        cur = sc.frame_current
        fps = sc.render.fps / sc.render.fps_base
        track = {o.name: [] for o in rb_objs}
        cloth_last = {}
        t0 = time.time()
        rbw = sc.rigidbody_world
        if rbw and rbw.point_cache.is_baked:
            rep.add("sim.baked", "INFO", "simulation",
                    "Rigid body cache is baked - QC read the bake (what renders). Bakes are NOT invalidated by "
                    "later edits: re-bake after moving/changing bodies.")
        try:
            sc.frame_set(f0)  # back at frame_start the unbaked cache restarts
            for f in range(f0, f1 + 1):
                sc.frame_set(f)  # sequential stepping: sims only advance one frame at a time
                for o in rb_objs:
                    track[o.name].append(np.array(o.matrix_world.translation))
                if time.time() - t0 > self.args.time_budget / 2:
                    rep.add("sim.partial", "WARN", "simulation",
                            f"Simulation stepping stopped at frame {f} (time budget).")
                    f1 = f
                    break
            dg = bpy.context.evaluated_depsgraph_get()
            final = {}
            for o in rb_objs:
                final[o.name] = mat_np(o.matrix_world)
            for o in cloth:
                oe = o.evaluated_get(dg)
                co, tri, _ = mesh_arrays(oe)
                cloth_last[o.name + "@end"] = Entry(o.name + "@end", o, co, tri, mat_np(oe.matrix_world))
        finally:
            sc.frame_set(cur)
        g_top = max([float(e.bmax[2]) for e in self.entries if e.ground] or [-math.inf])
        s_min = self.scene_min
        s_size = self.scene_size
        sim_findings = 0
        for name, pts in track.items():
            pts = np.array(pts)
            if len(pts) < 2:
                continue
            v = np.linalg.norm(np.diff(pts, axis=0), axis=1) * fps * self.U
            # gravity alone can give at most sqrt(2 g drop) - more means energy came from the solver
            drop = np.maximum(self.m(1) * (pts[0][2] - pts[1:, 2]), 0.0)
            allowed = 1.3 * np.sqrt(2 * 9.81 * drop) + 3.0
            bad = np.nonzero(v > allowed)[0]
            if len(bad):
                k = int(bad[np.argmax(v[bad] - allowed[bad])])
                rep.add("sim.explosion", "FAIL", "simulation",
                        f"Rigid body '{name}' reaches {v[k]:.1f} m/s at frame {k + f0 + 1}, more than gravity "
                        f"can give for its {drop[k]:.2f} m drop ({allowed[k] - 3:.1f} m/s) - solver "
                        "explosion (initial overlap, tiny/huge scale, MESH shape).", [name], physics=True)
                sim_findings += 1
            e = self.by_name.get(name)
            if g_top > -math.inf and pts[-1][2] < g_top - (float(e.dims[2]) if e is not None else 0) * 0.5:
                rep.add("sim.fell_through", "FAIL", "simulation",
                        f"Rigid body '{name}' ends below the ground (z {fmt_m(self.m(pts[-1][2]))}) - "
                        "tunnelling, missing passive collider, or collider not in the RB world.",
                        [name], physics=True)
                sim_findings += 1
            if np.linalg.norm(pts[-1] - pts[0]) > 3 * s_size:
                rep.add("sim.left_scene", "WARN", "simulation",
                        f"Rigid body '{name}' travels far outside the scene.", [name], physics=True)
            if len(v) > 10 and v[-10:].mean() > 0.05 and f1 >= sc.frame_end:
                rep.add("sim.not_settled", "INFO", "simulation",
                        f"'{name}' is still moving ({v[-10:].mean():.2f} m/s) at the last frame.", [name])
        # final-state penetration between sim objects and the rest
        moved = {}
        for name, M in final.items():
            e = self.by_name.get(name)
            if e is not None:
                moved[name] = e.moved(M)
        moved.update(cloth_last)
        for name, em in moved.items():
            for f in self.entries:
                if f.name == name.replace("@end", "") or f.name in moved or f.name + "@end" in moved:
                    continue
                if (em.bmin > f.bmax + 1e-9).any() or (f.bmin > em.bmax + 1e-9).any():
                    continue
                rel = self.relate(em, f)
                if rel["kind"] == "intersect" and rel["depth"] > self.ptol(em, f) * 2:
                    rep.add("sim.end_penetration", "FAIL", "simulation",
                            f"After simulating to frame {f1}, '{name.replace('@end', '')}' is "
                            f"{fmt_m(self.m(rel['depth']))} inside '{f.name}'.", [name.replace("@end", ""), f.name],
                            physics=True, waive="intersect")
            if name.endswith("@end"):
                o = bpy.data.objects.get(name[:-4])
                e0 = self.by_name.get(name[:-4])
                if e0 is not None and float(em.dims.max()) > 3 * float(e0.dims.max()):
                    rep.add("sim.cloth_exploded", "FAIL", "simulation",
                            f"Cloth '{o.name}' grew {em.dims.max() / e0.dims.max():.1f}x - the sim blew up.",
                            [o.name], physics=True)
                if o is not None and e0 is not None and any(md.type == "SOFT_BODY" for md in o.modifiers) and \
                        float(em.dims[2]) < 0.5 * float(e0.dims[2]):
                    rep.add("sim.softbody_collapsed", "WARN", "simulation",
                            f"Soft body '{o.name}' collapses to {em.dims[2] / max(e0.dims[2], 1e-9):.0%} of its "
                            "height (default soft body has no goal/stiffness - it pancakes).", [o.name],
                            fix="Enable goal / use_stiff_quads, raise bending/pull/push stiffness.", physics=True)
                if g_top > -math.inf and float(em.bmin[2]) < g_top - self.bu(0.02):
                    rep.add("sim.cloth_through_floor", "FAIL", "simulation",
                            f"Cloth/soft body '{o.name}' ends {fmt_m(self.m(g_top - em.bmin[2]))} below the ground.",
                            [o.name], physics=True)
        self.sim_summary = {"frames": [f0, f1], "rigid_bodies": len(rb_objs), "cloth": len(cloth)}

    # ------------------------------------------------------------------ inventory
    def build_inventory(self):
        sc = self.scene
        group_of = {e.name: e.group for e in self.entries}
        for o in sc.objects:
            if self.intent.ignored(o.name):
                continue
            row = {"name": o.name, "type": o.type, "renders": self.renders(o) if o.type in GEOM_TYPES or
                   o.type == "LIGHT" else None,
                   "collections": [c.name for c in o.users_collection][:3],
                   "parent": o.parent.name if o.parent else None,
                   "location_m": [round(float(v) * self.U, 3) for v in o.matrix_world.translation]}
            e = self.by_name.get(o.name)
            if e is not None:
                row["bbox_min_m"] = [round(float(v) * self.U, 3) for v in e.bmin]
                row["bbox_max_m"] = [round(float(v) * self.U, 3) for v in e.bmax]
                row["dims_m"] = [round(float(v) * self.U, 3) for v in e.dims]
                row["flags"] = [f for f, on in (("ground", e.ground), ("container", e.container),
                                                ("moving", self.entries.index(e) in self.moving)) if on]
                gi = group_of.get(o.name)
                row["group"] = gi
                if hasattr(self, "screen") and gi in self.screen:
                    row["camera_view"] = self.screen[gi]
            if o.type in GEOM_TYPES:
                mats = []
                for s in getattr(o, "material_slots", []):
                    if s.material:
                        mats.append({"name": s.material.name, "base_color": _base_color(s.material)})
                row["materials"] = mats
                st = self.mesh_info.get(o.name)
                if st and "verts" in st:
                    row["verts"] = st["verts"]
            if o.type == "LIGHT":
                row["light"] = {"type": o.data.type, "energy": round(o.data.energy, 3),
                                "color": [round(c, 3) for c in o.data.color]}
            if o.type == "CAMERA":
                row["camera"] = {"lens_mm": round(o.data.lens, 2), "type": o.data.type,
                                 "active": o == sc.camera}
            self.inventory.append(row)

    # ------------------------------------------------------------------ run
    def run(self) -> dict:
        rep = self.rep
        rep.run("build_entries", self.build_entries)
        rep.run("classify", self.classify)
        rep.run("detect_dynamic", self.detect_dynamic)
        rep.run("file_scene", self.check_file)
        rep.run("objects", self.check_objects)
        rep.run("geometry", self.check_geometry)
        rep.run("materials", self.check_materials)
        rep.run("images", self.check_images)
        rep.run("relations", self.build_relations)
        rep.run("groups", self.build_groups)
        rep.run("lighting", self.check_lighting)
        rep.run("camera", self.check_camera)
        if self.intent.physics != "off":
            rep.run("static_physics", self.check_static_physics)
        else:
            rep.skipped.append("static_physics (intent.physics=off)")
        rep.run("simulation", self.check_simulation)  # before animation: frame jumps poison sim caches
        rep.run("animation", self.check_animation)
        rep.run("inventory", self.build_inventory)
        rep.findings.sort(key=lambda f: (SEV_ORDER[f["severity"]], f["category"], f["id"]))
        summary = {s: sum(1 for f in rep.findings if f["severity"] == s) for s in SEV_ORDER}
        sc = self.scene
        r = sc.render
        meta = {
            "qc_version": QC_VERSION,
            "blender": bpy.app.version_string,
            "file": bpy.data.filepath or None,
            "scene": sc.name,
            "engine": r.engine,
            "resolution": [r.resolution_x, r.resolution_y, r.resolution_percentage],
            "fps": round(r.fps / r.fps_base, 3),
            "frame_range": [sc.frame_start, sc.frame_end],
            "unit_scale": sc.unit_settings.scale_length,
            "view_transform": sc.view_settings.view_transform,
            "camera": sc.camera.name if sc.camera else None,
            "entries_checked": len(self.entries),
            "groups": len(self.groups),
            "intent": {"physics": self.intent.physics, "target": self.intent.target,
                       "ground": self.intent.ground, "subjects": self.intent.subjects,
                       "notes": self.intent.notes},
            "lighting": getattr(self, "light_summary", {}),
            "simulation": getattr(self, "sim_summary", None),
            "runtime_s": round(time.time() - self.t0, 2),
        }
        groups = [{"id": gi, "label": self.group_label(m), "members": [self.entries[i].name for i in m][:12]}
                  for gi, m in enumerate(self.groups) if len(m) > 1]
        return {"meta": meta, "verdict": "FAIL" if summary["FAIL"] else ("WARN" if summary["WARN"] else "PASS"),
                "summary": summary, "findings": rep.findings, "checks": rep.checks,
                "skipped": rep.skipped, "multi_part_groups": groups, "inventory": self.inventory}


def _point_in_convex(hull, p) -> bool:
    sign = 0
    n = len(hull)
    for k in range(n):
        x1, y1 = hull[k]
        x2, y2 = hull[(k + 1) % n]
        cross = (x2 - x1) * (p[1] - y1) - (y2 - y1) * (p[0] - x1)
        if abs(cross) < 1e-15:
            continue
        s = 1 if cross > 0 else -1
        if sign == 0:
            sign = s
        elif s != sign:
            return False
    return True


def _dist_to_polygon(hull, p) -> float:
    best = math.inf
    for k in range(len(hull)):
        a = np.array(hull[k])
        b = np.array(hull[(k + 1) % len(hull)])
        ab = b - a
        t = np.clip(np.dot(np.array(p) - a, ab) / max(np.dot(ab, ab), 1e-18), 0, 1)
        best = min(best, float(np.linalg.norm(np.array(p) - (a + t * ab))))
    return best


def _base_color(mat):
    nt = getattr(mat, "node_tree", None)
    if nt:
        for n in nt.nodes:
            if n.type == "BSDF_PRINCIPLED":
                s = n.inputs["Base Color"]
                if s.is_linked:
                    return "texture:" + s.links[0].from_node.type.lower()
                c = s.default_value
                return "#%02x%02x%02x" % tuple(int(max(0, min(1, _lin2srgb(c[k]))) * 255 + 0.5) for k in range(3))
    c = mat.diffuse_color
    return "#%02x%02x%02x" % tuple(int(max(0, min(1, _lin2srgb(c[k]))) * 255 + 0.5) for k in range(3))


def _lin2srgb(x):
    return 12.92 * x if x <= 0.0031308 else 1.055 * (x ** (1 / 2.4)) - 0.055


# --------------------------------------------------------------------------- markdown

def to_markdown(res: dict) -> str:
    m = res["meta"]
    L = [f"# Blender QC - {res['verdict']}", "",
         f"- File: `{m['file']}`  scene `{m['scene']}`  Blender {m['blender']}",
         f"- Engine {m['engine']}, {m['resolution'][0]}x{m['resolution'][1]} @{m['resolution'][2]}%, "
         f"{m['fps']} fps, frames {m['frame_range'][0]}-{m['frame_range'][1]}, view {m['view_transform']}",
         f"- Camera `{m['camera']}`; {m['entries_checked']} renderable meshes in {m['groups']} groups; "
         f"lighting {m['lighting']}",
         f"- Intent: physics **{m['intent']['physics']}**, target {m['intent']['target']}"
         + (f" - {m['intent']['notes']}" if m['intent'].get('notes') else ""),
         f"- Findings: {res['summary']['FAIL']} FAIL, {res['summary']['WARN']} WARN, "
         f"{res['summary']['INFO']} INFO (runtime {m['runtime_s']} s)", ""]
    for sev in ("FAIL", "WARN"):
        rows = [f for f in res["findings"] if f["severity"] == sev]
        if not rows:
            continue
        L += [f"## {sev}", ""]
        for f in rows:
            L.append(f"- **{f['id']}** - {f['message']}" + (f"  \n  fix: {f['fix']}" if f.get("fix") else ""))
        L.append("")
    info = [f for f in res["findings"] if f["severity"] == "INFO"]
    if info:
        L += ["## INFO", ""]
        for f in info[:60]:
            L.append(f"- {f['id']} - {f['message']}" + (f" (waived: {f['waived']})" if f.get("waived") else ""))
        if len(info) > 60:
            L.append(f"- ... {len(info) - 60} more in JSON")
        L.append("")
    errs = [c for c in res["checks"] if c["status"] != "ok"]
    if errs or res["skipped"]:
        L += ["## Not verified", ""] + [f"- check `{c['check']}` crashed" for c in errs] + \
             [f"- skipped: {s}" for s in res["skipped"]] + [""]
    return "\n".join(L)


# --------------------------------------------------------------------------- entry

def parse(argv):
    ap = argparse.ArgumentParser(prog="blender_qc.py")
    ap.add_argument("--out", default="")
    ap.add_argument("--md", default="")
    ap.add_argument("--intent", default="")
    ap.add_argument("--physics", default=None, choices=["realistic", "stylized", "off"])
    ap.add_argument("--simulate", default="auto", choices=["auto", "on", "off"])
    ap.add_argument("--sim-frames", type=int, default=250)
    ap.add_argument("--anim-samples", type=int, default=120)
    ap.add_argument("--time-budget", type=float, default=300.0)
    ap.add_argument("--fail-exit", action="store_true")
    return ap.parse_args(argv)


def main(argv=None) -> dict:
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = parse(argv)
    intent_data = {}
    if args.intent:
        with open(args.intent, encoding="utf-8") as fh:
            intent_data = json.load(fh)
    intent = Intent(intent_data, args.physics)
    sel = [o.name for o in bpy.context.selected_objects] if hasattr(bpy.context, "selected_objects") else []
    res = Audit(args, intent).run()
    out = args.out
    if not out:
        base = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd()
        out = os.path.join(base, "qc_out", "qc.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=str)
    md = args.md or os.path.splitext(out)[0] + ".md"
    with open(md, "w", encoding="utf-8") as fh:
        fh.write(to_markdown(res))
    for o in bpy.context.scene.objects:  # restore selection (live sessions)
        try:
            o.select_set(o.name in sel)
        except Exception:
            pass
    print(f"[blender_qc] verdict={res['verdict']} FAIL={res['summary']['FAIL']} "
          f"WARN={res['summary']['WARN']} INFO={res['summary']['INFO']} -> {out}")
    if args.fail_exit and res["summary"]["FAIL"] and bpy.app.background:
        sys.exit(2)
    return res


if __name__ == "__main__":
    _argv = globals().get("QC_ARGV")
    main(list(_argv) if _argv is not None else None)
