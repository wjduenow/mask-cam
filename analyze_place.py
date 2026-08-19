"""Best board placements, and the eye/mouth geometry, stated precisely.

The camera is on a SHORT FPC ribbon, so the board cannot go wherever it likes -- it has
to stay near the lens.  This ranks placements of the board footprint by the depth
available under it, and reports the distance from each to the candidate lens sites.
"""
import numpy as np

d = np.load("pod.npz")
xs, zs, YF, STEP = d["xs"], d["zs"], d["YF"], float(d["STEP"])
solid, outline, holes = d["solid"], d["outline"], d["holes"]

STANDOFF = np.where(solid, -YF, np.nan)
S = np.where(holes, np.inf, STANDOFF)
S = np.where(outline, S, -1e3)

PCB_W, PCB_L = 30.4, 38.4
CLR = 1.5                       # per side around the PCB inside the pocket


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


def field(w, h):
    kw, kh = int(round(w / STEP)), int(round(h / STEP))
    R = running_min(running_min(S, kh, 0), kw, 1)
    cx = xs[:R.shape[1]] + (kw - 1) * STEP / 2
    cz = zs[:R.shape[0]] + (kh - 1) * STEP / 2
    return R, cx, cz


LENS_SITES = {"left eye": (-10.0, 40.0), "right eye": (10.0, 40.0),
              "mouth": (0.0, 13.0), "forehead jewel": (0.0, 57.0)}

for label, (w, h) in {
    "board upright  33.4 x 41.4": (PCB_W + 2 * CLR, PCB_L + 2 * CLR),
    "board sideways 41.4 x 33.4": (PCB_L + 2 * CLR, PCB_W + 2 * CLR),
}.items():
    R, cx, cz = field(w, h)
    print(f"\n=== {label} — min front stand-off under the footprint ===")
    print(f"{'centre (x,z)':>16}  {'stand-off':>9}   nearest lens site")
    flat = R.ravel()
    order = np.argsort(flat)[::-1]
    shown, seen = 0, []
    for k in order:
        i, j = np.unravel_index(k, R.shape)
        x0, z0 = cx[j], cz[i]
        if any(abs(x0 - a) < 8 and abs(z0 - b) < 8 for a, b in seen):
            continue
        seen.append((x0, z0))
        dists = {n: np.hypot(x0 - p[0], z0 - p[1]) for n, p in LENS_SITES.items()}
        near = min(dists, key=dists.get)
        print(f"  ({x0:6.1f},{z0:6.1f})  {R[i, j]:8.1f}   "
              + "  ".join(f"{n} {v:4.0f}mm" for n, v in dists.items()))
        shown += 1
        if shown >= 6:
            break

# ---------------------------------------------------------------- eye geometry
print("\n=== eye domes, measured ===")
for name, (ex, ez) in (("left eye", (-10.0, 40.0)), ("right eye", (10.0, 40.0))):
    sel_x = (xs > ex - 10) & (xs < ex + 10)
    sel_z = (zs > ez - 10) & (zs < ez + 10)
    sub = STANDOFF[np.ix_(sel_z, sel_x)]
    sx, sz = xs[sel_x], zs[sel_z]
    i, j = np.unravel_index(np.nanargmax(sub), sub.shape)
    apex = sub[i, j]
    # dome footprint = contiguous cells within 4 mm of the apex
    near = sub >= apex - 4.0
    ii, jj = np.where(near)
    print(f"  {name}: apex ({sx[j]:6.1f},{sz[i]:5.1f}) stand-off {apex:5.1f} mm; "
          f"dome spans x[{sx[jj].min():6.1f}..{sx[jj].max():6.1f}] "
          f"z[{sz[ii].min():5.1f}..{sz[ii].max():5.1f}]  "
          f"-> {sx[jj].max()-sx[jj].min():.1f} x {sz[ii].max()-sz[ii].min():.1f} mm")

print("\n=== how thick is the wall we must bore through at each lens site? ===")
YB = d["YB"]
for name, (px, pz) in LENS_SITES.items():
    sx = (np.abs(xs - px) <= 2.0)
    sz = (np.abs(zs - pz) <= 2.0)
    sub_f = STANDOFF[np.ix_(sz, sx)]
    sub_t = (YB - YF)[np.ix_(sz, sx)]
    print(f"  {name:16s}: stand-off {np.nanmedian(sub_f):5.1f} mm, "
          f"solid wall {np.nanmedian(sub_t):5.1f} mm "
          f"-> after carving to a 3 mm front wall, the lens can sit "
          f"{np.nanmedian(sub_f) - 3:5.1f} mm behind the outer surface")
