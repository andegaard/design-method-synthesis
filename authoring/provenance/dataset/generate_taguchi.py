#!/usr/bin/env python3
"""Generate environment/data/taguchi_spring_robustness.csv.

A Taguchi robust-design experiment (L9 orthogonal array) on the same
physical spring component: does the chosen wire diameter / coil diameter /
active-coil
combination hold its spring rate steady under two independent, named
manufacturing-tolerance noise sources, or does it drift?

  spring rate k = G * d^4 / (8 * D^3 * N)     (G = 80000 N/mm^2, fixed)

Inner array: 3 control factors x 3 levels each (L9).
Outer array: 3 *named* noise conditions (not random draws) --
  "low"  : wire diameter -0.015 mm, active coils -0.2   (cold / under-count)
  "nom"  : no perturbation
  "high" : wire diameter +0.015 mm, active coils +0.2   (hot / over-count)
d enters k to the 4th power and N enters as 1/N, so a fixed *absolute*
manufacturing tolerance on d and N has a size-dependent *relative* effect on
k -- this is the real, physically-grounded reason some factor levels turn
out more robust (higher signal-to-noise ratio) than others, not sampling
noise. Coil diameter D carries no noise in this experiment, deliberately,
to see whether the resulting response table shows that.

Fully deterministic (the three noise conditions are fixed, not random), so
every run is exactly reproducible. Self-checks against tests/ground_truth.json.
"""
import csv
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = REPO / "environment" / "data" / "taguchi_spring_robustness.csv"
TRUTH = REPO / "tests" / "ground_truth.json"

G = 80000.0

A_LEVELS = {1: 1.2, 2: 1.4, 3: 1.6}    # wire diameter d, mm
B_LEVELS = {1: 10.0, 2: 12.0, 3: 14.0}  # coil diameter D, mm
C_LEVELS = {1: 8, 2: 10, 3: 12}         # active coils N

L9 = [
    (1, 1, 1), (1, 2, 2), (1, 3, 3),
    (2, 1, 2), (2, 2, 3), (2, 3, 1),
    (3, 1, 3), (3, 2, 1), (3, 3, 2),
]

NOISE_CONDITIONS = [
    ("low", -0.015, -0.2),
    ("nom", 0.000, 0.0),
    ("high", 0.015, 0.2),
]


def spring_rate(d, D, N):
    return G * d**4 / (8 * D**3 * N)


def build_rows():
    rows = []
    for run_id, (ai, bi, ci) in enumerate(L9, start=1):
        d, D, N = A_LEVELS[ai], B_LEVELS[bi], C_LEVELS[ci]
        for noise_name, dd, dn in NOISE_CONDITIONS:
            k = spring_rate(d + dd, D, N + dn)
            rows.append({
                "run_id": run_id, "A_level": ai, "B_level": bi, "C_level": ci,
                "d_nominal_mm": d, "D_nominal_mm": D, "N_nominal": N,
                "noise_condition": noise_name, "spring_rate_k_Nmm": round(k, 6),
            })
    return rows


def sn_by_run(rows):
    out = {}
    for run_id in sorted({r["run_id"] for r in rows}):
        ks = np.array([r["spring_rate_k_Nmm"] for r in rows if r["run_id"] == run_id])
        mean_k, var_k = ks.mean(), ks.var(ddof=1)
        out[run_id] = 10 * np.log10(mean_k**2 / var_k)
    return out


def check():
    if not OUT.exists() or not TRUTH.exists():
        return False
    with open(OUT, newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["run_id"] = int(r["run_id"])
        r["spring_rate_k_Nmm"] = float(r["spring_rate_k_Nmm"])
    sn = sn_by_run(rows)
    truth = json.loads(TRUTH.read_text())
    true_sn = {int(k): v for k, v in truth["taguchi_sn_by_run_true"].items()}
    return all(abs(sn[rid] - true_sn[rid]) < 0.01 for rid in true_sn)


def main():
    if check():
        print(f"{OUT} already present and consistent with ground truth; not overwriting")
        return

    rows = build_rows()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    sn = sn_by_run(rows)
    for run_id, val in sn.items():
        print(f"run {run_id}: SN = {val:.3f} dB")
    print(f"wrote {len(rows)} rows to {OUT}")

    if not check():
        raise SystemExit("taguchi_spring_robustness.csv FAILED self-check against ground truth")
    print("self-check passed")


if __name__ == "__main__":
    main()
