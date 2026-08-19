"""How wide a view does each candidate lens site actually give?

The lens sits at the front of its pocket; the pupil is the aperture.  So

    setback  = front stand-off at the site  -  (pocket floor + barrel length)
    half FOV = atan( (pupil/2) / setback )

and the pocket floor is limited by how much relief surrounds the site.  This measures
that limit for a real module footprint at every site, instead of assuming.
"""
import numpy as np
from measure import standoff_min_rect, standoff_min_disc

CAM_BODY = 9.0 + 2*0.6      # pocket side for a 9.0 mm module
BARREL_L = 5.0
WALL = 2.5

SITES = {
    "right eye":      (11.39, 39.51),
    "left eye":       (-11.39, 39.51),
    "right nostril":  (5.4, 31.0),
    "mouth centre":   (0.0, 13.0),
    "mouth upper":    (0.0, 16.0),
    "forehead jewel": (0.0, 57.0),
    "nose bridge":    (0.0, 45.0),
    "brow centre":    (0.0, 50.0),
}
print(f"pocket {CAM_BODY:.1f} mm square, {WALL} mm wall, {BARREL_L} mm barrel\n")
print(f"{'site':16s} {'standoff':>8} {'pocket':>8} {'lens y':>8} {'setback':>8}   FOV at pupil Ø...")
print(f"{'':16s} {'':>8} {'floor':>8} {'':>8} {'':>8}   " + "  ".join(f"{d:4.1f}" for d in (6,7.2,9,11,14)))
print("-"*100)
for name,(cx,cz) in SITES.items():
    s_site = standoff_min_disc(cx, cz, 1.0)
    s_pock = standoff_min_rect(cx-CAM_BODY/2, cx+CAM_BODY/2, cz-CAM_BODY/2, cz+CAM_BODY/2)
    if not np.isfinite(s_pock):
        print(f"{name:16s}   -- pocket runs off the mask --"); continue
    floor = -(s_pock - WALL)
    lens  = floor - BARREL_L
    setback = s_site + lens
    fovs = []
    for d in (6,7.2,9,11,14):
        fovs.append(f"{2*np.degrees(np.arctan((d/2)/setback)):4.0f}°" if setback>0.2 else "  ∞ ")
    print(f"{name:16s} {s_site:8.2f} {floor:8.2f} {lens:8.2f} {setback:8.2f}   " + "  ".join(fovs))
