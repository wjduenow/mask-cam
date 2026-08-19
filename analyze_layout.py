"""Interior layout: how tall a bay can the mask's central column carry, and where does
each component go inside it?

The bay is a tube unioned onto the mask's rear surface, reaching back to a rim plane,
with its pocket cut forward into the mask's material.  For an inner width W centred on
the mirror line, the pocket floor at any z can go no further forward than

    y_floor(z) >= YF(z) + FRONT_WALL          (don't break the relief)

so the interior depth available at that z is

    STANDOFF_min(z, W) - FRONT_WALL - LID_T

This prints that profile down the whole column so the components can be stacked by z.
"""
import numpy as np

d = np.load("pod.npz")
xs, zs, YF, STEP = d["xs"], d["zs"], d["YF"], float(d["STEP"])
solid, outline, holes = d["solid"], d["outline"], d["holes"]

S = np.where(solid, -YF, np.nan)
S = np.where(holes, np.inf, S)
S = np.where(outline, S, -1e3)

FRONT_WALL = 3.0
LID_T = 2.5            # lid outer face flush with the wall plane (y = 0)

# component stack heights (mm along Y)
PARTS = {
    "ESP32-S3-CAM, pins snipped": 10.5 + 1.0,
    "ESP32-S3-CAM, pins intact": 14.5 + 1.0,
    "LiPo 503450 (5.0 thick)": 5.0 + 1.0,
    "LiPo 603048 (6.0 thick)": 6.0 + 1.0,
    "USB-C breakout (3.5 thick)": 3.5 + 1.0,
    "camera module (lens ~7 tall)": 7.0 + 1.0,
}


def col_profile(W):
    """min stand-off across a width-W band centred on x=0, per z row."""
    j0 = int(np.argmin(np.abs(xs - (-W / 2))))
    j1 = int(np.argmin(np.abs(xs - (W / 2))))
    return np.nanmin(np.where(np.isinf(S[:, j0:j1 + 1]), np.nan, S[:, j0:j1 + 1]), axis=1)


print(f"interior depth = stand-off - {FRONT_WALL} (relief) - {LID_T} (lid)\n")
widths = (30.0, 34.0, 38.0, 42.0)
print("   z |" + "".join(f"  W={w:4.0f}" for w in widths))
print("-----+" + "-------" * len(widths))
profs = {w: col_profile(w) for w in widths}
for z in np.arange(4, 106, 3.0):
    i = int(np.argmin(np.abs(zs - z)))
    row = f"{z:5.1f}|"
    for w in widths:
        v = profs[w][i]
        row += f"  {v - FRONT_WALL - LID_T:5.1f}" if np.isfinite(v) else "    --"
    print(row)

print("\n--- contiguous z bands with enough interior depth, at each bay width ---")
for w in widths:
    avail = profs[w] - FRONT_WALL - LID_T
    for name, need in PARTS.items():
        ok = np.nan_to_num(avail, nan=-99) >= need
        # longest run of True
        best_len, best_start, run, start = 0, None, 0, None
        for i, v in enumerate(ok):
            if v:
                if run == 0:
                    start = i
                run += 1
                if run > best_len:
                    best_len, best_start = run, start
            else:
                run = 0
        if best_len:
            print(f"  W={w:4.0f}  {name:30s} needs {need:5.1f} -> "
                  f"z {zs[best_start]:5.1f} .. {zs[best_start + best_len - 1]:5.1f} "
                  f"({best_len * STEP:5.1f} mm tall)")
        else:
            print(f"  W={w:4.0f}  {name:30s} needs {need:5.1f} -> NOWHERE")
