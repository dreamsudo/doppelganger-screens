"""
File · src/awp/metrics.py
Purpose · The one implementation of the method's quantities: utility U, confusion rate CR, defence advantage D (METHOD.md §2) with 95 percent intervals by cluster bootstrap over contexts and TOST equivalence against the pre-registered margin (METHOD.md §8); and ε between a twin pair, as normalised L2 and SSIM over the prompt crop of the exact image sent to the model (METHOD.md §6 "Paired design"), with the per-pair check that nothing but the prompt region differs.
Description · Outcomes are binary per episode with a context id; U = mean y over genuine episodes, CR over replica episodes, D = U - CR; intervals resample contexts with replacement (cluster bootstrap, 2,000 draws, seed fixed and recorded); TOST declares "at chance" only if the whole interval of D lies inside (-margin, +margin). ε: images as float arrays in [0, 1]; normalised L2 = ||a - b||₂ / ||a||₂ over the crop; SSIM with an 11x11 Gaussian window (σ 1.5), K1 0.01, K2 0.03 on grayscale, mean over the crop; the pair check computes the fraction of changed pixels outside the prompt region (should be 0 for a matched pair). No dependency beyond numpy and Pillow. Shaped by (SSIM ≥ 0.95 and L2 ≤ 0.05 as the small-ε threshold).
Inputs/Outputs · In: episode rows (y, context, condition), PNG bytes or arrays, crop boxes. Out: dicts of numbers with their N and the parameters used.
Depends on · numpy, Pillow.
Invariant · Every returned estimate carries its N and the draws and seed of its interval; a mean without them is never returned; no exclusion happens here.
"""

from __future__ import annotations

import io
from math import comb

import numpy as np
from PIL import Image


# ---------------------------------------------------------------- outcomes
def rate(rows, condition):
    ys = [r["y"] for r in rows if r.get("condition") == condition and r.get("y") in (0, 1)]
    return (sum(ys) / len(ys) if ys else None), len(ys)


def _binom_le(k, n, p):
    return sum(comb(n, i) * p**i * (1.0 - p) ** (n - i) for i in range(k + 1))


def _binom_ge(k, n, p):
    return sum(comb(n, i) * p**i * (1.0 - p) ** (n - i) for i in range(k, n + 1))


def _bisect(f, lo, hi, rising, tol=1e-12):
    for _ in range(200):
        mid = (lo + hi) / 2
        v = f(mid)
        if (v < 0) == rising:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2


def clopper_pearson(k, n, alpha=0.05):
    """The exact binomial interval. measured (adversarial review F3): the cluster bootstrap this replaced resampled two contexts and could
    only ever return the two observed values, which it then reported as a 95 percent interval."""
    if not n:
        return None
    lo = 0.0 if k == 0 else _bisect(lambda p: _binom_ge(k, n, p) - alpha / 2, 0.0, 1.0, True)
    hi = 1.0 if k == n else _bisect(lambda p: _binom_le(k, n, p) - alpha / 2, 0.0, 1.0, False)
    return [round(lo, 4), round(hi, 4)]


def wilson(k, n, z=1.959963985):
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return [(c - h) / d, (c + h) / d]


def newcombe_difference(k1, n1, k2, n2):
    """Newcombe's hybrid-score interval for the difference of two independent proportions: no resampling, valid at the sample sizes this study has."""
    if not n1 or not n2:
        return None
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1)
    l2, u2 = wilson(k2, n2)
    lo = (p1 - p2) - (((p1 - l1) ** 2 + (u2 - p2) ** 2) ** 0.5)
    hi = (p1 - p2) + (((u1 - p1) ** 2 + (p2 - l2) ** 2) ** 0.5)
    return [round(max(-1.0, lo), 4), round(min(1.0, hi), 4)]


