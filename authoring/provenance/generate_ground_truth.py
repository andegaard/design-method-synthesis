#!/usr/bin/env python3
"""End-to-end provenance self-check for design-method-synthesis.

Runs every dataset generator (each is idempotent: it leaves an existing,
already-consistent file alone and only writes when a file is missing or
fails its own check against tests/ground_truth.json), then runs the
reference solver against environment/data, then grades the result against
tests/ground_truth.json using the exact same checks as tests/test_outputs.py,
in-process (this repo's sandbox cannot install the real pytest package from
PyPI, so this mirrors it directly rather than shelling out to pytest).

Usage:
    python3 authoring/provenance/generate_ground_truth.py
"""
import importlib.util
import subprocess
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO / "authoring" / "provenance" / "dataset"
SOLUTION = REPO / "solution" / "solve.py"
TESTS = REPO / "tests" / "test_outputs.py"

GENERATORS = [
    "generate_morphological.py",
    "generate_axiomatic.py",
    "generate_spring_opt.py",
    "generate_taguchi.py",
    "generate_pareto_candidates.py",
]


def run(cmd, **env_overrides):
    import os
    env = dict(os.environ)
    env.update(env_overrides)
    print(f"$ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=REPO, env=env)
    if result.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(str(c) for c in cmd)}")


def main():
    print("=== 1. dataset generators (idempotent) ===")
    for g in GENERATORS:
        run([sys.executable, str(DATASET_DIR / g)])
        print()

    print("=== 2. reference solver ===")
    out_dir = REPO / "authoring" / "provenance" / "_solve_check_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    run([sys.executable, str(SOLUTION)],
        HARBOR_DATA_DIR=str(REPO / "environment" / "data"),
        HARBOR_OUT_DIR=str(out_dir))

    print("\n=== 3. grading against tests/ground_truth.json ===")
    import os
    os.environ["HARBOR_OUT_DIR"] = str(out_dir)
    os.environ["HARBOR_TRUTH_DIR"] = str(REPO / "tests")
    os.environ["MORPH_JSON"] = str(REPO / "tests" / "morphological_chart.json")
    os.environ["AXIOM_JSON"] = str(REPO / "tests" / "axiomatic_design_candidates.json")
    os.environ["TAGUCHI_CSV"] = str(REPO / "tests" / "taguchi_spring_robustness.csv")
    os.environ["PARETO_CSV"] = str(REPO / "tests" / "pareto_candidate_designs.csv")

    if "pytest" not in sys.modules:
        stub = types.ModuleType("pytest")
        sys.modules["pytest"] = stub

    spec = importlib.util.spec_from_file_location("test_outputs", TESTS)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["test_outputs"] = mod
    spec.loader.exec_module(mod)

    names = [n for n in dir(mod) if n.startswith("test_")]
    passed, failed = [], []
    for n in names:
        try:
            getattr(mod, n)()
            passed.append(n)
        except Exception as e:
            failed.append((n, repr(e)))

    print(f"{len(passed)}/{len(names)} checks passed")
    for n, e in failed:
        print(f"  FAIL: {n}: {e}")
    if failed:
        raise SystemExit(f"{len(failed)} check(s) failed")
    print("\nall checks passed -- dataset is self-consistent with tests/ground_truth.json")


if __name__ == "__main__":
    main()
