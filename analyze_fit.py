"""Where exactly does the board go, and how deep does the pod have to be?

Reads cavity.npz (from analyze_cavity.py) and answers:

  A. Sliding-window fit: over every placement of the board footprint, what is the
     WORST cavity depth inside that window?  The pod's back plate must sit at
     y = -(worst depth) - clearance, so a negative "worst depth" surplus tells us
     exactly how far the pod protrudes PAST the wall plane (y > 0), which is the
     one thing that costs us: it lifts the mask off the wall.
  B. Candidate lens sites: eyes / mouth / forehead, with the local wall thickness
     the lens must punch through and the cavity depth behind it.
  C. Existing through-holes in the donor mesh (the mouth already has some).
"""
import numpy as np

d = np.load("cavity.npz")
xs, zs, YB, YF, NC, STEP = d["xs"], d["zs"], d["YB"], d["YF"], d["NC"], float(d["STEP"])
DEPTH = -YB                      # cavity depth from the wall plane (NaN outside)
THICK = YB - YF
solid = ~np.isnan(YB)

PCB_W, PCB_L = 30.4, 38.4
BOARD_STACK_T = 14.5
CLR = 1.0                        # air behind the header pin tips


def window_min_depth(w_mm, h_mm):
    """For a w x h window, the max over placements of (min depth inside), + its centre.

    Cells outside the silhouette count as depth 0: the pod's back plate has to close
    over them too, so they are not free space.
    """
    D = np.where(solid, DEPTH, 0.0)
    kw, kh = int(round(w_mm / STEP)), int(round(h_mm / STEP))
    # min over a rectangle via two 1-D running minima
    def running_min(a, k, axis):
        out = a
        n = 1
        while n < k:
            step = min(n, k - n)
            sl_a = [slice(None)] * a.ndim
            sl_b = [slice(None)] * a.ndim
            sl_a[axis] = slice(0, out.shape[axis] - step)
            sl_b[axis] = slice(step, out.shape[axis])
            out = np.minimum(out[tuple(sl_a)], out[tuple(sl_b)])
            n += step
        return out
    R = running_min(running_min(D, kh, 0), kw, 1)
    i, j = np.unravel_index(np.argmax(R), R.shape)
    cx = xs[j] + (kw - 1) * STEP / 2
    cz = zs[i] + (kh - 1) * STEP / 2
    return R[i, j], cx, cz, R


print("=== A. board footprint fit (depth available under the whole footprint) ===")
print(f"{'footprint':>22}  {'min depth':>9}  {'centre (x,z)':>18}  verdict")
for label, (w, h) in {
    "PCB bare 30.4 x 38.4": (PCB_W, PCB_L),
    "PCB + 2mm/side": (PCB_W + 4, PCB_L + 4),
    "PCB rotated 38.4 x 30.4": (PCB_L, PCB_W),
    "pod 44 x 52 (w/ walls)": (44.0, 52.0),
    "pod 40 x 46": (40.0, 46.0),
    "pod 36 x 42": (36.0, 42.0),
}.items():
    md, cx, cz, _ = window_min_depth(w, h)
    need = BOARD_STACK_T + CLR
    surplus = md - need
    verdict = ("fits inside the mask, "
               f"{surplus:.1f} mm to spare") if surplus >= 0 else \
              f"pod must protrude {-surplus:.1f} mm past the wall plane"
    print(f"{label:>22}  {md:8.1f}   ({cx:6.1f}, {cz:6.1f})   {verdict}")

# ---------------------------------------------------------------- B. lens sites
print("\n=== B. candidate lens sites ===")


def probe_site(x, z, r=1.5, label=""):
    sel = (np.abs(xs[None, :] - x) <= r) & (np.abs(zs[:, None] - z) <= r) & solid
    if not sel.any():
        print(f"  {label:>24}: outside the silhouette / already open")
        return
    print(f"  {label:>24}: front stands off wall {-np.nanmedian(YF[sel]):5.1f} mm | "
          f"wall thickness {np.nanmedian(THICK[sel]):5.1f} mm | "
          f"cavity behind {np.nanmedian(DEPTH[sel]):5.1f} mm")


# eye centres: find the two deepest-protruding blobs in the eye band
band = (zs >= 33) & (zs <= 50)
front_off = -YF
sub = np.where(solid, front_off, -1e9)[band]
zb = zs[band]
for side, xsel in (("left eye", xs < -3), ("right eye", xs > 3)):
    cols = np.where(xsel)[0]
    s = sub[:, cols]
    i, j = np.unravel_index(np.argmax(s), s.shape)
    ex, ez = xs[cols[j]], zb[i]
    print(f"  {side:>24}: apex at x={ex:6.1f} z={ez:6.1f}  (stands off wall "
          f"{s[i, j]:.1f} mm)")
    probe_site(ex, ez, 1.5, f"  ^ {side} apex")

for label, (x, z) in {
    "between the eyes (nose)": (0.0, 40.0),
    "forehead jewel": (0.0, 57.0),
    "mouth centre": (0.0, 14.0),
    "left cheek rosette": (-24.0, 40.0),
}.items():
    probe_site(x, z, 2.0, label)

# ---------------------------------------------------------------- C. open holes
print("\n=== C. existing through-holes in the donor (rays that missed inside the outline) ===")
# a cell is "a hole" if it has no hit but is surrounded by solid within a few mm
from scipy import ndimage
filled = ndimage.binary_fill_holes(solid)
holes = filled & ~solid
lbl, nlab = ndimage.label(holes)
print(f"  {nlab} enclosed opening(s) in the front silhouette")
for i in range(1, nlab + 1):
    ii, jj = np.where(lbl == i)
    area = len(ii) * STEP * STEP
    if area < 1.0:
        continue
    print(f"    #{i}: {area:6.1f} mm^2   x[{xs[jj].min():6.1f}..{xs[jj].max():6.1f}]"
          f"  z[{zs[ii].min():6.1f}..{zs[ii].max():6.1f}]")
