"""Marked-up front view: where each candidate lens site is, and what it costs."""
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
d = np.load("pod.npz")
xs, zs, YF, solid = d["xs"], d["zs"], d["YF"], d["solid"]
S = np.where(solid, -YF, np.nan)
zi = (zs >= 0) & (zs <= 72); xi = (xs >= -32) & (xs <= 32)
sub = S[np.ix_(zi, xi)]
ls = LightSource(azdeg=315, altdeg=40)
rgb = ls.shade(np.nan_to_num(sub, nan=float(np.nanmin(sub))),
               cmap=plt.get_cmap("bone"), vert_exag=3.0, blend_mode="soft")
rgb[np.isnan(sub)] = 1.0
fig, ax = plt.subplots(figsize=(10.5, 12))
ax.imshow(rgb, origin="lower", extent=(xs[xi][0], xs[xi][-1], zs[zi][0], zs[zi][-1]))
OPTS = [
    ("A", (11.39, 39.51), 7.2, "tab:red",    "EYE  Ø7.2 →  35°"),
    ("B", (11.39, 39.51), 9.0, "tab:orange", "EYE  Ø9.0 →  43°  (eyeball fully hollow)"),
    ("C", (0.0,   16.0),  7.2, "tab:green",  "MOUTH Ø7.2 → 150°"),
    ("D", (0.0,   50.0),  7.2, "tab:blue",   "BROW  Ø7.2 → 173°"),
    ("E", (5.4,   31.0),  6.0, "tab:purple", "NOSTRIL Ø6 → 133°"),
]
for tag,(cx,cz),dia,col,lab in OPTS:
    ax.add_patch(plt.Circle((cx,cz), dia/2, fill=False, color=col, lw=2.6))
    ax.annotate(f"{tag}", (cx,cz), color=col, fontsize=13, fontweight="bold",
                xytext=(cx+dia/2+1.5, cz+1.5))
# mirror the eye options onto the other eye (both get bored either way)
for dia,col in ((7.2,"tab:red"),):
    ax.add_patch(plt.Circle((-11.39,39.51), dia/2, fill=False, color=col, lw=1.4, ls=":"))
ax.set_xticks(np.arange(-32,33,4)); ax.set_yticks(np.arange(0,73,4))
ax.grid(True, lw=0.3, alpha=0.45, color="0.4"); ax.tick_params(labelsize=7)
ax.set_aspect("equal"); ax.set_xlabel("x (mm)"); ax.set_ylabel("z (mm)")
ax.set_title("candidate lens sites — circle is the ACTUAL hole size, at true scale", fontsize=12)
h=[plt.Line2D([],[],color=c,lw=2.6,label=f"{t}  {l}") for t,_,_,c,l in OPTS]
ax.legend(handles=h, loc="lower center", bbox_to_anchor=(0.5,-0.16), fontsize=10, ncol=1)
fig.tight_layout(); fig.savefig("sites.png", dpi=95)
print("wrote sites.png")
