#!/usr/bin/env python3
"""run_qc.py - one-command headless QC of a .blend (system Python 3.8+, no dependencies).

    python3 run_qc.py scene.blend [--out-dir DIR] [--intent intent.json] [--physics MODE]
                      [--frames 1,mid,end] [--focus "Mug*"] [--no-render] [--simulate auto|on|off]
                      [--autoexec] [--blender PATH] [--cycles-device METAL|CUDA|OPTIX|HIP|ONEAPI]

Runs two separate Blender processes (so a crash in one cannot hide the other):
  1. blender_qc.py   -> qc.json + qc.md      (scene facts, physics, materials, camera, animation)
  2. render_views.py -> camera_f*.png, contact_sheet.png, render_report.json

Exit code: 0 = no FAIL, 2 = FAIL findings, 1 = the tool itself broke (read the logs).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def find_blender(explicit: str | None) -> str:
    cands = [explicit, os.environ.get("BLENDER"), os.environ.get("BLENDER_BIN"), shutil.which("blender")]
    if sys.platform == "darwin":
        cands += ["/Applications/Blender.app/Contents/MacOS/Blender",
                  os.path.expanduser("~/Applications/Blender.app/Contents/MacOS/Blender")]
        cands += sorted(glob.glob("/Applications/Blender*.app/Contents/MacOS/Blender"), reverse=True)
    elif sys.platform.startswith("win"):
        cands += sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"), reverse=True)
    else:
        cands += ["/usr/bin/blender", "/usr/local/bin/blender", "/snap/bin/blender",
                  os.path.expanduser("~/blender/blender")]
        cands += sorted(glob.glob(os.path.expanduser("~/blender-*/blender")), reverse=True)
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    sys.exit("run_qc: Blender not found. Pass --blender /path/to/blender or set $BLENDER.")


def run(cmd, log_path, timeout):
    with open(log_path, "w", encoding="utf-8") as log:
        try:
            p = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            return p.returncode
        except subprocess.TimeoutExpired:
            log.write(f"\n[run_qc] TIMEOUT after {timeout}s\n")
            return 124


def tail(path, n=25):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return "".join(fh.readlines()[-n:])
    except OSError:
        return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("blend")
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--intent", default="")
    ap.add_argument("--physics", choices=["realistic", "stylized", "off"])
    ap.add_argument("--simulate", default="auto", choices=["auto", "on", "off"])
    ap.add_argument("--sim-frames", type=int, default=250)
    ap.add_argument("--time-budget", type=float, default=300)
    ap.add_argument("--frames", default="", help="camera frames to render, e.g. 1,mid,end")
    ap.add_argument("--focus", default="", help="glob: extra close-up geometry views of these objects")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--autoexec", action="store_true", help="allow Python drivers/scripts (trusted files only)")
    ap.add_argument("--user-prefs", action="store_true", help="do not pass --factory-startup")
    ap.add_argument("--cycles-device", default="", help="GPU backend for Cycles renders (else CPU)")
    ap.add_argument("--blender", default="")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args()

    blend = os.path.abspath(a.blend)
    if not os.path.isfile(blend):
        sys.exit(f"run_qc: {blend} does not exist - save the scene first (headless QC audits the file on disk).")
    out = os.path.abspath(a.out_dir or os.path.join(os.path.dirname(blend), "qc_out"))
    os.makedirs(out, exist_ok=True)
    blender = find_blender(a.blender)
    base = [blender, "-b", blend]  # the .blend must come BEFORE --python, or the script runs on the startup scene
    if not a.user_prefs:
        base.append("--factory-startup")
    base.append("--enable-autoexec" if a.autoexec else "--disable-autoexec")
    base += ["--python-exit-code", "1"]  # must precede --python, else exceptions exit 0

    qc_json, qc_md = os.path.join(out, "qc.json"), os.path.join(out, "qc.md")
    for stale in (qc_json, os.path.join(out, "render_report.json")):
        if os.path.exists(stale):
            os.remove(stale)
    cmd = base + ["--python", os.path.join(HERE, "blender_qc.py"), "--",
                  "--out", qc_json, "--md", qc_md, "--simulate", a.simulate,
                  "--sim-frames", str(a.sim_frames), "--time-budget", str(a.time_budget)]
    if a.intent:
        cmd += ["--intent", os.path.abspath(a.intent)]
    if a.physics:
        cmd += ["--physics", a.physics]
    rc = run(cmd, os.path.join(out, "blender_audit.log"), a.timeout)
    broken = False
    if rc != 0 or not os.path.exists(qc_json):
        broken = True
        print(f"[run_qc] AUDIT FAILED TO RUN (exit {rc}). Log tail:\n{tail(os.path.join(out, 'blender_audit.log'))}")
        res = None
    else:
        with open(qc_json, encoding="utf-8") as fh:
            res = json.load(fh)

    rr = None
    if not a.no_render:
        cmd = base + ["--python", os.path.join(HERE, "render_views.py"), "--", "--out-dir", out]
        if a.frames:
            cmd += ["--frames", a.frames]
        if a.focus:
            cmd += ["--focus", a.focus]
        if a.cycles_device:
            cmd += ["--cycles-device", a.cycles_device]
        rc2 = run(cmd, os.path.join(out, "blender_render.log"), a.timeout)
        rpath = os.path.join(out, "render_report.json")
        if rc2 != 0 or not os.path.exists(rpath):
            print(f"[run_qc] render step failed (exit {rc2}) - visual evidence missing. Log tail:\n"
                  f"{tail(os.path.join(out, 'blender_render.log'))}")
        else:
            with open(rpath, encoding="utf-8") as fh:
                rr = json.load(fh)

    # ---------- summary
    fails = 0
    if res:
        m = res["meta"]
        print(f"QC {res['verdict']}: {res['summary']['FAIL']} FAIL, {res['summary']['WARN']} WARN, "
              f"{res['summary']['INFO']} INFO | Blender {m['blender']} | physics={m['intent']['physics']} "
              f"| {m['entries_checked']} meshes | {m['runtime_s']}s")
        fails += res["summary"]["FAIL"]
        shown = 0
        for f in res["findings"]:
            if f["severity"] == "INFO":
                continue
            if shown >= 30:
                print(f"  ... more in {qc_md}")
                break
            print(f"  {f['severity']} {f['id']}: {f['message']}")
            shown += 1
        crashed = [c["check"] for c in res["checks"] if c["status"] != "ok"]
        if crashed:
            print(f"  NOT VERIFIED (check crashed): {', '.join(crashed)}")
    if rr:
        for f in rr["findings"]:
            print(f"  {f['severity']} render: {f['message']}")
            fails += f["severity"] == "FAIL"
        for e in rr["errors"]:
            print(f"  render error: {e}")
        imgs = [v["png"] for v in rr["camera_views"] if v.get("png")]
        if rr.get("contact_sheet"):
            imgs.append(rr["contact_sheet"])
        print("LOOK AT:", *imgs, sep="\n  ")
    print(f"Reports: {qc_md} | {qc_json}")
    if broken:
        sys.exit(1)
    sys.exit(2 if fails else 0)


if __name__ == "__main__":
    main()
