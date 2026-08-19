"""Pick the bay outline from measured minima, not from a coarse table."""
import numpy as np
from measure import standoff_min_rect, standoff_min_disc
COVER_T, FRONT_WALL = 2.5, 3.0
BOARD_NEED = 10.51 + 1.0
def interior(x0,x1,z0,z1):
    s = standoff_min_rect(x0,x1,z0,z1)
    return s, s - FRONT_WALL - COVER_T
print("UPPER zone (must carry the board, needs %.2f mm):" % BOARD_NEED)
print(f"{'half-w':>7} {'z0':>5} {'z1':>5} {'standoff':>9} {'interior':>9}  verdict")
for hw in (15.0, 16.0, 17.0, 18.0):
    for z0,z1 in ((34,86),(36,86),(38,86),(34,84),(36,84),(40,84),(38,88)):
        s,i = interior(-hw,hw,z0,z1)
        print(f"{hw:7.1f} {z0:5.0f} {z1:5.0f} {s:9.2f} {i:9.2f}  "
              f"{'OK  +%.2f'%(i-BOARD_NEED) if i>=BOARD_NEED else 'short %.2f'%(BOARD_NEED-i)}")
print("\nLOWER zone (battery + USB-C breakout):")
for hw in (12.0, 13.0, 15.0, 17.0):
    for z0,z1 in ((20,34),(22,34),(24,34),(22,36),(24,38)):
        s,i = interior(-hw,hw,z0,z1)
        print(f"{hw:7.1f} {z0:5.0f} {z1:5.0f} {s:9.2f} {i:9.2f}")
print("\nBROW lens site, midline, by z:")
for z in (46,48,50,52,54,56,58):
    s_site = standoff_min_disc(0,z,1.0)
    s_pock = standoff_min_rect(-5.1,5.1,z-5.1,z+5.1)
    floor = -(s_pock-2.5)
    print(f"  z={z:3.0f}  site standoff {s_site:6.2f}  pocket standoff {s_pock:6.2f}  "
          f"floor {floor:7.2f}  lens can reach y={floor-5.0:7.2f}  "
          f"setback {s_site+floor-5.0:6.2f}")
