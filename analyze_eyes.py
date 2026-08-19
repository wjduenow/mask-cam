"""Find the eyeball dome centres precisely, and check a lens bore fits in one.

The pupil is the one feature that has to land dead on: an off-centre hole reads as
damage, a centred one reads as a painted pupil.  So the centres are FOUND, not typed.

First attempt searched z 30..55 and latched onto the NOSTRILS (x=+/-5.4, z=31) -- they
are the sharpest local maxima on the muzzle.  The eyeballs are the two big smooth caps
higher up.  So: search only the eye band, only outboard of the nose, and fit a circle
to the cap rather than trusting a single apex pixel.
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from scipy import ndimage

d = np.load("pod.npz")
xs, zs, YF, STEP = d["xs"], d["zs"], d["YF"], float(d["STEP"])
solid = d["solid"]
S = np.where(solid, -YF, np.nan)

# The eye band, established by eye from eyes.png on the UNSCALED donor: two caps around
# (+/-10.5, 40).  It must follow MASK_SCALE -- left unscaled it lands on the muzzle and
# the detector locks onto the NOSTRILS, which is exactly what happened at 1.5x (it
# returned +/-5.80, 37.51 with a 3.5 mm cap, versus the eyeballs' 7 mm).
from mask_frame import MASK_SCALE
BAND_Z = (33.0 * MASK_SCALE, 48.0 * MASK_SCALE)
BAND_X = (4.5 * MASK_SCALE, 18.0 * MASK_SCALE)

print("=== eyeball domes ===")
eyes = {}
for name, sgn in (("left", -1), ("right", +1)):
    xi = (sgn * xs >= BAND_X[0]) & (sgn * xs <= BAND_X[1])
    zi = (zs >= BAND_Z[0]) & (zs <= BAND_Z[1])
    xb, zb = xs[xi], zs[zi]
    sub = S[np.ix_(zi, xi)]

    i, j = np.unravel_index(np.nanargmax(sub), sub.shape)
    apex = sub[i, j]

    # the cap: connected region within 2 mm of the apex.  A dome gives a round blob;
    # a ridge gives a long thin one, so print the aspect ratio as a sanity check.
    reg = np.nan_to_num(sub, nan=-1e3) >= apex - 2.0
    lbl, _ = ndimage.label(reg)
    cap = lbl == lbl[i, j]
    ii, jj = np.where(cap)
    x0, x1, z0, z1 = xb[jj].min(), xb[jj].max(), zb[ii].min(), zb[ii].max()
    # area-weighted centroid of the cap, weighted by how proud each cell is
    w = np.clip(sub[cap] - (apex - 2.0), 0, None)
    cx = float((xb[jj] * w).sum() / w.sum())
    cz = float((zb[ii] * w).sum() / w.sum())
    eyes[name] = (cx, cz, apex, x1 - x0, z1 - z0)
    print(f"  {name:5s}: apex ({xb[j]:6.2f},{zb[i]:6.2f}) stand-off {apex:5.2f} mm | "
          f"cap {x1-x0:5.2f} x {z1-z0:5.2f} mm (aspect {(x1-x0)/(z1-z0):4.2f}) | "
          f"centroid ({cx:6.2f},{cz:6.2f})")

lx, lz, la, lw, lh = eyes["left"]
rx, rz, ra, rw, rh = eyes["right"]
EX = (abs(lx) + abs(rx)) / 2
EZ = (lz + rz) / 2
DOME_D = min(lw, rw, lh, rh)
print(f"\n  symmetry: |x| {abs(lx):.2f} vs {abs(rx):.2f} "
      f"(delta {abs(abs(lx)-abs(rx)):.2f} mm) | z {lz:.2f} vs {rz:.2f} "
      f"(delta {abs(lz-rz):.2f} mm)")
print(f"  -> EYE_X = +/-{EX:.2f} mm, EYE_Z = {EZ:.2f} mm, "
      f"smallest cap dimension {DOME_D:.2f} mm")

# ---- how flat is the eyeball across a bore of each size?  A big sag means the bore
#      breaks the dome's silhouette and stops reading as a pupil.
print("\n=== bore feasibility on the eyeball ===")
for bore_d in (4.0, 5.0, 6.0, 6.5, 7.0, 8.0):
    r = bore_d / 2
    out = []
    for name, sgn in (("L", -1), ("R", +1)):
        cxx = sgn * EX
        sx = np.abs(xs - cxx) <= r
        sz = np.abs(zs - EZ) <= r
        sub = S[np.ix_(sz, sx)]
        out.append((np.nanmin(sub), np.nanmax(sub)))
    sag = max(b - a for a, b in out)
    frac = bore_d / DOME_D
    print(f"  d={bore_d:4.1f} mm: sag across the aperture {sag:5.2f} mm, "
          f"{100*frac:4.0f}% of the eyeball's width  "
          f"{'<- too big, eats the eyeball' if frac > 0.6 else ''}")

np.savez("eyes.npz", EYE_X=EX, EYE_Z=EZ, DOME_D=DOME_D)

# ---- picture
fig, ax = plt.subplots(figsize=(11, 12))
zi2 = (zs >= 0) & (zs <= 70)
xi2 = (xs >= -30) & (xs <= 30)
sub = S[np.ix_(zi2, xi2)]
ls = LightSource(azdeg=315, altdeg=40)
rgb = ls.shade(np.nan_to_num(sub, nan=float(np.nanmin(sub))),
               cmap=plt.get_cmap("bone"), vert_exag=3.0, blend_mode="soft")
rgb[np.isnan(sub)] = 1.0
ax.imshow(rgb, origin="lower",
          extent=(xs[xi2][0], xs[xi2][-1], zs[zi2][0], zs[zi2][-1]))
for sgn in (-1, 1):
    ax.add_patch(plt.Circle((sgn * EX, EZ), DOME_D / 2, fill=False,
                            color="deepskyblue", lw=1.4, ls="--"))
    ax.add_patch(plt.Circle((sgn * EX, EZ), 6.5 / 2, fill=False, color="red", lw=2))
    ax.plot([sgn * EX], [EZ], "r+", ms=10)
ax.set_xticks(np.arange(-30, 31, 2))
ax.set_yticks(np.arange(0, 71, 2))
ax.grid(True, lw=0.35, alpha=0.5, color="0.35")
ax.tick_params(labelsize=7)
ax.set_aspect("equal")
ax.set_title(f"Ø6.5 pupil bore (red) inside the eyeball cap (blue) "
             f"at x=±{EX:.1f}, z={EZ:.1f}")
fig.tight_layout()
fig.savefig("eyes.png", dpi=95)
print("\nwrote eyes.png + eyes.npz")
