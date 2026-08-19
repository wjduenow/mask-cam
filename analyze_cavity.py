"""Can the ESP32-S3-CAM actually live behind this mask's face?

Measures, in the canonical frame (see mask_frame.py):

  1. The rear cavity: for every (x, z), how far forward (-Y) the back surface sits.
     `-Y_back` is the usable pocket depth at that point, measured from the wall plane.
  2. The largest axis-aligned rectangle in (x, z) over which the cavity is at least
     D mm deep -- i.e. where a board of thickness D could sit flat against the wall
     plane.  Run for the board's real stack thickness.
  3. Local wall thickness at the candidate lens sites (eyes, mouth, forehead jewel),
     because the lens has to punch through that wall.
  4. Existing through-holes in the donor (the mouth already has some).

Writes cavity.png + cavity.npz and prints the fit verdict.
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mask_frame import load_mask

STEP = 0.5          # sampling pitch, mm

# ---- what has to fit (from ../sonos-nest/hardware/cam-button/shell/button_params.py)
PCB_W, PCB_L = 30.4, 38.4      # X, and the board's long axis
BOARD_STACK_T = 14.5           # tip-to-tip incl. the pre-soldered header pins

m = load_mask()
lo, hi = m.bounds
print(f"mask bounds min={lo.round(2)} max={hi.round(2)}")

xs = np.arange(lo[0] + STEP / 2, hi[0], STEP)
zs = np.arange(lo[2] + STEP / 2, hi[2], STEP)
XX, ZZ = np.meshgrid(xs, zs)

# Cast from well behind the wall plane, forward (-Y), so the FIRST hit is the back
# surface and the LAST hit is the front surface.
origins = np.column_stack([XX.ravel(), np.full(XX.size, 50.0), ZZ.ravel()])
dirs = np.tile([0.0, -1.0, 0.0], (len(origins), 1))
print(f"casting {len(origins)} rays ...")
locs, idx_ray, _ = m.ray.intersects_location(
    ray_origins=origins, ray_directions=dirs, multiple_hits=True)
print(f"{len(locs)} hits")

n = len(origins)
y_back = np.full(n, np.nan)     # first surface met coming from the wall  (max y)
y_front = np.full(n, np.nan)    # last surface met                        (min y)
n_cross = np.zeros(n, dtype=int)
o = np.argsort(idx_ray, kind="stable")
ri, yv = idx_ray[o], locs[o, 1]
bounds_i = np.searchsorted(ri, np.arange(n + 1))
for r in range(n):
    a, b = bounds_i[r], bounds_i[r + 1]
    if b > a:
        seg = yv[a:b]
        y_back[r] = seg.max()
        y_front[r] = seg.min()
        n_cross[r] = b - a

sh = XX.shape
YB = y_back.reshape(sh)      # <= 0 ; the rear surface
YF = y_front.reshape(sh)     # <= 0 ; the visible front surface
NC = n_cross.reshape(sh)
DEPTH = -YB                  # usable pocket depth from the wall plane, mm
THICK = YB - YF              # material thickness along Y at this (x,z)

solid = ~np.isnan(YB)
print(f"\nsilhouette cells: {solid.sum()} of {solid.size}")
print(f"cavity depth   max={np.nanmax(DEPTH):.2f}  median(where solid)="
      f"{np.nanmedian(DEPTH[solid]):.2f}")
print(f"wall thickness min={np.nanmin(THICK[solid]):.2f} "
      f"median={np.nanmedian(THICK[solid]):.2f} max={np.nanmax(THICK[solid]):.2f}")
print(f"crossing counts: {sorted(set(NC[solid].tolist()))}")


def largest_rect(mask_ok):
    """Largest axis-aligned all-True rectangle in a boolean grid -> (r0,r1,c0,c1)."""
    best = (0, None)
    h = np.zeros(mask_ok.shape[1], dtype=int)
    for r in range(mask_ok.shape[0]):
        h = np.where(mask_ok[r], h + 1, 0)
        stack = []           # (start_col, height)
        for c in range(len(h) + 1):
            cur = h[c] if c < len(h) else 0
            start = c
            while stack and stack[-1][1] >= cur:
                s, ht = stack.pop()
                area = ht * (c - s)
                if area > best[0]:
                    best = (area, (r - ht + 1, r, s, c - 1))
                start = s
            if cur:
                stack.append((start, cur))
    return best[1]


print(f"\n--- where can a {BOARD_STACK_T} mm stack sit flat against the wall plane? ---")
for need in (BOARD_STACK_T, BOARD_STACK_T + 2.0, 20.0, 25.0):
    ok = solid & (DEPTH >= need)
    rect = largest_rect(ok)
    if rect is None:
        print(f"  depth >= {need:5.1f} mm : nothing")
        continue
    r0, r1, c0, c1 = rect
    w = (c1 - c0 + 1) * STEP
    h = (r1 - r0 + 1) * STEP
    print(f"  depth >= {need:5.1f} mm : largest clear rect {w:5.1f} x {h:5.1f} mm "
          f"at x[{xs[c0]:7.1f} .. {xs[c1]:7.1f}]  z[{zs[r0]:6.1f} .. {zs[r1]:6.1f}]"
          f"   {'FITS ' + str(PCB_W) + 'x' + str(PCB_L) if (w >= PCB_W and h >= PCB_L) or (h >= PCB_W and w >= PCB_L) else ''}")

np.savez("cavity.npz", xs=xs, zs=zs, YB=YB, YF=YF, NC=NC, STEP=STEP)

fig, ax = plt.subplots(1, 4, figsize=(24, 8))
ext = [xs[0], xs[-1], zs[0], zs[-1]]
for a, data, title, kw in [
    (ax[0], -YF, "front relief: how far it stands off the wall (mm)", {}),
    (ax[1], DEPTH, "rear cavity depth from wall plane (mm)", {}),
    (ax[2], THICK, "wall thickness along Y (mm)", {"vmax": 20}),
    (ax[3], (DEPTH >= BOARD_STACK_T).astype(float),
     f"depth >= {BOARD_STACK_T} mm (board stack)", {}),
]:
    im = a.imshow(data, origin="lower", extent=ext, cmap="magma", **kw)
    a.set_title(title, fontsize=10)
    a.set_aspect("equal")
    plt.colorbar(im, ax=a, shrink=0.7)
fig.tight_layout()
fig.savefig("cavity.png", dpi=95)
print("\nwrote cavity.png + cavity.npz")
