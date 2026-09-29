#!/usr/bin/env python3
"""Generate environment/data/morphological_chart.json.

A morphological chart (Zwicky's morphological analysis) for the concept
design of a spring-loaded latch/retention mechanism: four sub-functions, each
with three
or four discrete solution variants, plus a small set of pairwise
incompatibility rules (a standard "cross-consistency assessment" extension
of Zwicky's method) that rule out some combinations outright.

Deterministic and idempotent: no random data. The generator writes the chart
and self-checks, by direct enumeration of the full combinatorial space, that
the feasible count and the unique highest-scoring feasible combination match
tests/ground_truth.json before writing.
"""
import itertools
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = REPO / "environment" / "data" / "morphological_chart.json"
TRUTH = REPO / "tests" / "ground_truth.json"

SUB_FUNCTIONS = {
    "energy_storage": {
        "A1": {"name": "helical compression spring", "score": 8},
        "A2": {"name": "helical extension spring", "score": 6},
        "A3": {"name": "torsion spring", "score": 5},
        "A4": {"name": "elastomer pad", "score": 4},
    },
    "guide_method": {
        "B1": {"name": "rod-guided (internal guide rod)", "score": 9},
        "B2": {"name": "hole-guided (external sleeve)", "score": 7},
        "B3": {"name": "unguided (free-standing)", "score": 4},
    },
    "end_fixation": {
        "C1": {"name": "plain ends", "score": 3},
        "C2": {"name": "squared ends", "score": 6},
        "C3": {"name": "squared-and-ground ends", "score": 9},
    },
    "material": {
        "D1": {"name": "Ni-alloy-matrix particulate composite wire (low reinforcement)", "score": 6},
        "D2": {"name": "Fe-alloy-matrix particulate composite wire (high reinforcement)", "score": 5},
        "D3": {"name": "Fe-Cr-alloy-matrix particulate composite wire (moderate reinforcement)", "score": 9},
    },
}

# Pairwise incompatibilities: a feasible combination may not contain both
# members of any listed pair, regardless of the other two sub-functions.
EXCLUDED_PAIRS = [
    ["A4", "B1"],  # an elastomer pad has no coil body for a guide rod
    ["A4", "C3"],  # end-grinding is not meaningful for an elastomer pad
    ["A3", "C2"],  # torsion springs use hook/tangent ends, not squared axial ends
    ["A3", "C3"],  # same reasoning as above
    ["D3", "B1"],  # catalogue rule: the Fe-Cr-alloy composite wire is not paired with a press-fit rod guide in this family
]


def _enumerate(chart, excluded_pairs):
    excluded = {frozenset(p) for p in excluded_pairs}
    keys = list(chart.keys())
    total = 1
    for k in keys:
        total *= len(chart[k])
    feasible = []
    for combo in itertools.product(*[chart[k].keys() for k in keys]):
        pairs = [frozenset(p) for p in itertools.combinations(combo, 2)]
        if any(p in excluded for p in pairs):
            continue
        score = sum(chart[keys[i]][combo[i]]["score"] for i in range(len(keys)))
        feasible.append((score, dict(zip(keys, combo))))
    feasible.sort(key=lambda t: t[0], reverse=True)
    return total, feasible


def check():
    if not OUT.exists() or not TRUTH.exists():
        return False
    chart = json.loads(OUT.read_text())["sub_functions"]
    total, feasible = _enumerate(chart, EXCLUDED_PAIRS)
    truth = json.loads(TRUTH.read_text())
    if total != truth["morph_total_combinations"]:
        return False
    if len(feasible) != truth["morph_feasible_combinations"]:
        return False
    best_score, best_combo = feasible[0]
    if best_score != truth["morph_best_score"]:
        return False
    if best_combo != truth["morph_best_combination"]:
        return False
    return True


def main():
    if check():
        print(f"{OUT} already present and consistent with ground truth; not overwriting")
        return

    total, feasible = _enumerate(SUB_FUNCTIONS, EXCLUDED_PAIRS)
    best_score, best_combo = feasible[0]
    n_at_best = sum(1 for s, _ in feasible if s == best_score)

    payload = {
        "sub_functions": SUB_FUNCTIONS,
        "excluded_pairs": EXCLUDED_PAIRS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))

    print(f"total combinations = {total}")
    print(f"feasible combinations = {len(feasible)}")
    print(f"best feasible combination = {best_combo} score={best_score} "
          f"(unique: {n_at_best == 1})")
    print(f"wrote {OUT}")

    if n_at_best != 1:
        raise SystemExit("morphological chart FAILED self-check: best score is not unique")
    if not check():
        raise SystemExit("morphological_chart.json FAILED self-check against ground truth")
    print("self-check passed")


if __name__ == "__main__":
    main()
