"""What charger + cell combination actually fits, if the lower bay is resized?

The user's architecture is right; the binding constraint is volume in the muzzle.  So:
enumerate real charger modules against real cell sizes and report which pairs fit, and
what runtime each buys.
"""
import numpy as np
from measure import standoff_min_rect
import mask_params as P

FW, CT = P.FRONT_WALL, P.COVER_T
DRAW_MA = 200.0        # ESP32-S3 streaming, WiFi + camera

CHARGERS = {                       # name: (w, h, thickness)
    "TP4056 USB-C, standard": (26.0, 17.0, 4.0),
    "TP4056 micro, no USB":   (17.0, 17.0, 3.5),
    "1S charger, mini":       (16.0, 11.0, 3.0),
}
CELLS = {                          # name: (w, h, t, mAh)
    "603048": (30.0, 48.0, 6.0, 1000),
    "503040": (30.0, 40.0, 5.0,  600),
    "502535": (25.0, 35.0, 5.0,  400),
    "402530": (25.0, 30.0, 4.0,  300),
    "402025": (20.0, 25.0, 4.0,  200),
    "401730": (17.0, 30.0, 4.0,  180),
}

# candidate lower-bay faces, widest-first
FACES = []
for w in (26, 28, 30, 32):
    for z0, z1 in ((12, 36), (14, 38), (14, 34), (16, 40), (12, 40), (10, 38)):
        s = standoff_min_rect(-w / 2, w / 2, z0, z1)
        if np.isfinite(s):
            FACES.append((w, z0, z1, s, s - FW - CT))

print(f"{'bay face':>14} {'z span':>12} {'depth':>7}   best charger + cell that fits")
print("-" * 92)
seen = set()
best_overall = None
for w, z0, z1, s, depth in sorted(FACES, key=lambda f: -(f[0] * (f[2] - f[1]))):
    h = z1 - z0
    if (w, h) in seen or depth < 5:
        continue
    seen.add((w, h))
    found = []
    for cn, (cw, ch, ct) in CHARGERS.items():
        for ln, (lw, lh, lt, mah) in CELLS.items():
            # side by side in the face, stacked in depth, 1.5 mm clearance all round
            side_by_side = (cw + lw + 3 <= w and max(ch, lh) + 3 <= h
                            and max(ct, lt) + 1.5 <= depth)
            stacked = (max(cw, lw) + 3 <= w and max(ch, lh) + 3 <= h
                       and ct + lt + 2.0 <= depth)
            if side_by_side or stacked:
                found.append((mah, cn, ln, "side-by-side" if side_by_side else "stacked"))
    if not found:
        print(f"{w:6.0f} x {h:<5.0f} {z0:5.0f}..{z1:<5.0f} {depth:7.2f}   —")
        continue
    found.sort(reverse=True)
    mah, cn, ln, how = found[0]
    hrs = mah / DRAW_MA
    print(f"{w:6.0f} x {h:<5.0f} {z0:5.0f}..{z1:<5.0f} {depth:7.2f}   "
          f"{cn} + {ln} ({mah} mAh, ~{hrs:.1f} h) {how}")
    if best_overall is None or mah > best_overall[0]:
        best_overall = (mah, w, h, z0, z1, depth, cn, ln, how, hrs)

print()
if best_overall:
    mah, w, h, z0, z1, depth, cn, ln, how, hrs = best_overall
    print(f"BEST: bay {w} x {h} x {depth:.2f} mm at z {z0}..{z1}")
    print(f"      {cn} + {ln} {how} -> {mah} mAh = ~{hrs:.1f} h of streaming")
