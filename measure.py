"""Queries against the sampled front surface, so geometry numbers are DERIVED not typed.

pod.npz holds a 0.5 mm grid of the mask's front surface stand-off (-y).  Everything that
asks "how deep may I cut here without breaking the relief" goes through this module, so
there is exactly one answer and mask_params.py cannot drift from build_mask.py.
"""
import numpy as np

_G = None


def grid():
    global _G
    if _G is None:
        d = np.load("pod.npz")
        S = np.where(d["solid"], -d["YF"], np.nan)
        # gaps inside the outline (tooth slots, petal slots) constrain nothing
        S = np.where(d["holes"], np.inf, S)
        _G = (d["xs"], d["zs"], S, d["outline"])
    return _G


def standoff_min_rect(x0, x1, z0, z1):
    """Worst (smallest) front stand-off anywhere in an axis-aligned window."""
    xs, zs, S, _ = grid()
    sx = (xs >= x0) & (xs <= x1)
    sz = (zs >= z0) & (zs <= z1)
    sub = S[np.ix_(sz, sx)]
    sub = sub[np.isfinite(sub)]
    if sub.size == 0:
        return float("nan")
    return float(sub.min())


def standoff_min_disc(cx, cz, r):
    xs, zs, S, _ = grid()
    sx = np.abs(xs - cx) <= r
    sz = np.abs(zs - cz) <= r
    X, Z = np.meshgrid(xs[sx], zs[sz])
    sub = S[np.ix_(sz, sx)]
    sub = np.where((X - cx) ** 2 + (Z - cz) ** 2 <= r * r, sub, np.inf)
    sub = sub[np.isfinite(sub)]
    return float(sub.min()) if sub.size else float("nan")


def deepest_floor(x0, x1, z0, z1, wall):
    """The most forward y a flat pocket floor may reach over a window."""
    return -(standoff_min_rect(x0, x1, z0, z1) - wall)


def rear_depth_max(cx, cz, r):
    """Worst-case distance from the wall plane to the donor's REAR surface over a disc.

    This is what decides whether an added pillar is standing on anything.  The bay floor
    is a plane at the worst case over the whole zone, but the donor's back is a dish, so
    over most of the bay the rear surface is already DEEPER than that plane and a pillar
    based on it has nothing underneath.
    """
    d = _load()
    xs, zs, YB, solid = d["xs"], d["zs"], d["YB"], d["solid"]
    depth = np.where(solid, -YB, np.nan)
    sx = np.abs(xs - cx) <= r
    sz = np.abs(zs - cz) <= r
    sub = depth[np.ix_(sz, sx)]
    sub = sub[np.isfinite(sub)]
    return float(sub.max()) if sub.size else float("nan")


def root_y(cx, cz, r, _wall=None):
    """How far FORWARD a pillar at (cx, cz) must run to stand on solid material.

    That is the donor's REAR surface -- NOT the front-wall cut limit.  The two are
    different constraints and confusing them is easy: the cut limit governs how deep a
    POCKET may go before it breaks the relief; a pillar only ADDS material, so it can
    safely run forward until it lands on the back of the mask, however thin the skin
    there happens to be.  Using the cut limit here rejected the two upper cover posts,
    where the crown is a 1 mm shell -- they root perfectly well on its back face.
    """
    return -rear_depth_max(cx, cz, r)


_RAW = None


def _load():
    global _RAW
    if _RAW is None:
        _RAW = np.load("pod.npz")
    return _RAW


def best_pocket(cx, cz, w, h, wall, search=8.0, step=0.5):
    """Slide a w x h pocket around (cx, cz) and return the placement that reaches
    furthest forward.  The camera module does not have to be centred on the eye --
    only its lens barrel does -- so letting the body drift toward the deeper brow
    buys real depth.  Returns (floor_y, offset_x, offset_z, standoff)."""
    best = None
    for dx in np.arange(-search, search + 1e-9, step):
        for dz in np.arange(-search, search + 1e-9, step):
            s = standoff_min_rect(cx + dx - w / 2, cx + dx + w / 2,
                                  cz + dz - h / 2, cz + dz + h / 2)
            if not np.isfinite(s):
                continue
            if best is None or s > best[3]:
                best = (-(s - wall), float(dx), float(dz), s)
    return best


if __name__ == "__main__":
    print("stand-off over a square centred on the eye, by side length:")
    for s in (7.0, 8.0, 9.0, 10.0, 11.0, 12.0):
        v = standoff_min_rect(11.39 - s / 2, 11.39 + s / 2, 39.51 - s / 2, 39.51 + s / 2)
        print(f"  {s:5.1f} mm square: worst stand-off {v:6.2f} mm "
              f"-> pocket may reach y = {-(v - 2.5):7.2f}")
    print("\nbest OFFSET placement of a 10.2 x 10.2 pocket near the eye:")
    b = best_pocket(11.39, 39.51, 10.2, 10.2, 2.5)
    print(f"  floor {b[0]:.2f}  offset ({b[1]:+.1f},{b[2]:+.1f})  stand-off {b[3]:.2f}")
    for w, h in ((10.2, 10.2), (9.6, 9.6), (11.0, 9.0), (9.0, 11.0), (12.0, 9.0)):
        b = best_pocket(11.39, 39.51, w, h, 2.5)
        print(f"  {w:4.1f} x {h:4.1f}: floor {b[0]:7.2f}  "
              f"offset ({b[1]:+5.1f},{b[2]:+5.1f})  stand-off {b[3]:6.2f}")
