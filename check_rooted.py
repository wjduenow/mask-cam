"""Is every added pillar actually standing on mask material, or floating in the cavity?

The bay floor is a PLANE at the worst-case depth, but the donor's rear surface is a
dish: over much of the bay it is already deeper than that plane.  Anything based on the
plane there -- a boss, a post, the tube wall -- has nothing under it.  The boolean still
yields one watertight body (everything touches somewhere) but the part would print as
unsupported spindles.
"""
import numpy as np
import mask_params as P

d = np.load("pod.npz")
xs, zs, YB, solid = d["xs"], d["zs"], d["YB"], d["solid"]
DEPTH = np.where(solid, -YB, np.nan)      # how far the REAR surface is from the wall

def depth_at(cx, cz, r):
    sx = np.abs(xs-cx) <= r; sz = np.abs(zs-cz) <= r
    sub = DEPTH[np.ix_(sz,sx)]; sub = sub[np.isfinite(sub)]
    return (float(sub.min()), float(sub.max())) if sub.size else (np.nan, np.nan)

print("A pillar based at y = FLOOR is rooted only where the rear surface depth <= |FLOOR|.\n")
print(f"upper floor |y| = {-P.FLOOR_Y_UP:.2f}   lower floor |y| = {-P.FLOOR_Y_LO:.2f}\n")
print("board bosses (need depth <= 16.23):")
for sx in (-1,1):
    for sz in (-1,1):
        x,z = sx*P.HOLE_DX/2, P.BOARD_CZ+sz*P.HOLE_DY/2
        lo,hi = depth_at(x,z,P.BOSS_OD/2)
        print(f"  ({x:+6.1f},{z:5.1f}) rear depth {lo:6.2f}..{hi:6.2f}  "
              f"{'ROOTED' if hi<= -P.FLOOR_Y_UP else 'FLOATS by %.2f'%(hi+P.FLOOR_Y_UP)}")
print("\ncover posts:")
for x,z in P.POST_XY:
    f = P.FLOOR_Y_UP if z>=P.BAY_Z0_UP else P.FLOOR_Y_LO
    lo,hi = depth_at(x,z,P.POST_OD/2)
    print(f"  ({x:+6.1f},{z:5.1f}) rear depth {lo:6.2f}..{hi:6.2f}  vs |floor| {-f:6.2f}  "
          f"{'ROOTED' if hi<=-f else 'FLOATS by %.2f'%(hi+f)}")
print("\nbay tube perimeter (upper zone, wall centreline):")
hw = P.BAY_HW_UP + P.BAY_WALL/2
pts = ([(sx*hw, z) for sx in (-1,1) for z in np.arange(P.BAY_Z0_UP, P.BAY_Z1_UP+1, 8)]
       + [(x, P.BAY_Z1_UP+P.BAY_WALL/2) for x in np.arange(-hw, hw+1, 8)])
bad = 0
for x,z in pts:
    lo,hi = depth_at(x,z,1.0)
    if not np.isfinite(hi): print(f"  ({x:+6.1f},{z:5.1f}) OFF MASK"); bad+=1; continue
    ok = hi <= -P.FLOOR_Y_UP
    if not ok: bad += 1
    print(f"  ({x:+6.1f},{z:5.1f}) rear depth {hi:6.2f}  {'rooted' if ok else 'FLOATS by %.2f'%(hi+P.FLOOR_Y_UP)}")
print(f"\n{bad} of {len(pts)} perimeter samples unsupported")