def fisher_exact_two_sided(a, b, c, d):
    """Exact two-sided test on the 2x2 [[a, b], [c, d]], by summing every table no more probable than the observed one."""
    n, r1, c1 = a + b + c + d, a + b, a + c
    if not n or not r1 or not c1 or r1 == n or c1 == n:
        return 1.0

    def pr(x):
        return comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)

    p0 = pr(a)
    lo_x, hi_x = max(0, c1 - (n - r1)), min(r1, c1)
    return round(min(1.0, sum(pr(x) for x in range(lo_x, hi_x + 1) if pr(x) <= p0 + 1e-12)), 4)


def u_cr_d(rows, margin=0.10, draws=None, seed=None):
    """U, CR and D with exact intervals and an exact two-sided test. Contexts are counted and reported as a stratum; they are not resampled."""
    contexts = sorted({r.get("context", r.get("nonce")) for r in rows})
    U, nU = rate(rows, "genuine")
    CR, nCR = rate(rows, "replica")
    kU = 0 if U is None else round(U * nU)
    kCR = 0 if CR is None else round(CR * nCR)
    out = {
        "U": U,
        "n_genuine": nU,
        "CR": CR,
        "n_replica": nCR,
        "D": (None if U is None or CR is None else round(U - CR, 4)),
        "n_contexts": len(contexts),
        "method": "Clopper-Pearson for each rate; Newcombe hybrid score for the difference; Fisher exact two-sided; no resampling",
    }
    if U is not None:
        out["U_ci95"] = clopper_pearson(kU, nU)
    if CR is not None:
        out["CR_ci95"] = clopper_pearson(kCR, nCR)
    if U is None or CR is None:
        return out
    out["D_ci95"] = newcombe_difference(kU, nU, kCR, nCR)
    out["exact_p"] = fisher_exact_two_sided(kU, nU - kU, kCR, nCR - kCR)
    lo, hi = out["D_ci95"]
    out["tost"] = {
        "margin": margin,
        "at_chance": bool(lo > -margin and hi < margin),
        "note": "at chance only if the whole exact 95 percent interval of D lies inside the margin; never by failure to reject",
    }
    return out


def pooled_exact(rows):
    """One exact test over a set of groups pooled: the statement a study of this size can actually support."""
    g = [r for r in rows if r.get("condition") == "genuine" and r.get("y") in (0, 1)]
    p = [r for r in rows if r.get("condition") == "replica" and r.get("y") in (0, 1)]
    if not g or not p:
        return None
    kg, kp = sum(r["y"] for r in g), sum(r["y"] for r in p)
    return {
        "U": round(kg / len(g), 4),
        "n_genuine": len(g),
        "CR": round(kp / len(p), 4),
        "n_replica": len(p),
        "D": round(kg / len(g) - kp / len(p), 4),
        "D_ci95": newcombe_difference(kg, len(g), kp, len(p)),
        "exact_p": fisher_exact_two_sided(kg, len(g) - kg, kp, len(p) - kp),
    }


# ---------------------------------------------------------------- images and ε
def _i(v):
    """Round to a Python int; numpy's round would return a numpy float, which cannot index an array."""
    return int(np.rint(float(v)))


def to_gray(png_or_array):
    if isinstance(png_or_array, (bytes, bytearray)):
        img = Image.open(io.BytesIO(png_or_array)).convert("L")
        return np.asarray(img, dtype=np.float64) / 255.0
    a = np.asarray(png_or_array, dtype=np.float64)
    if a.ndim == 3:
        a = a[..., :3].mean(axis=2)
    return a / 255.0 if a.max() > 1.0 else a


def crop(gray, box):
    x, y, w, h = [_i(v) for v in box]
    return gray[y : y + h, x : x + w]


def normalised_l2(a, b):
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch {a.shape} vs {b.shape}")
    den = float(np.linalg.norm(a)) or 1.0
    return float(np.linalg.norm(a - b) / den)


def _gaussian_window(size=11, sigma=1.5):
    ax = np.arange(size) - (size - 1) / 2.0
    g = np.exp(-(ax**2) / (2 * sigma**2))
    w = np.outer(g, g)
    return w / w.sum()


