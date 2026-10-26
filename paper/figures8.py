"""The attack against text injection, with the paper's current vocabulary."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

D = Path(__file__).resolve().parent
F = json.loads((D / "facts.json").read_text())
INK, INK2, MUTED, GRID = "#15171a", "#55585e", "#9a9ca1", "#e6e7ea"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({"figure.facecolor": "#fff", "axes.facecolor": "#fff", "savefig.facecolor": "#fff",
                     "font.family": "DejaVu Sans", "font.size": 8.4, "legend.frameon": False})
AG = ["open_2", "open_1", "anthropic_frontier"]
SHORT = {"open_2": "Qwen3-VL 8B", "open_1": "UI-TARS 7B", "anthropic_frontier": "Claude Opus 5.5"}
ROWS = [("copy", "The adversary's copy (this paper)"), ("plain", "Injection: plain instruction"),
        ("authority", "Injection: appeal to authority"), ("hidden", "Injection: hidden text")]
fig, ax = plt.subplots(figsize=(6.4, 2.9))
h = 0.24
for i, ag in enumerate(AG):
    col = [S1, S2, S3][i]
    for j, (key, _) in enumerate(ROWS):
        d = F["replica_on_injection_cells"].get(ag) if key == "copy" else F["injection"].get(f"{ag}|{key}")
        if not d: continue
        y = j + h - i * h
        ax.barh(y, d["rate"], h * 0.86, color=col, zorder=3)
        ax.text(d["rate"] + 0.012, y, f"{d['rate']:.0%}", va="center", fontsize=7.2, color=INK)
ax.set_yticks(range(len(ROWS))); ax.set_yticklabels([lab for _, lab in ROWS], fontsize=8)
ax.invert_yaxis(); ax.set_xlim(0, 1.08)
ax.set_xticks([0, .25, .5, .75, 1]); ax.set_xticklabels(["0", "25%", "50%", "75%", "100%"])
ax.set_xlabel("share of episodes in which the attack succeeded")
for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color(GRID); ax.tick_params(length=0)
ax.xaxis.grid(True, color=GRID, lw=0.7); ax.set_axisbelow(True)
ax.axhline(0.5, color=GRID, lw=0.9)
ax.legend(handles=[Line2D([], [], color=[S1, S2, S3][i], lw=5, label=SHORT[a]) for i, a in enumerate(AG)],
          loc="lower right", fontsize=7.6)
fig.savefig(D / "figures/23-vs-injection.png", dpi=235, bbox_inches="tight", pad_inches=0.05)
plt.close(fig); print("   23-vs-injection")
