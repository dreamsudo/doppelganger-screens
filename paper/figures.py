#!/usr/bin/env python3
"""Regenerate the paper's data figures from the record.

Run from the repository root, after paper/facts.py has written paper/facts.json:

    python3 paper/facts.py
    python3 paper/figures.py
    python3 paper/figures8.py        # the injection comparison

Every figure here derives from results/ under the registered utility floor (the genuine-prompt-only
runs in results/E0/utility-floor-*). Two figures, first-clicks.png and first-action.png, are carried
as artefacts of the original run and are not regenerated.
"""
from __future__ import annotations

import collections
import glob
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import gridspec  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "paper" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
SHOTS = ROOT / "results" / "E1" / "paired" / "shots"
NO_DATA = ("parse_failures", "timeout", "crash", "error", "refusal")

F = json.loads((ROOT / "paper" / "facts.json").read_text(encoding="utf-8"))
NAME = F["agent_names"]
AG = ["open_2", "open_1", "anthropic_frontier"]
SHORT = {"open_2": "Qwen3-VL", "open_1": "UI-TARS", "anthropic_frontier": "Claude"}
COL = {"open_2": "#1b9e77", "open_1": "#e2622f", "anthropic_frontier": "#2e6fd6"}
GEN, CPY = "#2e6fd6", "#e2622f"
SURF = {"browser-l1": "inline", "browser-l2": "framed"}
ACTN = {"CONF": "payment", "PERM": "permission", "UPDT": "update", "CRED": "credential"}


# ----------------------------------------------------------------------------- record
def registered_floor() -> set:
    """Act cells each agent cleared in the dedicated floor run: genuine prompt only, no copy on screen."""
    reg = collections.defaultdict(lambda: [0, 0])
    for f in glob.glob(str(ROOT / "results" / "E0" / "utility-floor-*" / "episodes.jsonl")):
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            k = (r["agent"], r["cell"], r["act"])
            reg[k][0] += 1 if r.get("n_events_matching", 0) > 0 else 0
            reg[k][1] += 1
    return {k for k, (a, n) in reg.items() if n and a / n >= 0.70}


