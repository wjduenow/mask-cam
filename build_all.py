"""Build every part, then verify the result.  One command, and it refuses to lie.

    python build_all.py

Order matters: analyse -> build -> verify.  The analysis pass writes the 0.5 mm sampled
grid that mask_params.py derives its floors from, so a fresh checkout produces the same
numbers rather than trusting the ones written in the file.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

STAGES = [
    ("sample the donor's surfaces", "analyze_cavity.py", "cavity.npz"),
    ("derive the bay envelope", "analyze_pod.py", "pod.npz"),
    ("locate the eyeballs", "analyze_eyes.py", "eyes.npz"),
    ("build the mask", "build_mask.py", "mask_cam.stl"),
    ("build the cover", "build_cover.py", "cover.stl"),
    ("build the small parts", "build_smalls.py", "camera_clamp.stl"),
    ("build the stand", "build_stand.py", "stand.stl"),
    ("verify the result", "verify.py", None),
    ("verify the cover", "verify_cover.py", None),
    ("verify the stand", "verify_stand.py", None),
    ("render the preview", "render_preview.py", "render_preview.png"),
]


def main():
    force = "--force" in sys.argv
    for label, script, product in STAGES:
        path = os.path.join(HERE, product) if product else None
        if path and os.path.exists(path) and not force and script.startswith("analyze"):
            print(f"--- {label}: {product} present, skipping (--force to redo)")
            continue
        print(f"\n=== {label}  ({script}) " + "=" * max(0, 50 - len(label)))
        r = subprocess.run([PY, os.path.join(HERE, script)], cwd=HERE)
        if r.returncode != 0:
            raise SystemExit(f"\n{script} failed -- stopping.  Nothing here is safe to "
                             f"print until it passes.")
    print("\n" + "=" * 70)
    print("all parts built and verified:")
    for f in ("mask_cam.stl", "cover.stl", "stand.stl", "camera_clamp.stl",
              "camera_shims.stl", "eye_plugs.stl", "render_preview.png"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            print(f"  {f:20s} {os.path.getsize(p)/1024:8.0f} kB")


if __name__ == "__main__":
    main()
