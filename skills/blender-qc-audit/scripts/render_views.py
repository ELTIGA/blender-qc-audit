"""render_views.py - visual evidence for a Blender scene QC (Blender 4.2 - 5.x).

Renders, inside Blender, then restores every setting it touched (never saves):
  * camera view in the scene's own engine at low res/samples, at one or more frames
    -> PNG (display look) + stats; plus a transparent EXR pass for coverage / NaN / fireflies
  * Workbench orthographic views (front, right, top, iso) fitted to the content with walls and
    ceilings hidden ("dollhouse"), random object colours so separate objects are distinguishable
  * optional --focus PATTERN: close-up ortho views around matching objects (inspect a contact)
  * contact_sheet.png tiling the geometry views

    blender -b scene.blend --factory-startup --python-exit-code 1 \
        --python render_views.py -- --out-dir qc_out [--frames 1,mid,end] [--focus "Mug*"]

Writes <out-dir>/render_report.json. Look at the PNGs yourself - numbers do not judge composition.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Vector

GEOM = {"MESH", "CURVE", "SURFACE", "META", "FONT"}
HIDE_WORDS = {"wall", "walls", "ceiling", "roof", "room", "skydome", "dome", "cyclorama", "haze", "fog",
              "volume", "baseboard", "skirting", "cornice"}
KEEP_WORDS = {"floor", "ground", "terrain", "rug", "carpet", "landscape"}  # supports stay visible


def _tokens(name):
    import re
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return {t.lower() for t in re.split(r"[^A-Za-z0-9]+", name) if t}


class Restore:
    """Snapshot attributes and put them back (safe in live sessions)."""

    def __init__(self):
        self.items = []

    def set(self, obj, attr, value):
        try:
            self.items.append((obj, attr, getattr(obj, attr)))
            setattr(obj, attr, value)
        except (AttributeError, TypeError, ValueError):
            pass

    def undo(self):
        for obj, attr, val in reversed(self.items):
            try:
                setattr(obj, attr, val)
            except Exception:
                pass
        self.items.clear()


def load_px(path):
    im = bpy.data.images.load(path, check_existing=False)
    try:
        a = np.empty(len(im.pixels), np.float32)
        im.pixels.foreach_get(a)
        w, h = im.size
        return a.reshape(h, w, 4)
    finally:
        bpy.data.images.remove(im)


def renders(ob, vl):
    if ob.hide_render:
        return False
    cols = {}

    def walk(lc, ok):
        ok = ok and not lc.exclude and not lc.collection.hide_render
        cols[lc.collection.name] = cols.get(lc.collection.name, False) or ok
        for c in lc.children:
            walk(c, ok)
    walk(vl.layer_collection, True)
    return any(cols.get(c.name, False) for c in ob.users_collection)


def world_bbox(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    if not pts:
        return Vector((-1, -1, -1)), Vector((1, 1, 1))
    a = np.array(pts)
    return Vector(a.min(0)), Vector(a.max(0))


def set_still_png(rs, R, path, rgba=False):
    if hasattr(rs.image_settings, "media_type"):  # 5.0+: must precede file_format
        R.set(rs.image_settings, "media_type", "IMAGE")
    R.set(rs.image_settings, "file_format", "PNG")
    R.set(rs.image_settings, "color_mode", "RGBA" if rgba else "RGB")
    R.set(rs.image_settings, "color_depth", "8")
    rs.filepath = path


def do_render(path):
    bpy.ops.render.render(write_still=True)
    if not os.path.exists(path):
        raise RuntimeError(f"render produced no file at {path}")
    return path


def _magenta_frac(rgb):
    """Share of magenta-hued pixels (missing textures). Hue test, because AgX and dim light turn
    the pure (1, 0, 1) placeholder into a dull purple that a value threshold misses."""
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1e-6)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    magenta = (g == mn) & (sat > 0.45) & (mx > 0.08) & (np.abs(r - b) < 0.35 * mx)
    return round(float(magenta.mean()), 5)


def image_stats(disp, lin=None):
    rgb = disp[..., :3]
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
    st = {
        "mean_lum": round(float(lum.mean()), 4),
        "std_lum": round(float(lum.std()), 4),
        "p05": round(float(np.percentile(lum, 5)), 4),
        "p95": round(float(np.percentile(lum, 95)), 4),
        "pct_black": round(float((rgb.max(-1) <= 0.02).mean()), 4),
        "pct_clipped": round(float((rgb.min(-1) >= 0.99).mean()), 4),
        "pct_magenta": _magenta_frac(rgb),
    }
    if lin is not None:
        lrgb = lin[..., :3]
        alpha = lin[..., 3]
        mask = alpha > 0.5
        st["alpha_coverage"] = round(float(mask.mean()), 4)
        st["nan_px"] = int(np.isnan(lrgb).any(-1).sum())
        st["inf_px"] = int(np.isinf(lrgb).any(-1).sum())
        llum = np.nan_to_num(lrgb) @ np.array([0.2126, 0.7152, 0.0722])
        med = float(np.median(llum[mask])) if mask.any() else 0.0
        bright = llum > max(10.0, 50 * med)
        # fireflies are *isolated* hot pixels; lamps and emissive surfaces are bright regions
        pad = np.pad(bright, 1)
        neigh = sum(pad[1 + dy:pad.shape[0] - 1 + dy, 1 + dx:pad.shape[1] - 1 + dx]
                    for dy in (-1, 0, 1) for dx in (-1, 0, 1)) - bright
        st["firefly_frac"] = round(float((bright & (neigh <= 1)).mean()), 6)
        ys, xs = np.nonzero(mask)
        if len(xs):
            st["content_bbox"] = [round(xs.min() / mask.shape[1], 3), round(1 - (ys.max() + 1) / mask.shape[0], 3),
                                  round((xs.max() + 1) / mask.shape[1], 3), round(1 - ys.min() / mask.shape[0], 3)]
    return st


def judge(st, findings, tag):
    def add(sev, msg):
        findings.append({"severity": sev, "view": tag, "message": msg})
    if st["std_lum"] < 0.01:
        add("FAIL", f"{tag}: image is flat (std {st['std_lum']}) - blank/black/white render.")
    if st["mean_lum"] < 0.04:
        add("FAIL" if st["mean_lum"] < 0.01 else "WARN", f"{tag}: very dark (mean display luminance {st['mean_lum']}).")
    elif st["mean_lum"] > 0.85:
        add("WARN", f"{tag}: very bright (mean display luminance {st['mean_lum']}).")
    if st["pct_clipped"] > 0.05:
        add("WARN", f"{tag}: {st['pct_clipped']:.1%} of pixels clipped to white.")
    if st["pct_magenta"] > 0.01:
        add("WARN", f"{tag}: {st['pct_magenta']:.1%} magenta/purple pixels - missing texture? "
                    "(or a genuinely purple design: check the image)")
    if st.get("nan_px") or st.get("inf_px"):
        add("FAIL", f"{tag}: {st.get('nan_px', 0)} NaN / {st.get('inf_px', 0)} Inf pixels in the linear render.")
    if "alpha_coverage" in st and st["alpha_coverage"] < 0.01:
        add("FAIL", f"{tag}: almost no geometry in frame (alpha coverage {st['alpha_coverage']:.2%}).")
    if st.get("firefly_frac", 0) > 5e-4:
        add("WARN", f"{tag}: fireflies ({st['firefly_frac']:.3%} of pixels are extreme outliers).")


def parse_frames(spec, sc):
    out = []
    for tok in (spec or "").split(","):
        tok = tok.strip().lower()
        if not tok:
            continue
        if tok in ("start", "first"):
            out.append(sc.frame_start)
        elif tok in ("end", "last"):
            out.append(sc.frame_end)
        elif tok == "mid":
            out.append((sc.frame_start + sc.frame_end) // 2)
        else:
            out.append(int(tok))
    return sorted(set(out)) or [sc.frame_current]


def main(argv=None):
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--frames", default="", help="e.g. 1,mid,end (default: current frame)")
    ap.add_argument("--long-side", type=int, default=960, help="camera-view long side in px")
    ap.add_argument("--tile", type=int, default=512, help="geometry view size in px")
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--views", default="front,right,top,iso")
    ap.add_argument("--focus", default="", help="glob of objects to frame close-up")
    ap.add_argument("--no-camera", action="store_true")
    ap.add_argument("--keep-walls", action="store_true", help="do not hide walls/ceilings in geometry views")
    args, _unknown = ap.parse_known_args(argv)  # tolerate Blender's own --cycles-device

    sc = bpy.context.scene
    vl = bpy.context.view_layer
    rs = sc.render
    out = args.out_dir or os.path.join(os.path.dirname(bpy.data.filepath) or os.getcwd(), "qc_out")
    out = os.path.abspath(out)
    os.makedirs(out, exist_ok=True)
    report = {"out_dir": out, "camera_views": [], "geometry_views": [], "findings": [], "errors": []}
    R = Restore()
    cur = sc.frame_current
    t0 = time.time()
    temp = []
    try:
        R.set(rs, "use_compositing", False)
        R.set(rs, "use_sequencer", False)
        R.set(rs, "use_stamp", False)
        R.set(rs, "use_stamp_filename", False)  # PNG metadata would otherwise carry the .blend path
        R.set(rs, "filepath", rs.filepath)
        # ---------- camera view(s) in the shipping engine
        if not args.no_camera and sc.camera is not None:
            ok = True
            scale = min(1.0, args.long_side / max(rs.resolution_x, rs.resolution_y))
            R.set(rs, "resolution_percentage", max(1, int(100 * scale)))
            R.set(rs, "use_motion_blur", False)
            if rs.engine == "CYCLES":
                R.set(sc.cycles, "samples", min(sc.cycles.samples, args.samples * 4))
                R.set(sc.cycles, "use_denoising", True)
                R.set(sc.cycles, "time_limit", 60.0)
            elif rs.engine.startswith("BLENDER_EEVEE"):
                R.set(sc.eevee, "taa_render_samples", min(sc.eevee.taa_render_samples, args.samples))
            for f in parse_frames(args.frames, sc):
                sc.frame_set(f)
                entry = {"frame": f, "engine": rs.engine}
                try:
                    png = os.path.join(out, f"camera_f{f:04d}.png")
                    set_still_png(rs, R, png)
                    do_render(png)
                    entry["png"] = png
                    lin = None
                    if ok:
                        exr = os.path.join(out, f"camera_f{f:04d}_linear.exr")
                        film = rs.film_transparent
                        R.set(rs, "film_transparent", True)
                        R.set(rs.image_settings, "file_format", "OPEN_EXR")
                        R.set(rs.image_settings, "color_mode", "RGBA")
                        R.set(rs.image_settings, "color_depth", "32")
                        rs.filepath = exr
                        do_render(exr)
                        lin = load_px(exr)
                        rs.film_transparent = film
                    entry["stats"] = image_stats(load_px(png), lin)
                    judge(entry["stats"], report["findings"], f"camera@{f}")
                except Exception as exc:  # GPU-less Linux etc.
                    report["errors"].append(f"camera render frame {f} with {rs.engine}: {exc}")
                    ok = False
                report["camera_views"].append(entry)
        elif sc.camera is None:
            report["findings"].append({"severity": "FAIL", "view": "camera", "message": "scene.camera is None."})
        sc.frame_set(cur)

        # ---------- geometry views (Workbench, random colours, walls hidden)
        objs = [o for o in sc.objects if o.type in GEOM and renders(o, vl)]
        hide = []
        if not args.keep_walls:
            for o in objs:
                t = _tokens(o.name)
                if t & HIDE_WORDS and not t & KEEP_WORDS:
                    hide.append(o)
        focus = [o for o in objs if args.focus and fnmatch.fnmatchcase(o.name, args.focus)]
        content = focus or [o for o in objs if o not in hide] or objs
        for o in hide:
            R.set(o, "hide_render", True)
        if not focus and len(content) > 2:
            # don't fit the views to a 4 km sea / ground plane: drop objects far larger than the rest
            fit = []
            for o in content:
                rest = [p for p in content if p is not o]
                olo, ohi = world_bbox([o])
                rlo, rhi = world_bbox(rest)
                if max(ohi.x - olo.x, ohi.y - olo.y) <= 3 * max(rhi.x - rlo.x, rhi.y - rlo.y, 1e-6):
                    fit.append(o)
            content = fit or content
        lo, hi = world_bbox(content)
        if focus:
            pad = max((hi - lo).length * 0.6, 0.05)
            lo, hi = lo - Vector((pad, pad, pad)), hi + Vector((pad, pad, pad))
            for o in objs:  # isolate the neighbourhood so nothing outside it blocks the view
                olo, ohi = world_bbox([o])
                if o not in hide and ((olo.x > hi.x or ohi.x < lo.x) or (olo.y > hi.y or ohi.y < lo.y)
                                      or (olo.z > hi.z or ohi.z < lo.z)):
                    hide.append(o)
                    R.set(o, "hide_render", True)
        ctr = (lo + hi) / 2
        size = max((hi - lo).length, 1e-3)
        R.set(rs, "engine", "BLENDER_WORKBENCH")
        sh = sc.display.shading
        R.set(sh, "light", "STUDIO")
        R.set(sh, "color_type", "RANDOM")
        R.set(sh, "show_cavity", True)
        R.set(sh, "show_object_outline", True)
        R.set(sh, "show_shadows", True)
        R.set(rs, "resolution_x", args.tile)
        R.set(rs, "resolution_y", args.tile)
        R.set(rs, "resolution_percentage", 100)
        R.set(rs, "film_transparent", False)
        R.set(sc.display, "render_aa", "8")
        cd = bpy.data.cameras.new("QC_TMP_CAM")
        cd.type = "ORTHO"
        cd.clip_start = size * 0.001
        cd.clip_end = size * 20
        cam = bpy.data.objects.new("QC_TMP_CAM", cd)
        sc.collection.objects.link(cam)
        temp.append(cam)
        R.set(sc, "camera", cam)
        dirs = {"front": (0, -1, 0), "back": (0, 1, 0), "right": (1, 0, 0), "left": (-1, 0, 0),
                "top": (0, 0, 1), "iso": (1, -1, 0.8), "iso_back": (-1, 1, 0.8)}
        tiles = []
        for name in [v.strip() for v in args.views.split(",") if v.strip() in dirs]:
            d = Vector(dirs[name]).normalized()
            ext = hi - lo
            if name in ("front", "back"):
                cd.ortho_scale = max(ext.x, ext.z) * 1.08
            elif name in ("right", "left"):
                cd.ortho_scale = max(ext.y, ext.z) * 1.08
            elif name == "top":
                cd.ortho_scale = max(ext.x, ext.y) * 1.08
            else:
                cd.ortho_scale = size * 0.95
            cam.location = ctr + d * size * 3
            cam.rotation_euler = (-d).to_track_quat("-Z", "Y" if name != "top" else "Y").to_euler()
            vl.update()
            path = os.path.join(out, f"geo_{'focus_' if focus else ''}{name}.png")
            set_still_png(rs, R, path)
            try:
                do_render(path)
                report["geometry_views"].append({"view": name, "png": path,
                                                 "ortho_scale_m": round(cd.ortho_scale * sc.unit_settings.scale_length, 3)})
                tiles.append(load_px(path))
            except Exception as exc:
                report["errors"].append(f"workbench {name}: {exc}")
                break
        if tiles:
            h = max(t.shape[0] for t in tiles)
            row = [np.pad(t, ((0, h - t.shape[0]), (0, 0), (0, 0)), constant_values=1.0) for t in tiles]
            sheet = np.concatenate(row, axis=1)
            img = bpy.data.images.new("QC_SHEET", sheet.shape[1], sheet.shape[0], alpha=True)
            img.pixels.foreach_set(sheet.ravel())
            spath = os.path.join(out, "contact_sheet_focus.png" if focus else "contact_sheet.png")
            img.filepath_raw = spath
            img.file_format = "PNG"
            img.save()
            bpy.data.images.remove(img)
            report["contact_sheet"] = spath
            report["contact_sheet_order"] = [v["view"] for v in report["geometry_views"]]
        report["hidden_for_geometry_views"] = [o.name for o in hide]
        report["focus"] = [o.name for o in focus]
    finally:
        R.undo()
        for o in temp:
            data = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            if data and data.users == 0:
                bpy.data.cameras.remove(data)
        sc.frame_set(cur)
    report["runtime_s"] = round(time.time() - t0, 2)
    path = os.path.join(out, "render_report.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    fails = sum(1 for f in report["findings"] if f["severity"] == "FAIL")
    print(f"[render_views] {len(report['camera_views'])} camera view(s), {len(report['geometry_views'])} "
          f"geometry view(s), {fails} FAIL, {len(report['errors'])} error(s) -> {path}")
    return report


if __name__ == "__main__":
    _argv = globals().get("QC_ARGV")
    main(list(_argv) if _argv is not None else None)