CLEARS = registered_floor()
ROWS = [json.loads(l) for l in (ROOT / "results" / "E1" / "paired" / "episodes.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
OK = [r for r in ROWS if r["stop"] not in NO_DATA]
PX = [r for r in OK if r["observation"] == "pixels" and r["cell"].startswith("browser") and (r["agent"], r["cell"], r["act"]) in CLEARS]


def pairs(obs="pixels"):
    d = {}
    for r in ROWS:
        if r["observation"] != obs or not r["steps"]:
            continue
        d.setdefault((r["agent"], r["cell"], r["act"], r["context"], r["sanitiser"], r["rep"]), {})[r["condition"]] = r
    return {k: v for k, v in d.items() if len(v) == 2}


def navigated_first(r) -> bool:
    """The first click landed outside the prompt box."""
    b = r.get("prompt", {}).get("box")
    st = r["steps"][0].get("action", {}) if r["steps"] else {}
    if not b or st.get("type") != "click" or st.get("x") is None:
        return False
    return not (b[0] <= st["x"] <= b[0] + b[2] and b[1] <= st["y"] <= b[1] + b[3])


def pad_aspect(path: Path, target: float) -> None:
    """Pad with white to a height/width ratio so the page layout does not depend on the plot's own proportions."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    need = int(round(w * target))
    if need > h:
        canvas = Image.new("RGB", (w, need), "white")
        canvas.paste(im, (0, (need - h) // 2))
        canvas.save(path)


def clean_axes(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color("#bbb")
    ax.spines["bottom"].set_color("#bbb")
    ax.grid(axis="y", color="#eee", lw=0.8)
    ax.set_axisbelow(True)


# ----------------------------------------------------------------------------- figures
def fig_headline():
    """Fig. 6: acts on the genuine prompt and on the copy, screenshots only, browser surfaces."""
    B = F["browser_only"]["pixels"]
    fig, ax = plt.subplots(figsize=(9.6, 5.0), dpi=140)
    w = 0.33
    for i, ag in enumerate(AG):
        g, c = B[ag]["genuine"], B[ag]["replica"]
        gr, cr = 100 * g["k"] / g["n"], 100 * c["k"] / c["n"]
        glo, ghi = [100 * x for x in g["ci"]]
        clo, chi = [100 * x for x in c["ci"]]
        ax.bar(i - w / 2, gr, w, color=GEN)
        ax.bar(i + w / 2, cr, w, color=CPY)
        ax.errorbar(i - w / 2, gr, yerr=[[gr - glo], [ghi - gr]], fmt="none", ecolor="#111", capsize=4, lw=1.2)
        ax.errorbar(i + w / 2, cr, yerr=[[cr - clo], [chi - cr]], fmt="none", ecolor="#111", capsize=4, lw=1.2)
        ax.text(i - w / 2, ghi + 3, f"{gr:.0f}%", ha="center", fontsize=13, weight="bold")
        ax.text(i - w / 2, ghi - 0.5, f"{g['k']}/{g['n']}", ha="center", fontsize=9.5, color="#666", va="bottom")
        ax.text(i + w / 2, chi + 3, f"{cr:.0f}%", ha="center", fontsize=13, weight="bold")
        ax.text(i + w / 2, chi - 0.5, f"{c['k']}/{c['n']}", ha="center", fontsize=9.5, color="#666", va="bottom")
    ax.set_xticks(range(3))
    ax.set_xticklabels([NAME[a] for a in AG], fontsize=13)
    ax.set_ylim(0, 120)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(["0", "25%", "50%", "75%", "100%"], fontsize=11)
    ax.set_ylabel("episodes in which the agent\nperformed the authority act", fontsize=12)
    clean_axes(ax)
    ax.legend(handles=[Patch(color=GEN, label="the application's own prompt"), Patch(color=CPY, label="the adversary's copy")],
              loc="upper center", bbox_to_anchor=(0.5, 1.13), ncol=2, frameon=False, fontsize=12)
    fig.tight_layout()
    p = OUT / "headline-browser.png"
    fig.savefig(p, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    pad_aspect(p, 0.486)


def _pick(cell, act, obs="pixels"):
    for k, v in pairs(obs).items():
        if k[1] == cell and k[2] == act:
            return SHOTS / v["genuine"]["steps"][0]["shot"], SHOTS / v["replica"]["steps"][0]["shot"]
    raise RuntimeError(f"no pair for {cell} {act}")


def fig_twins():
    """Fig. 4: the inline pair and the chat pair, side by side."""
    rows = [("inline", _pick("browser-l1", "CRED")), ("chat", _pick("chat-l1-web", "PERM"))]
    fig = plt.figure(figsize=(16.5, 10.2), dpi=100)
    gs = gridspec.GridSpec(2, 2, hspace=0.16, wspace=0.04, left=0.012, right=0.988, top=0.918, bottom=0.048)
    fig.text(0.5, 0.963, "Two surfaces, the same pairing: the application's own prompt on the left, the adversary's copy on the right.",
             ha="center", fontsize=14, color="#333")
    for row, (lab, (ga, rb)) in enumerate(rows):
        A = np.asarray(Image.open(ga).convert("RGB")).astype(np.int16)
        B = np.asarray(Image.open(rb).convert("RGB")).astype(np.int16)
        n = int((np.abs(A - B).max(axis=2) > 0).sum())
        pct = 100 * n / A[:, :, 0].size
        note = "identical: 0 of 1,064,960 pixels differ" if n == 0 else f"not alike: {pct:.0f} percent of the frame differs"
        for col, (img, who) in enumerate([(A, "the application's own prompt"), (B, "the adversary's copy")]):
            ax = fig.add_subplot(gs[row, col])
            ax.imshow(img.astype(np.uint8))
            ax.set_xticks([]); ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_color("#ccc")
            ttl = f"{lab} — {who}" if col == 0 else f"{lab} — {who}   ·   {note}"
            ax.set_title(ttl, fontsize=12, color=("#333" if col == 0 else "#b4532a"), pad=6, loc="left")
    fig.text(0.5, 0.013, "Inline is how the webmail and chat clients we measured render message bodies.  On chat the adversary can only post a link, so the two are not alike and those episodes are reported separately.",
             ha="center", fontsize=10.5, color="#666")
    fig.savefig(OUT / "twins-pairs.png", facecolor="white")
    plt.close(fig)


def fig_eps():
    """Fig. 5: the inline and framed pairs with every differing pixel amplified."""
    rows = [("inline (L1)", _pick("browser-l1", "PERM")), ("framed (L2)", _pick("browser-l2", "PERM"))]
    fig = plt.figure(figsize=(16.5, 9.0), dpi=100)
    gs = gridspec.GridSpec(2, 3, hspace=0.14, wspace=0.05, left=0.012, right=0.952, top=0.930, bottom=0.050)
    fig.text(0.5, 0.974, "What the agent is asked to tell apart.  Right column: every differing pixel, amplified so a one level difference is fully visible.",
             ha="center", fontsize=13, color="#444")
    for row, (lab, (ga, rb)) in enumerate(rows):
        A = np.asarray(Image.open(ga).convert("RGB")).astype(np.int16)
        B = np.asarray(Image.open(rb).convert("RGB")).astype(np.int16)
        dl = np.abs(A - B).max(axis=2)
        n, tot = int((dl > 0).sum()), dl.size
        for col, (img, ttl) in enumerate([(A, f"{lab}: the application's own prompt"), (B, f"{lab}: the adversary's copy")]):
            ax = fig.add_subplot(gs[row, col])
            ax.imshow(img.astype(np.uint8))
            ax.set_xticks([]); ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_color("#ccc")
            ax.set_title(ttl, fontsize=11.5, color="#333", pad=5, loc="left")
        ax = fig.add_subplot(gs[row, 2])
        im = ax.imshow(np.clip(dl, 0, 4), cmap="inferno", vmin=0, vmax=4)
        ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_color("#ccc")
        ax.set_title(f"difference: 0 of {tot:,} differ" if n == 0 else f"difference: {n:,} of {tot:,} differ, median 1 level",
                     fontsize=11.5, color="#b4532a", pad=5, loc="left")
        cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.012, ticks=[0, 1, 2, 3, 4])
        cb.ax.set_yticklabels(["0", "1", "2", "3", "4+"])
        cb.ax.tick_params(labelsize=8.5)
    fig.text(0.5, 0.013, "Inline, the surface webmail, chat and ticketing use: the two frames are one image.   Framed: every difference lies inside the dialog and its shadow.",
             ha="center", fontsize=10.5, color="#666")
    fig.savefig(OUT / "eps-pairs.png", facecolor="white")
    plt.close(fig)


def _cells():
    C = collections.defaultdict(lambda: {"g": 0, "c": 0, "cn": 0, "n": 0})
    for r in PX:
        k = (r["agent"], r["cell"], r["act"])
        if r["condition"] == "genuine":
            C[k]["g"] += r["y"]; C[k]["n"] += 1
        else:
            C[k]["c"] += r["y"]; C[k]["cn"] += navigated_first(r)
    return C


def fig_gapnav():
    """Fig. 7: the copy's deficit against first-click navigation, every act cell."""
    C = _cells()
    groups = collections.defaultdict(list)
    for k, v in C.items():
        groups[(v["cn"], v["g"] - v["c"])].append(k)
    fig, ax = plt.subplots(figsize=(5.4, 4.3), dpi=170)
    ax.plot([-1, 13], [-1, 13], color="#bbb", lw=1, ls="--", zorder=1)
    for (x, gap), ks in sorted(groups.items()):
        for i, k in enumerate(ks):
            ax.scatter(x + i * 0.22, gap, s=100, color=COL[k[0]], zorder=3, edgecolor="white", lw=1.1)
        if (x, gap) == (0, 0):
            ax.annotate(f"{len(ks)} cells", (0, 0), textcoords="offset points", xytext=(9, -13), fontsize=8, color="#555")
            continue
        if len(ks) > 1 and len({k[0] for k in ks}) == 1 and len({k[2] for k in ks}) == 1:
            lab = f"{SHORT[ks[0][0]]} {ACTN[ks[0][2]]}, inline and framed"
        else:
            lab = "; ".join(f"{SHORT[k[0]]} {SURF[k[1]]} {ACTN[k[2]]}" for k in ks)
        off = (8, -4)
        if ks[0][0] == "open_1" and ks[0][2] == "UPDT":
            off = (8, 6)
        if ks[0][2] == "CRED" and ks[0][1] == "browser-l1":
            off = (8, -12)
        ax.annotate(lab, (x + (len(ks) - 1) * 0.22, gap), textcoords="offset points", xytext=off, fontsize=8, color="#333")
    ax.set_xlim(-0.8, 12); ax.set_ylim(-6.5, 7)
    ax.set_xlabel("copy episodes whose first click left the prompt", fontsize=9.5)
    ax.set_ylabel("gap: genuine acts minus copy acts", fontsize=9.5)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(color="#eee", lw=0.8); ax.set_axisbelow(True)
    ax.text(6.9, 6.2, "gap = navigation", ha="right", fontsize=8, color="#888", rotation=38)
    fig.tight_layout()
    fig.savefig(OUT / "gap-navigation.png", facecolor="white", bbox_inches="tight")
    plt.close(fig)


def fig_acts():
    """Fig. 8: copy rate by authority act, with counts."""
    acts = [("CONF", "payment"), ("PERM", "permission"), ("UPDT", "update"), ("CRED", "credential")]
    M = np.full((3, 4), np.nan); K = {}
    for i, ag in enumerate(AG):
        for j, (a, _) in enumerate(acts):
            s = [r for r in PX if r["agent"] == ag and r["act"] == a and r["condition"] == "replica"]
            if s:
                M[i, j] = 100 * sum(r["y"] for r in s) / len(s)
                K[(i, j)] = (sum(r["y"] for r in s), len(s))
    fig, ax = plt.subplots(figsize=(5.6, 3.3), dpi=170)
    ax.imshow(np.nan_to_num(M, nan=0), cmap="Oranges", vmin=0, vmax=100, aspect="auto")
    for i in range(3):
        for j in range(4):
            if np.isnan(M[i, j]):
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, facecolor="#f3f3f3", hatch="///", edgecolor="#ccc", lw=0))
                ax.text(j, i, "no rate", ha="center", va="center", fontsize=8.5, color="#777")
            else:
                k, n = K[(i, j)]
                col = "white" if M[i, j] > 55 else "#222"
                ax.text(j, i - 0.15, f"{M[i, j]:.0f}%", ha="center", va="center", fontsize=13, weight="bold", color=col)
                ax.text(j, i + 0.25, f"{k}/{n}", ha="center", va="center", fontsize=9, color=col)
    ax.set_xticks(range(4)); ax.set_xticklabels([a[1] for a in acts], fontsize=10)
    ax.set_yticks(range(3)); ax.set_yticklabels([NAME[a] for a in AG], fontsize=9.5)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(length=0)
    fig.tight_layout()
    fig.savefig(OUT / "act-heatmap.png", facecolor="white", bbox_inches="tight")
    plt.close(fig)


