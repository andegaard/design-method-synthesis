#!/usr/bin/env python3
"""Generate environment/data/pareto_candidate_designs.csv.

Twelve candidate final (d, D, Na, treatment) spring designs to be screened
with multi-objective decision methods (Pareto dominance, TOPSIS, and the
weighted-sum method) against THREE competing objectives: minimize relative
cost (the parametric-optimization stage's own cost(d, D, Na, treatment),
which already accounts for the wire-treatment's cost multiplier), maximize
active coil count Na as a durability proxy, and maximize the fundamental
natural frequency's margin above the required surge floor (a dynamic-safety
proxy) -- three objectives that do not all improve together, since a larger,
more-durable spring (more Na, larger D) tends to have a *lower* natural
frequency, not a higher one.

None of the twelve is pre-verified as feasible, and feasibility now means
every one of the parametric-optimization stage's requirements at once --
five static/geometric, the (infinite-life) fatigue criterion, the buckling
limit, the frequency-margin floor, and the process-robustness re-check of
fatigue, buckling, and frequency-margin under the same manufacturing-
tolerance noise the robust-design stage characterizes -- using the same
material and end-fixation selections and the same temperature derating as
that stage, applied per candidate's own listed wire treatment:

  Q1      -- sits at the same (D, Na) as the global cost optimum with wire
             diameter nudged up past the force-delivery cap alone; every
             other requirement, nominal and process-robustness alike, still
             passes comfortably.
  Q2, Q3  -- sit at the cost-minimal (d, D) frontier at Na=9 and Na=11 with
             wire diameter nudged down by 0.008 mm: the *nominal* fatigue
             check still passes, but under the process-robustness noise's
             worst-case (thinner) direction it fails -- a design that looks
             feasible until the same noise the robust-design stage already
             characterizes is actually applied to it.
  Q4, Q5, Q6, Q7 -- the cost-minimal frontier at Na=9, 10.28 (the global
             optimum, Q5), 11, and 12: feasible on every requirement,
             nominal and process-robustness alike, and Pareto-optimal in
             the three-objective sense.
  Q8      -- feasible at the housing-bore limit (D=14) with a large active-
             coil count; costs far more than the frontier above and has a
             far smaller dynamic margin, so it is feasible but strictly
             Pareto-dominated.
  Q9      -- uses the (d, D) that minimizes cost at Na=16 but is reported at
             Na=16.3 without re-optimizing (a plausible supplier-catalog
             slip): fails the force-delivery floor (spring rate is now too
             soft for that d, D) and the process-robustness buckling
             re-check together -- a genuine two-cause failure, not a single
             clean trap, because at this end of the frontier the
             force-delivery and buckling-robustness limits are jointly
             active.
  Q10     -- at the housing-bore limit (D=14, Na=11) with the smallest wire
             diameter that still nominally clears the force, static,
             fatigue, and nominal-fatigue-robustness checks: fails only the
             process-robustness re-check of the frequency-margin floor --
             comfortably clears the *nominal* floor but not its worst-case
             (thinner-wire, higher-Na) noise direction.
  Q11     -- a large active-coil count (Na=22): satisfies the static stress
             and fatigue limits comfortably, but fails the force-delivery
             floor and both the nominal and process-robustness buckling
             checks together, not as three unrelated coincidences -- at this
             coil count, within the stated diameter bounds, the free length
             that would make the spring stiff enough to deliver the required
             force is exactly the free length that is also laterally
             unstable, so no (d, D) at Na=22 can satisfy one without failing
             the other.
  Q12     -- a grossly under-sized, unpeened wire: fails the static stress
             limit, the force-delivery floor, the spring-index
             manufacturability limit, the frequency-margin floor, the
             nominal fatigue criterion, and both of those requirements'
             process-robustness re-checks at once.

Razor's-edge candidates (Q1, Q4-Q8, Q10) are derived programmatically from
the same solver used for the parametric-optimization stage itself, not
hand-typed decimals -- both the global optimum and several of these
candidates sit with two requirements essentially exactly binding at once,
where rounding too coarsely can flip a requirement's margin across zero.
_round() therefore keeps 12 decimal places (not the 9 an earlier version
used): at 9 decimals, Q4/Q5/Q6/Q7/Q8's tightest margins rounded to
-3e-10..-8e-9 (spuriously infeasible under a tight tolerance) even though
the solver's own unrounded output has them at +1e-15..+1e-10 (feasible);
at 12 decimals the rounding error is pushed below the solver's own
convergence floor, so the tightest margins land at -4e-11..+3e-10 --
within the 1e-6 tolerance instruction.md now states explicitly, and also
within a stricter 1e-9 tolerance, consistent with the true optimum.

Deterministic; no random data. Self-checks against tests/ground_truth.json.
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import NonlinearConstraint, brentq, minimize

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = REPO / "environment" / "data" / "pareto_candidate_designs.csv"
TRUTH = REPO / "tests" / "ground_truth.json"

sys.path.insert(0, str(HERE))
from generate_spring_opt import (  # noqa: E402
    BOUNDS, RHO_EFF_SELECTED, cost, g1, g2, g3, g4, g5, g6, g7, g8,
    g9_buckling, g9_fatigue, g9_freq, natural_frequency_hz, solve_reference,
)

F_OPERATING_HZ = 20.0
_BOUNDS_LIST = [tuple(BOUNDS["d_mm"]), tuple(BOUNDS["D_mm"]), tuple(BOUNDS["Na"])]

_LABELS = ["g1", "g2", "g3", "g4", "g5", "g7", "g8", "g6", "g9_fatigue", "g9_buckling", "g9_freq"]


def _full_cons_vec(x, treatment):
    return np.array([
        -g1(x), -g2(x), -g3(x), -g4(x), -g5(x), -g7(x), -g8(x),
        -g6(x, treatment), -g9_fatigue(x, treatment), -g9_buckling(x), -g9_freq(x),
    ])


def _failing(x, treatment, tol=1e-6):
    gs = _full_cons_vec(x, treatment)
    return [_LABELS[i] for i, v in enumerate(gs) if v < -tol]


def _min_cost_at_Na(Na_fixed, treatment, x0):
    """Cost-minimal (d, D) at a fixed active-coil count, against every
    requirement (full precision -- see module docstring)."""
    def cons_vec(x2):
        d, D = x2
        return _full_cons_vec((d, D, Na_fixed), treatment)
    nlc = NonlinearConstraint(cons_vec, 0, np.inf)
    res = minimize(lambda x2: cost((x2[0], x2[1], Na_fixed), treatment), x0, method="trust-constr",
                    bounds=[_BOUNDS_LIST[0], _BOUNDS_LIST[1]], constraints=[nlc],
                    options={"maxiter": 6000, "gtol": 1e-14, "xtol": 1e-15})
    return res.x


def _round(x, n=12):
    return round(float(x), n)


def build_candidates(treatment, best):
    d0, D0, Na0 = best.x

    cands = {}
    cands["Q5"] = (_round(d0), _round(D0), _round(Na0), treatment)

    d_cap = brentq(lambda d: g3((d, D0, Na0)), 0.5, 2.0, xtol=1e-13)
    cands["Q1"] = (_round(d_cap * 1.003), _round(D0), _round(Na0), treatment)

    x0 = np.array([1.6, 10.9])
    frontier = {}
    for Na in (9, 11, 12):
        xy = _min_cost_at_Na(Na, treatment, x0)
        frontier[Na] = xy
        x0 = xy
    d9, D9 = frontier[9]
    d11, D11 = frontier[11]
    d12, D12 = frontier[12]
    cands["Q4"] = (_round(d9), _round(D9), 9, treatment)
    cands["Q6"] = (_round(d11), _round(D11), 11, treatment)
    cands["Q7"] = (_round(d12), _round(D12), 12, treatment)

    cands["Q2"] = (_round(d9 - 0.008), _round(D9), 9, treatment)
    cands["Q3"] = (_round(d11 - 0.008), _round(D11), 11, treatment)

    d_freqok = brentq(lambda d: max(g1((d, 14.0, 10.5)), g2((d, 14.0, 10.5)),
                                     g6((d, 14.0, 10.5), treatment), g9_fatigue((d, 14.0, 10.5), treatment)),
                       0.5, 2.0, xtol=1e-13)
    cands["Q8"] = (_round(d_freqok), 14.0, 10.5, treatment)

    x16 = _min_cost_at_Na(16.0, treatment, np.array([1.6, 11.0]))
    cands["Q9"] = (_round(x16[0]), _round(x16[1]), 16.3, treatment)

    d_freqtrap = brentq(lambda d: max(g1((d, 14.0, 11.0)), g2((d, 14.0, 11.0)),
                                       g6((d, 14.0, 11.0), treatment), g9_fatigue((d, 14.0, 11.0), treatment)),
                         0.5, 2.0, xtol=1e-13)
    cands["Q10"] = (_round(d_freqtrap), 14.0, 11.0, treatment)

    cands["Q11"] = (1.45, 9.0, 22.0, treatment)
    cands["Q12"] = (0.6, 12.0, 8.0, "unpeened")

    return cands


def feasible(d, D, Na, treatment, tol=1e-6):
    # _full_cons_vec returns positive-is-feasible margins (-g_i(x) for each
    # requirement g_i), so feasibility is every entry >= -tol, not <= tol --
    # getting this backwards is the exact sign-confusion bug this project
    # has already been bitten by once (see dataset_manifest.md); _failing
    # above uses the same convention correctly (v < -tol => violated).
    x = (d, D, Na)
    bounds_ok = (BOUNDS["d_mm"][0] <= d <= BOUNDS["d_mm"][1] and
                 BOUNDS["D_mm"][0] <= D <= BOUNDS["D_mm"][1] and
                 BOUNDS["Na"][0] <= Na <= BOUNDS["Na"][1])
    gs = _full_cons_vec(x, treatment)
    return bounds_ok and all(g >= -tol for g in gs)


def check():
    if not OUT.exists() or not TRUTH.exists():
        return False
    with open(OUT, newline="") as fh:
        rows = {r["candidate"]: (float(r["d_mm"]), float(r["D_mm"]), float(r["Na"]), r["treatment"])
                for r in csv.DictReader(fh)}
    if "Q9" not in rows or len(rows) != 12:
        return False
    truth = json.loads(TRUTH.read_text())
    feas_true = truth["pareto_feasible_candidates_true"]
    feas_got = sorted(n for n, (d, D, Na, t) in rows.items() if feasible(d, D, Na, t))
    return feas_got == sorted(feas_true)


def main():
    # Resolve the winning (tempering condition, wire treatment) combination
    # once, up front -- this sets the module-level strength constants g1,
    # g6/g9_fatigue read (via generate_spring_opt's _apply_temper), which
    # check()'s own feasibility recomputation depends on just as much as
    # build_candidates() does.
    treatment, best, _temper_row = solve_reference()

    if check():
        print(f"{OUT} already present and consistent with ground truth; not overwriting")
        return

    cands = build_candidates(treatment, best)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["candidate", "d_mm", "D_mm", "Na", "treatment"])
        for name in sorted(cands, key=lambda n: int(n[1:])):
            d, D, Na, treatment = cands[name]
            w.writerow([name, d, D, Na, treatment])

    for name in sorted(cands, key=lambda n: int(n[1:])):
        d, D, Na, treatment = cands[name]
        feas = feasible(d, D, Na, treatment)
        c = cost((d, D, Na), treatment)
        fn = natural_frequency_hz((d, D, Na), RHO_EFF_SELECTED)
        print(f"{name}: d={d} D={D} Na={Na} treatment={treatment} feasible={feas} "
              f"cost={c:.5f} fn={fn:.3f} margin={fn/F_OPERATING_HZ:.4f} failing={_failing((d, D, Na), treatment)}")
    print(f"wrote {len(cands)} rows to {OUT}")

    if not check():
        raise SystemExit("pareto_candidate_designs.csv FAILED self-check against ground truth")
    print("self-check passed")


if __name__ == "__main__":
    main()
