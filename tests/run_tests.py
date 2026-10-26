#!/usr/bin/env python3
"""Regression tests: build fixture scenes with planted defects, audit them, check the findings.

    python3 tests/run_tests.py [--blender /path/to/blender] [--keep DIR]

Needs only Blender (4.2+; developed on 5.2 LTS) and a system Python 3.8+.
Exit 0 when every expectation holds.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "skills", "blender-qc-audit", "scripts")
sys.path.insert(0, SCRIPTS)
from run_qc import find_blender  # noqa: E402

# fixture -> (ids that must appear at >= the given severity, ids that must NOT appear as FAIL/WARN)
EXPECT = {
    "clean_room": ({}, "any"),
    "defect_room": ({
        "image.missing": "FAIL",
        "physics.floating": "FAIL",        # crate 10 cm above the table
        "physics.intersection": "FAIL",    # mug 3 cm into the table
        "physics.scale": "FAIL",           # 1.2 m coffee cup (and 4.5 m door as WARN)
        "anim.fall_eases_out": "WARN",
        "geometry.inverted_normals": "WARN",
        "material.colorspace_data": "WARN",
        "objects.hidden_but_renders": "WARN",
        "objects.stacked_duplicates": "WARN",
        "physics.side_supported": "WARN",
        "physics.wall_gap": "WARN",
        "transform.rotation_mode_ignored": "WARN",
    }, None),
    "rigid_drop": ({
        "sim.explosion": "FAIL",
        "sim.fell_through": "FAIL",
        "sim.initial_overlap": "WARN",
        "sim.mesh_shape_active": "WARN",
        "sim.cache_short": "WARN",
    }, None),
    "cloth_soft": ({
        "sim.cloth_through_floor": "FAIL",
        "sim.cloth_no_collider": "WARN",
    }, None),
}
RANK = {"FAIL": 0, "WARN": 1, "INFO": 2}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", default="")
    ap.add_argument("--keep", default="", help="keep fixtures and reports in this folder")
    a = ap.parse_args()
    blender = find_blender(a.blender)
    work = os.path.abspath(a.keep) if a.keep else tempfile.mkdtemp(prefix="bqc_tests_")
    os.makedirs(work, exist_ok=True)
    print(f"Blender: {blender}\nWork dir: {work}")
    r = subprocess.run([blender, "-b", "--factory-startup", "--python-exit-code", "1",
                        "--python", os.path.join(HERE, "make_fixtures.py"), "--", work],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:])
        return 1
    failures = 0
    for name, (must, clean) in EXPECT.items():
        out = os.path.join(work, f"qc_{name}")
        render = name == "defect_room"  # exercise render_views once
        cmd = [sys.executable, os.path.join(SCRIPTS, "run_qc.py"), os.path.join(work, f"{name}.blend"),
               "--out-dir", out, "--blender", blender] + ([] if render else ["--no-render"])
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode == 1 or not os.path.exists(os.path.join(out, "qc.json")):
            print(f"[FAIL] {name}: audit did not run\n{p.stdout[-1500:]}")
            failures += 1
            continue
        res = json.load(open(os.path.join(out, "qc.json")))
        best = {}
        for f in res["findings"]:
            best[f["id"]] = min(best.get(f["id"], 9), RANK[f["severity"]])
        problems = []
        for fid, sev in must.items():
            if best.get(fid, 9) > RANK[sev]:
                problems.append(f"expected {fid} >= {sev}")
        if clean == "any":
            loud = [f"{f['severity']} {f['id']}" for f in res["findings"] if f["severity"] != "INFO"]
            if loud:
                problems.append(f"clean scene reported {loud}")
        crashed = [c["check"] for c in res["checks"] if c["status"] != "ok"]
        if crashed:
            problems.append(f"checks crashed: {crashed}")
        if render:
            rr = os.path.join(out, "render_report.json")
            if not os.path.exists(rr) or json.load(open(rr))["errors"]:
                problems.append("render_views failed")
        status = "ok" if not problems else "FAIL"
        failures += bool(problems)
        print(f"[{status}] {name}: {res['verdict']} {res['summary']}" + "".join(f"\n    - {x}" for x in problems))
    if not a.keep:
        shutil.rmtree(work, ignore_errors=True)
    print("ALL PASS" if not failures else f"{failures} fixture(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