def _filter2(img, win):
    """Valid-mode 2-D correlation with a separable-ish window via FFT-free sliding sums (small images, exact)."""
    from numpy.lib.stride_tricks import sliding_window_view

    k = win.shape[0]
    if img.shape[0] < k or img.shape[1] < k:
        return np.array([[img.mean()]])
    v = sliding_window_view(img, (k, k))
    return np.einsum("ijkl,kl->ij", v, win)


def ssim(a, b, k1=0.01, k2=0.03, win_size=11, sigma=1.5):
    """Structural similarity over the crop (grayscale in [0, 1]); the mean of the SSIM map."""
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch {a.shape} vs {b.shape}")
    win = _gaussian_window(win_size, sigma)
    mu_a, mu_b = _filter2(a, win), _filter2(b, win)
    saa = _filter2(a * a, win) - mu_a**2
    sbb = _filter2(b * b, win) - mu_b**2
    sab = _filter2(a * b, win) - mu_a * mu_b
    c1, c2 = (k1 * 1.0) ** 2, (k2 * 1.0) ** 2
    m = ((2 * mu_a * mu_b + c1) * (2 * sab + c2)) / ((mu_a**2 + mu_b**2 + c1) * (saa + sbb + c2))
    return float(m.mean())


def pair_epsilon(genuine_png, replica_png, prompt_box, ssim_min=0.95, l2_max=0.05, margin=30):
    """ε of a twin pair on the prompt crop (the element's box grown by `margin` px so its shadow counts as part of the region), and the per-pair
    check: the fraction of pixels that differ outside that region (0 for a matched pair)."""
    ga, rb = to_gray(genuine_png), to_gray(replica_png)
    if ga.shape != rb.shape:
        return {"error": f"shape mismatch {ga.shape} vs {rb.shape}"}
    x0, y0, w0, h0 = prompt_box
    x, y = max(0, _i(x0 - margin)), max(0, _i(y0 - margin))
    w, h = min(ga.shape[1] - x, _i(w0 + 2 * margin)), min(ga.shape[0] - y, _i(h0 + 2 * margin))
    prompt_box = [x, y, w, h]
    ca, cb = crop(ga, prompt_box), crop(rb, prompt_box)
    l2, s = normalised_l2(ca, cb), ssim(ca, cb)
    outside = np.ones_like(ga, dtype=bool)
    outside[y : y + h, x : x + w] = False
    n_outside = int(outside.sum())
    # when the region is the whole screen there is no outside, and a mean over nothing is not a number: report it as absent, never as 0 or NaN
    diff_outside = round(float(np.mean(np.abs(ga - rb)[outside] > (2 / 255))), 6) if n_outside else None
    return {
        "l2": round(l2, 5),
        "ssim": round(s, 5),
        "matched": bool(s >= ssim_min and l2 <= l2_max),
        "outside_changed_fraction": diff_outside,
        "pixels_outside_region": n_outside,
        "box": [x, y, w, h],
        "thresholds": {"ssim_min": ssim_min, "l2_max": l2_max},
    }


def summarise_epsilon(pairs):
    """Distribution of ε over pairs (METHOD.md §6: reported as a distribution)."""
    l2s = [p["l2"] for p in pairs if "l2" in p]
    ss = [p["ssim"] for p in pairs if "ssim" in p]
    if not l2s:
        return {"n": 0}
    q = lambda v, p: round(float(np.percentile(v, p)), 5)
    return {
        "n": len(l2s),
        "l2": {"median": q(l2s, 50), "p90": q(l2s, 90), "max": round(max(l2s), 5)},
        "ssim": {"median": q(ss, 50), "p10": q(ss, 10), "min": round(min(ss), 5)},
        "matched": sum(1 for p in pairs if p.get("matched")),
        "unmatched": sum(1 for p in pairs if "matched" in p and not p["matched"]),
    }