def fig_ctx():
    """Fig. 9: the same cells split by the two frozen task contexts."""
    fig, ax = plt.subplots(figsize=(5.6, 3.4), dpi=170)
    w = 0.36
    for i, ag in enumerate(AG):
        for j, c_ in enumerate(("ctx-1", "ctx-2")):
            s = [r for r in PX if r["agent"] == ag and r["condition"] == "replica" and r["context"] == c_]
            x = i + (j - 0.5) * w * 1.05
            if not s:
                ax.bar(x, 2, w, color="#eee", edgecolor="#ccc", hatch="///")
                ax.text(x, 6, "not run", ha="center", fontsize=8, color="#888")
                ax.text(x, -10, c_, ha="center", fontsize=8, color="#666")
                continue
            k, n = sum(r["y"] for r in s), len(s)
            rate = 100 * k / n
            ax.bar(x, rate, w, color=COL[ag], alpha=1 if j == 0 else 0.55)
            ax.text(x, rate + 2.5, f"{rate:.0f}%", ha="center", fontsize=10.5, weight="bold")
            ax.text(x, max(rate - 9, 3), f"{k}/{n}", ha="center", fontsize=8, color="white" if rate > 15 else "#555")
            ax.text(x, -10, c_, ha="center", fontsize=8, color="#666")
    ax.set_xticks(range(3)); ax.set_xticklabels([NAME[a] for a in AG], fontsize=9.5)
    ax.tick_params(axis="x", pad=14)
    ax.set_ylim(0, 118); ax.set_yticks([0, 50, 100]); ax.set_yticklabels(["0", "50%", "100%"], fontsize=9)
    ax.set_ylabel("copies acted on", fontsize=9.5)
    clean_axes(ax)
    fig.tight_layout()
    fig.savefig(OUT / "context-split.png", facecolor="white", bbox_inches="tight")
    plt.close(fig)


