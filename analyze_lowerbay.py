"""Resize the lower bay for a TP4056 + a flat LiPo, now that charging must be external.

The current pocket (26 x 14 x 21.9) is the wrong SHAPE: it is deep and small-faced, while
both new occupants are flat slabs.  Trade depth for face area and see how big a face the
mask's muzzle can carry.
"""
import numpy as np
from measure import standoff_min_rect
import mask_params as P

FW, CT = P.FRONT_WALL, P.COVER_T

print("interior depth available for a lower pocket of a given FACE size")
print(f"(= worst stand-off - {FW} relief - {CT} cover)\n")
print(f"{'face (w x h)':>16} {'z span':>14} {'standoff':>9} {'interior':>9}   fits?")
print("-" * 74)

CANDIDATES = []
for w in (26, 28, 30, 32, 34):
    for z0, z1 in ((14, 34), (16, 36), (18, 38), (20, 40),
                   (14, 38), (16, 40), (12, 36), (18, 42)):
        s = standoff_min_rect(-w / 2, w / 2, z0, z1)
        if not np.isfinite(s):
            continue
        interior = s - FW - CT
        if interior < 4.0:
            continue
        CANDIDATES.append((w, z1 - z0, z0, z1, s, interior))

CANDIDATES.sort(key=lambda c: -(c[0] * c[1]))
seen = set()
for w, h, z0, z1, s, interior in CANDIDATES:
    key = (w, h)
    if key in seen:
        continue
    seen.add(key)
    # what fits in this face?
    tp = "TP4056 (26x17)" if (w >= 28 and h >= 19) else ""
    lipo = ""
    for name, (lw, lh, lt) in {"603048 (1000mAh)": (30, 48, 6),
                               "503040 (600mAh)": (30, 40, 5),
                               "502535 (400mAh)": (25, 35, 5),
                               "402030 (200mAh)": (20, 30, 4)}.items():
        if w >= lw + 2 and h >= lh + 2 and interior >= lt + 1:
            lipo = name
            break
    fits = " + ".join(x for x in (tp, lipo) if x) or "—"
    print(f"{w:6.0f} x {h:5.0f}  {z0:5.0f}..{z1:<5.0f} {s:9.2f} {interior:9.2f}   {fits}")

print("\n=== can BOTH live in the lower bay, stacked in depth? ===")
for w, z0, z1 in ((30, 16, 40), (32, 14, 40), (30, 14, 38)):
    s = standoff_min_rect(-w / 2, w / 2, z0, z1)
    if not np.isfinite(s):
        continue
    interior = s - FW - CT
    need = 4.0 + 1.0 + 4.0 + 1.0          # LiPo 4 + air + TP4056 4 + air
    print(f"  {w} x {z1-z0} face, interior {interior:5.2f} mm: "
          f"LiPo + TP4056 stacked needs {need:.1f} -> "
          f"{'OK, ' + format(interior-need, '+.2f') + ' spare' if interior >= need else 'SHORT'}")
