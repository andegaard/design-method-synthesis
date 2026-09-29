#!/usr/bin/env python3
"""Generate environment/data/axiomatic_design_candidates.json.

Three candidate embodiments (design-parameter mappings) for the latch
spring subsystem selected in the morphological-analysis stage, to be
evaluated with Suh's Axiomatic Design:

  Independence Axiom -- classify each design's FR-DP sensitivity matrix as
  uncoupled (diagonal), decoupled (triangular, reorderable so every FR has
  a DP that affects it and nothing "later"), or coupled (neither). Only
  uncoupled and decoupled designs satisfy the Independence Axiom.

  Information Axiom -- among Independence-Axiom-compliant designs, the
  preferred one has the lowest total information content, summed over the
  three functional requirements:
      I_i = -log2(p_i),  p_i = Phi((USL-mu)/sigma) - Phi((LSL-mu)/sigma)
  where [LSL, USL] is the design range (customer specification) for FR_i
  and (mu, sigma) is the achieved system range (process capability) for
  that design, Phi the standard normal CDF.

Three functional requirements throughout:
  FR1 = deliver the specified retention force at operating deflection (N)
  FR2 = limit lateral deflection under a side load (mm)
  FR3 = keep tool-free assembly insertion force within spec (N)

Design Y is a deliberate distractor: its FR-DP matrix is fully coupled, and
its process data is (deliberately) the tightest of the three, giving it the
lowest raw information content. A correct application of Axiomatic Design
rejects Y on the Independence Axiom regardless of its information content,
and picks the lower-information design between X and Z.

Deterministic; no random data. Self-checks against tests/ground_truth.json.
"""
import json
from math import log2
from pathlib import Path

from scipy.stats import norm

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = REPO / "environment" / "data" / "axiomatic_design_candidates.json"
TRUTH = REPO / "tests" / "ground_truth.json"

FR_NAMES = ["FR1", "FR2", "FR3"]
DP_NAMES = ["DP1", "DP2", "DP3"]

DESIGNS = {
    "X": {
        "description": "rod-guided compression spring: separate guide rod for "
                        "stability, squared-and-ground end for the assembly stop",
        # rows = FR1..FR3, cols = DP1..DP3; nonzero pattern only matters for
        # coupling classification (values are illustrative sensitivities).
        "matrix": [
            [1.0, 0.0, 0.0],
            [0.6, 1.0, 0.0],
            [0.0, 0.4, 1.0],
        ],
        "process_data": {
            # FR: [LSL, USL, mu, sigma]  (force in N, deflection in mm)
            "FR1": [39.0, 51.0, 45.5, 2.2],
            "FR2": [0.0, 0.30, 0.17, 0.05],
            "FR3": [8.0, 16.0, 12.5, 1.3],
        },
    },
    "Z": {
        "description": "hole-guided compression spring: external sleeve doubles as "
                        "both guide and force reaction, single-feature end geometry",
        "matrix": [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        "process_data": {
            "FR1": [39.0, 51.0, 44.0, 1.6],
            "FR2": [0.0, 0.30, 0.14, 0.04],
            "FR3": [8.0, 16.0, 13.5, 2.0],
        },
    },
    "Y": {
        "description": "unguided free-standing spring with a single integrated "
                        "geometry parameter set intended to control force, "
                        "stability and assembly simultaneously",
        "matrix": [
            [1.0, 0.7, 0.5],
            [0.6, 1.0, 0.6],
            [0.5, 0.7, 1.0],
        ],
        "process_data": {
            "FR1": [39.0, 51.0, 45.0, 1.0],
            "FR2": [0.0, 0.30, 0.15, 0.025],
            "FR3": [8.0, 16.0, 12.0, 0.75],
        },
    },
}


def classify_coupling(matrix, tol=1e-9):
    """Uncoupled: diagonal only. Decoupled: some row/column permutation makes
    it triangular (every FR has a DP that affects it and nothing after it in
    the sequence). Coupled: neither. Brute-forces all column permutations
    (3x3, so 6 permutations) since the matrices here are always 3x3."""
    import itertools
    n = len(matrix)
    nz = [[abs(matrix[i][j]) > tol for j in range(n)] for i in range(n)]

    def is_diagonal(m):
        return all(m[i][j] == (i == j) for i in range(n) for j in range(n))

    def is_lower_triangular(m):
        return all(not m[i][j] for i in range(n) for j in range(n) if j > i)

    if is_diagonal(nz):
        return "uncoupled"
    for perm in itertools.permutations(range(n)):
        permuted = [[nz[i][perm[j]] for j in range(n)] for i in range(n)]
        if is_lower_triangular(permuted):
            return "decoupled"
    return "coupled"


def info_content(lsl, usl, mu, sigma):
    p = norm.cdf((usl - mu) / sigma) - norm.cdf((lsl - mu) / sigma)
    return -log2(p), p


def check():
    if not OUT.exists() or not TRUTH.exists():
        return False
    data = json.loads(OUT.read_text())
    truth = json.loads(TRUTH.read_text())
    for name, spec in data["designs"].items():
        coupling = classify_coupling(spec["matrix"])
        if coupling != truth["axiomatic_coupling_true"][name]:
            return False
        if coupling == "coupled":
            continue
        total_I = sum(info_content(*spec["process_data"][fr])[0] for fr in FR_NAMES)
        if abs(total_I - truth["axiomatic_info_bits_true"][name]) > 0.01:
            return False
    return True


def main():
    if check():
        print(f"{OUT} already present and consistent with ground truth; not overwriting")
        return

    payload = {"designs": DESIGNS, "fr_definitions": {
        "FR1": "retention force at operating deflection (N)",
        "FR2": "lateral deflection under a 10 N side load (mm)",
        "FR3": "tool-free assembly insertion force (N)",
    }}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))

    for name, spec in DESIGNS.items():
        coupling = classify_coupling(spec["matrix"])
        print(f"Design {name}: coupling = {coupling}")
        if coupling != "coupled":
            total_I = 0.0
            for fr in FR_NAMES:
                I, p = info_content(*spec["process_data"][fr])
                total_I += I
                print(f"    {fr}: p={p:.6f} I={I:.4f} bits")
            print(f"    TOTAL I = {total_I:.4f} bits")

    print(f"wrote {OUT}")
    if not check():
        raise SystemExit("axiomatic_design_candidates.json FAILED self-check against ground truth")
    print("self-check passed")


if __name__ == "__main__":
    main()
