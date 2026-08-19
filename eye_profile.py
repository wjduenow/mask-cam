"""Horizontal + vertical section through one eyeball, to find where the dome ends."""
import numpy as np
d = np.load("pod.npz"); e = np.load("eyes.npz")
xs, zs, YF = d["xs"], d["zs"], d["YF"]
S = np.where(d["solid"], -YF, np.nan)
EX, EZ = float(e["EYE_X"]), float(e["EYE_Z"])
iz = int(np.argmin(np.abs(zs - EZ)))
ix = int(np.argmin(np.abs(xs - (-EX))))
print(f"eye centre x=-{EX:.2f}  z={EZ:.2f}\n")
print("HORIZONTAL section (z = eye centre), stand-off vs x:")
for x in np.arange(-EX - 9, -EX + 9.01, 0.5):
    j = int(np.argmin(np.abs(xs - x)))
    v = S[iz, j]
    dx = x + EX
    bar = "#" * int(max(0, (v - 25)) * 2) if np.isfinite(v) else ""
    print(f"  dx={dx:+5.1f}  x={x:+6.1f}  {v:6.2f}  {bar}")
print("\nVERTICAL section (x = eye centre), stand-off vs z:")
for z in np.arange(EZ - 9, EZ + 9.01, 0.5):
    i = int(np.argmin(np.abs(zs - z)))
    v = S[i, ix]
    dz = z - EZ
    bar = "#" * int(max(0, (v - 25)) * 2) if np.isfinite(v) else ""
    print(f"  dz={dz:+5.1f}  z={z:+6.1f}  {v:6.2f}  {bar}")
