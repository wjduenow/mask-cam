"""Sizing the electronics bay -- the version that is allowed to CARVE the mask.

analyze_fit.py asked "does the board fit in the cavity as it stands?" and got a
disappointing 9.3 mm.  That was the wrong question.  The mask is an 8-27 mm thick
shell, not a thin one, so the bay may eat into that material as long as it leaves a
decent front wall -- the relief the eye actually sees is only the outermost few mm.

Budget at any (x, z):

    interior depth available = (front surface stand-off from the wall plane)
                               - FRONT_WALL_MIN   relief we must not break through
                               - RIM_INSET        keeps the bay rim, its lid and the
                                                  screw heads INSIDE the mask's own rear
                                                  envelope, so nothing protrudes past
                                                  the wall plane

Cells that are inside the mask's outline but have no material (the gaps between the
teeth, the slots between the crown petals) are NOT constraints -- they are holes the
bay floor simply inherits -- so they are excluded from the minimum rather than
counted as zero depth.  Cells outside the outline are hard exclusions.
"""
import numpy as np
from scipy import ndimage

d = np.load("cavity.npz")
xs, zs, YB, YF, STEP = d["xs"], d["zs"], d["YB"], d["YF"], float(d["STEP"])
solid = ~np.isnan(YF)
outline = ndimage.binary_fill_holes(solid)          # silhouette incl. its holes
holes = outline & ~solid

FRONT_WALL_MIN = 3.0
RIM_INSET = 4.0
BOARD_STACK_T = 14.5
BOARD_CLR = 1.5
NEED = BOARD_STACK_T + BOARD_CLR

AVAIL = np.where(solid, -YF - FRONT_WALL_MIN - RIM_INSET, np.nan)
AVAIL = np.where(holes, np.inf, AVAIL)              # holes constrain nothing
AVAIL = np.where(outline, AVAIL, -1e3)              # off-mask is fatal


def running_min(a, k, axis):
    out, n = a, 1
    while n < k:
        s = min(n, k - n)
        sa, sb = [slice(None)] * a.ndim, [slice(None)] * a.ndim
        sa[axis] = slice(0, out.shape[axis] - s)
        sb[axis] = slice(s, out.shape[axis])
        out = np.minimum(out[tuple(sa)], out[tuple(sb)])
        n += s
    return out


def window_min(w_mm, h_mm, field=AVAIL):
    kw, kh = int(round(w_mm / STEP)), int(round(h_mm / STEP))
    R = running_min(running_min(field, kh, 0), kw, 1)
    return R, kw, kh


def best_window(w_mm, h_mm):
    R, kw, kh = window_min(w_mm, h_mm)
    i, j = np.unravel_index(np.argmax(R), R.shape)
    return R[i, j], xs[j] + (kw - 1) * STEP / 2, zs[i] + (kh - 1) * STEP / 2


print(f"need {NEED:.1f} mm of interior (board {BOARD_STACK_T} + {BOARD_CLR} air), "
      f"leaving {FRONT_WALL_MIN} mm relief + {RIM_INSET} mm rim inset\n")
print(f"{'bay opening (X x Z)':>26}  {'avail':>6}  {'centre (x,z)':>17}  verdict")
for label, (w, h) in {
    "PCB only 30.4 x 38.4": (30.4, 38.4),
    "PCB + 1.5 clr 33.4 x 41.4": (33.4, 41.4),
    "+ 3 mm walls  39.4 x 47.4": (39.4, 47.4),
    "+ screw bosses 46 x 54": (46.0, 54.0),
    "50 x 58": (50.0, 58.0),
    "56 x 64": (56.0, 64.0),
    "60 x 70": (60.0, 70.0),
}.items():
    a, cx, cz = best_window(w, h)
    print(f"{label:>26}  {a:6.1f}   ({cx:6.1f}, {cz:6.1f})   "
          f"{'OK' if a >= NEED else f'SHORT by {NEED - a:.1f}'}")

print("\n--- centred on the mirror line (x = 0): best z for each bay size ---")
for w in (39.4, 46.0, 52.0):
    R, kw, kh_unused = window_min(w, 1.0)
    j = int(np.argmin(np.abs(xs - (-w / 2))))
    strip = R[:, j]
    for h in (44.0, 50.0, 56.0, 62.0, 70.0):
        kh = int(round(h / STEP))
        run = running_min(strip[:, None], kh, 0)[:, 0]
        i = int(np.argmax(run))
        print(f"  bay {w:5.1f} x {h:5.1f}: avail {run[i]:6.1f} mm   "
              f"z {zs[i]:5.1f} .. {zs[i] + h:5.1f}   "
              f"{'OK' if run[i] >= NEED else 'SHORT'}")

np.savez("pod.npz", xs=xs, zs=zs, AVAIL=AVAIL, outline=outline, solid=solid,
         holes=holes, STEP=STEP, YF=YF, YB=YB)
print("\nwrote pod.npz")