def fig_dose():
    """Fig. 13: copy rate as the observation gains information about who drew the screen."""
    D = F["dose"]
    arms = [("pixels", "screenshot\nonly"), ("structured", "+ accessibility\ntree"), ("provenance", "+ principal\nlabels")]
    fig, ax = plt.subplots(figsize=(8.8, 3.4), dpi=160)
    gmin = 1.0
    for ag in AG:
        ys, ks = [], []
        for a, _ in arms:
            v = D[ag]["arms"][a]
            ys.append(100 * v["replica"]["k"] / v["replica"]["n"])
            ks.append(f"{v['replica']['k']}/{v['replica']['n']}")
            gmin = min(gmin, v["genuine"]["k"] / v["genuine"]["n"])
        ax.plot(range(3), ys, marker="o", lw=2.1, ms=6, color=COL[ag])
        ax.annotate(f"{NAME[ag]}  {ys[-1]:.0f}%", (2, ys[-1]), textcoords="offset points", xytext=(9, -3), fontsize=9.5, color=COL[ag], weight="600")
        for x, (y, k) in enumerate(zip(ys, ks)):
            ax.annotate(k, (x, y), textcoords="offset points", xytext=(0, -13), ha="center", fontsize=7.5, color="#888")
    ax.set_xticks(range(3)); ax.set_xticklabels([a[1] for a in arms], fontsize=9.5)
    ax.set_xlim(-0.22, 3.0); ax.set_ylim(-10, 115)
    ax.set_yticks([0, 50, 100]); ax.set_yticklabels(["0", "50%", "100%"], fontsize=9)
    ax.set_ylabel("the adversary's copy\nacted on", fontsize=9.5)
    ax.set_title(f"the application's own prompt is acted on in {100 * gmin:.0f}–100% of episodes at every level", fontsize=9.5, color="#666", pad=7)
    clean_axes(ax)
    fig.tight_layout()
    p = OUT / "dose-response.png"
    fig.savefig(p, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    pad_aspect(p, 0.589)


def fig_blind():
    """Fig. 14: the vendor's classifier on 60 single screens, blind to the condition."""
    d = json.loads((ROOT / "results" / "E0" / "frontier-refusal-taxonomy-blind" / "summary.json").read_text(encoding="utf-8"))["cells"]
    agg = collections.defaultdict(lambda: [0, 0])
    for k, v in d.items():
        cell, kind, _cond, _instr = k.split("/")
        agg[(cell, kind)][0] += v["classifier_halt"]
        agg[(cell, kind)][1] += v["n"]
    order = [("browser-l1", "prompt", "web inline\nauthority prompt"), ("browser-l2", "prompt", "web framed\nauthority prompt"),
             ("chat-l1-web", "prompt", "chat\nauthority prompt"), ("browser-l1", "benign", "web inline\nno prompt"), ("chat-l1-web", "benign", "chat\nno prompt")]
    fig, ax = plt.subplots(figsize=(8.6, 4.0), dpi=160)
    for i, (c, k, _lab) in enumerate(order):
        kk, nn = agg[(c, k)]
        ax.bar(i, kk / nn, 0.62, color="#8a6a4f" if k == "prompt" else "#c0392b")
        ax.text(i, kk / nn + 0.035, f"{kk}/{nn}", ha="center", fontsize=11, weight="bold")
    ax.set_xticks(range(5)); ax.set_xticklabels([o[2] for o in order], fontsize=9.5)
    ax.set_ylim(0, 1.18); ax.set_yticks([0, 0.5, 1.0]); ax.set_yticklabels(["0", "50%", "100%"], fontsize=10)
    ax.set_ylabel("share of requests halted", fontsize=10.5)
    ax.set_title("The vendor's injection classifier on 60 single screens, blind to the condition", fontsize=11.5, pad=10, color="#333")
    clean_axes(ax)
    ax.axvline(2.5, color="#ddd", lw=1)
    ax.text(3.5, 1.10, "controls: no authority prompt on screen", ha="center", fontsize=9.5, color="#c0392b")
    fig.tight_layout()
    p = OUT / "probe-blind.png"
    fig.savefig(p, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    pad_aspect(p, 0.507)


def fig_fix():
    """Fig. 15: the provenance check handed to the model against enforced in the harness."""
    pro = F["dose"]["anthropic_frontier"]["arms"]["provenance"]
    pol = F["policy"]
    groups = [("the agent reads the channel\n(Claude Opus 5.5)", pro["genuine"], pro["replica"]),
              ("the harness enforces it\n(policy, any agent)", pol["genuine"], pol["replica"])]
    fig, ax = plt.subplots(figsize=(8.4, 4.3), dpi=160)
    w = 0.34
    for i, (_lab, g, c) in enumerate(groups):
        gr, cr = 100 * g["k"] / g["n"], 100 * c["k"] / c["n"]
        ax.bar(i - w / 2, gr, w, color=GEN); ax.bar(i + w / 2, cr, w, color=CPY)
        ax.text(i - w / 2, gr + 2.5, f"{gr:.0f}%", ha="center", fontsize=12, weight="bold")
        ax.text(i - w / 2, gr - 7, f"{g['k']}/{g['n']}", ha="center", fontsize=9, color="white")
        ax.text(i + w / 2, cr + 2.5, f"{cr:.0f}%", ha="center", fontsize=12, weight="bold")
        if cr > 12:
            ax.text(i + w / 2, cr - 7, f"{c['k']}/{c['n']}", ha="center", fontsize=9, color="white")
        else:
            ax.text(i + w / 2, cr + 9.5, f"{c['k']}/{c['n']}", ha="center", fontsize=9, color="#666")
    ax.set_xticks(range(2)); ax.set_xticklabels([g[0] for g in groups], fontsize=11)
    ax.set_ylim(0, 120); ax.set_yticks([0, 50, 100]); ax.set_yticklabels(["0", "50%", "100%"], fontsize=10)
    ax.set_ylabel("acted on", fontsize=11)
    clean_axes(ax)
    ax.legend(handles=[Patch(color=GEN, label="the application's own prompt"), Patch(color=CPY, label="the adversary's copy")],
              loc="upper center", bbox_to_anchor=(0.5, 1.16), ncol=2, frameon=False, fontsize=10.5)
    fig.tight_layout()
    p = OUT / "the-fix.png"
    fig.savefig(p, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    pad_aspect(p, 0.627)


if __name__ == "__main__":
    for fn in (fig_headline, fig_twins, fig_eps, fig_gapnav, fig_acts, fig_ctx, fig_dose, fig_blind, fig_fix):
        fn()
        print("wrote", fn.__name__.replace("fig_", ""))
