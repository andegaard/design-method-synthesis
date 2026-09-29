#!/usr/bin/env python3
"""Reference analysis for the design-method-synthesis task.

Carries one spring-loaded latch mechanism through five classical and modern
engineering-design methods -- concept selection, embodiment selection,
parametric optimization, robust design, and multi-criteria final-design
selection -- using standard design-theory and optimization methods:

  [1] Morphological analysis / cross-consistency assessment (Zwicky)
  [2] Axiomatic Design: Independence Axiom (coupling classification) and
      Information Axiom (information content) (Suh)
  [3] Constrained parametric optimization of a helical compression spring
      sized from first-principles spring-design relations (bounded
      multi-start SLSQP)
  [4] Taguchi robust design: signal-to-noise ratio and quality loss
  [5] Multi-objective final-design selection: Pareto dominance, TOPSIS,
      and the weighted-sum method
"""
import itertools
import json
import os
from math import log2
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import NonlinearConstraint, differential_evolution, least_squares, minimize
from scipy.stats import norm

DATA_DIR = Path(os.environ.get("HARBOR_DATA_DIR", "/app/data"))
OUT_DIR = Path(os.environ.get("HARBOR_OUT_DIR", "/app/output"))
OUT_REPORT = OUT_DIR / "design_report.json"
OUT_FINDINGS = OUT_DIR / "findings.md"


def tprint(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------------------
# 1. Morphological analysis
# ---------------------------------------------------------------------------
def analyze_morphological():
    chart = json.loads((DATA_DIR / "morphological_chart.json").read_text())
    sub_functions = chart["sub_functions"]
    excluded = {frozenset(p) for p in chart["excluded_pairs"]}
    keys = list(sub_functions.keys())

    total = 1
    for k in keys:
        total *= len(sub_functions[k])

    feasible = []
    for combo in itertools.product(*[sub_functions[k].keys() for k in keys]):
        pairs = [frozenset(p) for p in itertools.combinations(combo, 2)]
        if any(p in excluded for p in pairs):
            continue
        score = sum(sub_functions[keys[i]][combo[i]]["score"] for i in range(len(keys)))
        feasible.append((score, dict(zip(keys, combo))))
    feasible.sort(key=lambda t: t[0], reverse=True)

    best_score, best_combo = feasible[0]
    return {
        "total_combinations": total,
        "feasible_combinations": len(feasible),
        "best_combination": best_combo,
        "best_score": best_score,
    }


# ---------------------------------------------------------------------------
# 2. Axiomatic design
# ---------------------------------------------------------------------------
def _classify_coupling(matrix, tol=1e-9):
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


def _info_content(lsl, usl, mu, sigma):
    p = norm.cdf((usl - mu) / sigma) - norm.cdf((lsl - mu) / sigma)
    return -log2(p)


def analyze_axiomatic():
    data = json.loads((DATA_DIR / "axiomatic_design_candidates.json").read_text())
    designs = data["designs"]

    coupling = {}
    info_bits = {}
    for name, spec in designs.items():
        c = _classify_coupling(spec["matrix"])
        coupling[name] = c
        # The Independence Axiom is a categorical gate: a coupled design is
        # rejected outright, regardless of how tightly its process data is
        # controlled, so its information content is not part of the
        # Information-Axiom comparison at all.
        if c != "coupled":
            total_I = sum(_info_content(*spec["process_data"][fr]) for fr in ("FR1", "FR2", "FR3"))
            info_bits[name] = total_I

    recommended = min(info_bits, key=info_bits.get)
    return {
        "coupling_by_design": coupling,
        "information_content_bits": {k: round(v, 4) for k, v in info_bits.items()},
        "recommended_design": recommended,
    }


# ---------------------------------------------------------------------------
# 3. Parametric optimization (constrained helical-spring sizing)
# ---------------------------------------------------------------------------
def _wahl(C):
    return (4*C - 1)/(4*C - 4) + 0.615/C


def _spring_f(x, req):
    d, D, Na = x
    return (np.pi**2 / 4.0) * d**2 * D * (Na + 2.0)


def _spring_g1(x, req):
    d, D, Na = x
    C = D / d
    return 8*req["F_op_N"]*D*_wahl(C)/(np.pi*d**3) - req["tau_allow_Nmm2"]


def _spring_g2(x, req):
    d, D, Na = x
    k = req["G_Nmm2"]*d**4/(8*D**3*Na)
    return req["F_op_N"] - k*req["delta_req_mm"]


def _spring_g3(x, req):
    d, D, Na = x
    k = req["G_Nmm2"]*d**4/(8*D**3*Na)
    return k*req["delta_req_mm"] - req["oversupply_factor"]*req["F_op_N"]


def _spring_g4(x, req):
    d, D, Na = x
    return D - req["D_max_mm"]


def _spring_g5(x, req):
    d, D, Na = x
    return D/d - req["spring_index_max"]


def _turner_effective_cte(mat):
    """Turner's model: the composite's homogenized effective CTE, weighting
    each phase's own CTE by its volume fraction and bulk modulus."""
    Vr = mat["reinforcement_vol_fraction"]
    Vm = 1.0 - Vr
    num = (Vm * mat["matrix_K_Nmm2"] * mat["matrix_alpha_per_C"]
           + Vr * mat["reinforcement_K_Nmm2"] * mat["reinforcement_alpha_per_C"])
    den = Vm * mat["matrix_K_Nmm2"] + Vr * mat["reinforcement_K_Nmm2"]
    return num / den


def _thermal_residual_shear_Nmm2(mat, t_process_C, t_ref_C):
    """Thermal residual stress locked into the matrix by the two phases'
    mismatched contraction on cooldown from t_process_C to t_ref_C,
    converted from a normal to a shear-equivalent stress via von Mises."""
    Vr = mat["reinforcement_vol_fraction"]
    sigma_res = ((Vr / (1.0 - Vr)) * mat["matrix_E_Nmm2"]
                 * (mat["matrix_alpha_per_C"] - mat["reinforcement_alpha_per_C"])
                 * (t_process_C - t_ref_C))
    return sigma_res / np.sqrt(3.0)


def _composite_density_kg_m3(mat):
    """Rule-of-mixtures homogenized mass density of the two-phase composite
    wire, weighting each phase's own density by its volume fraction."""
    Vr = mat["reinforcement_vol_fraction"]
    Vm = 1.0 - Vr
    return Vm * mat["matrix_density_kg_m3"] + Vr * mat["reinforcement_density_kg_m3"]


def _natural_frequency_hz(x, rho_kg_m3, G_Nmm2):
    """Fundamental natural frequency of a helical compression spring with
    both ends fixed against rotation (the standard spring-surge check).
    d, D in mm and G in N/mm^2, so the 1e6 factor carries out the mm->m and
    N/mm^2->Pa unit conversions needed to return f_n in Hz."""
    d, D, Na = x
    return 1.0e6 * (2.0 / np.pi) * (d / (Na * D**2)) * np.sqrt(G_Nmm2 / (32.0 * rho_kg_m3))


def _tau_a_allow_basquin(req):
    """Basquin's equation: allowable fully-reversed alternating stress at
    the stated rated qualification cycle count, before the wire-treatment
    multiplier (applied where this is used, same as S_se)."""
    Nc = req["rated_qualification_cycles"]
    return req["basquin_fatigue_strength_coefficient_Nmm2"] * (2.0 * Nc) ** req["basquin_fatigue_strength_exponent"]


def _spring_fatigue_g(x, req, treatment, philosophy="infinite"):
    """Linear mean/alternating shear-stress damage criterion, evaluated for
    the force cycling between F_min_N and F_op_N that the spring actually
    experiences over repeated latch actuation (distinct from the single
    peak-force static check in g1), against temperature-derated,
    treatment-adjusted strengths, with the composite wire's own thermal
    residual shear stress added to the mean stress. philosophy="infinite"
    (the only criterion the minimum-cost design is ever checked against)
    uses the endurance limit S_se; philosophy="finite" (only ever used for
    the frequency-optimized alternative, as a genuine judgment call) uses
    the Basquin-derived allowable at the rated qualification cycle count
    instead, still carrying the treatment's S_se multiplier."""
    d, D, Na = x
    C = D / d
    Kw = _wahl(C)
    Fa = (req["F_op_N"] - req["F_min_N"]) / 2.0
    Fm = (req["F_op_N"] + req["F_min_N"]) / 2.0
    tau_a = 8*Fa*D*Kw/(np.pi*d**3)
    tau_m = 8*Fm*D*Kw/(np.pi*d**3) + req["tau_res_Nmm2"]
    derate = 1.0 - req["strength_derating_fraction_per_C"] * (req["operating_temp_C"] - req["material_reference_temp_C"])
    S_su = req["S_su_base_Nmm2"] * derate
    if philosophy == "infinite":
        allow_a = req["S_se_base_Nmm2"] * derate * req["treatment_S_se_mult"]
    else:
        allow_a = _tau_a_allow_basquin(req) * req["treatment_S_se_mult"]
    return tau_a/allow_a + tau_m/S_su - 1.0/req["fatigue_safety_factor"]


def _spring_g6(x, req, treatment):
    """Infinite-life fatigue criterion -- the only one the minimum-cost
    design is ever checked against."""
    return _spring_fatigue_g(x, req, treatment, philosophy="infinite")


def _spring_g7(x, req):
    """Lateral-buckling slenderness limit for the selected end-fixation."""
    d, D, Na = x
    Ls = (Na + 2.0)*d
    L0 = Ls + req["delta_req_mm"] + req["clash_allowance_mm"]
    return L0/D - req["buckling_limit"]


def _spring_g8(x, req):
    """Fundamental-natural-frequency floor against spring surge."""
    fn = _natural_frequency_hz(x, req["composite_density_kg_m3"], req["G_Nmm2"])
    floor = req["frequency_safety_margin"] * req["operating_actuation_frequency_hz"]
    return floor - fn


def _spring_frequency_margin_ratio(x, req):
    fn = _natural_frequency_hz(x, req["composite_density_kg_m3"], req["G_Nmm2"])
    return fn / req["operating_actuation_frequency_hz"]


def _derive_process_noise(df, e_level, G=80000.0):
    """Recover the Taguchi robust-design study's own wire-diameter and
    active-coil manufacturing-tolerance noise magnitudes directly from
    taguchi_spring_robustness.csv -- the noise is never restated as a
    number anywhere else. Each run's 'low'/'high' rows share the same two
    (unknown) offsets from that run's own nominal d and N (mean coil
    diameter D is unperturbed, per that stage's own data), so pooling every
    run's 'low' rows -- and, separately, every run's 'high' rows -- gives an
    over-determined nonlinear least-squares fit for the shared offsets,
    using the same spring-rate relation and reference shear modulus G that
    stage's own analysis uses.

    The offsets are not shared across the whole array: they scale with the
    run's forming-setup level (E), so the fit is restricted to the runs at
    the E level the robust-design stage recommends -- that setup is the
    process the downstream stages are qualified against."""
    df = df[df["E_level"] == e_level]

    def resid(params, rows):
        dd, dn = params
        out = []
        for d_nom, D_nom, N_nom, k_obs in rows:
            k_pred = G * (d_nom + dd)**4 / (8 * D_nom**3 * (N_nom + dn))
            out.append(k_pred - k_obs)
        return out

    def rows_for(condition):
        sub = df[df["noise_condition"] == condition]
        return list(zip(sub["d_nominal_mm"], sub["D_nominal_mm"], sub["N_nominal"], sub["spring_rate_k_Nmm"]))

    dd_low, dn_low = least_squares(resid, x0=[-0.01, -0.1], args=(rows_for("low"),)).x
    dd_high, dn_high = least_squares(resid, x0=[0.01, 0.1], args=(rows_for("high"),)).x
    dd_mag = (abs(dd_low) + abs(dd_high)) / 2.0
    dn_mag = (abs(dn_low) + abs(dn_high)) / 2.0
    return dd_mag, dn_mag


def _recommended_setup_level(df):
    """The forming-setup (E) level the robust-design stage recommends: the
    level with the highest average signal-to-noise ratio."""
    sn = {}
    for run_id, grp in df.groupby("run_id"):
        ks = grp["spring_rate_k_Nmm"].values
        sn[int(run_id)] = 10 * np.log10(ks.mean()**2 / ks.var(ddof=1))
    e_of_run = df.groupby("run_id")["E_level"].first()
    avg = {int(l): np.mean([sn[int(r)] for r in e_of_run.index[e_of_run == l]])
           for l in sorted(e_of_run.unique())}
    return int(max(avg, key=avg.get))


def _spring_g9_fatigue(x, req, treatment, dd, philosophy="infinite"):
    """Process-robustness re-check of the fatigue criterion: worst-case
    direction is a thinner wire (raises both shear-stress components; Na
    does not enter the fatigue relation, so the active-coil noise is
    irrelevant here)."""
    d, D, Na = x
    return _spring_fatigue_g((d - dd, D, Na), req, treatment, philosophy=philosophy)


def _spring_g9_buckling(x, req, dd, dn):
    """Process-robustness re-check of the buckling limit: worst-case
    direction is a thicker wire together with more active coils (both raise
    the free length)."""
    d, D, Na = x
    return _spring_g7((d + dd, D, Na + dn), req)


def _spring_g9_freq(x, req, dd, dn):
    """Process-robustness re-check of the frequency floor: f_n increases
    with d and decreases with Na, so the worst case is a thinner wire
    together with more active coils -- the opposite d-direction from the
    fatigue re-check above."""
    d, D, Na = x
    return _spring_g8((d - dd, D, Na + dn), req)


_SPRING_CONSTRAINTS_STATIC = (_spring_g1, _spring_g2, _spring_g3, _spring_g4, _spring_g5, _spring_g7, _spring_g8)
_SPRING_CONSTRAINTS_NO_FREQ = (_spring_g1, _spring_g2, _spring_g3, _spring_g4, _spring_g5, _spring_g7)


def _spring_cost(x, req, cost_mult):
    d, D, Na = x
    vol = (np.pi**2 / 4.0) * d**2 * D * (Na + 2.0)
    return vol * cost_mult


def _full_cons_vec(x, req, treatment, dd, dn, philosophy="infinite", include_freq_floor=True):
    """Positive-is-feasible margins for every requirement: five
    static/geometric, the (chosen-philosophy) fatigue criterion, buckling,
    and -- unless include_freq_floor is False, for the frequency-optimized
    alternative -- the frequency floor, each followed by its
    process-robustness re-check (fatigue and buckling always; the frequency
    floor's re-check only when the floor itself is included)."""
    out = [-_spring_g1(x, req), -_spring_g2(x, req), -_spring_g3(x, req), -_spring_g4(x, req),
           -_spring_g5(x, req), -_spring_g7(x, req),
           -_spring_fatigue_g(x, req, treatment, philosophy=philosophy),
           -_spring_g9_fatigue(x, req, treatment, dd, philosophy=philosophy),
           -_spring_g9_buckling(x, req, dd, dn)]
    if include_freq_floor:
        out += [-_spring_g8(x, req), -_spring_g9_freq(x, req, dd, dn)]
    return np.array(out)


def _feasibility_violation(x, req, treatment, dd, dn, philosophy="infinite", include_freq_floor=True):
    gs = _full_cons_vec(x, req, treatment, dd, dn, philosophy=philosophy, include_freq_floor=include_freq_floor)
    return float(np.sum(np.clip(-gs, 0.0, None)))


def _solve_min_cost(req, treatment, spec, bounds, dd, dn, seed=5):
    """Independently re-solve the minimum-cost design for one wire
    treatment against every requirement (nominal + process-robustness,
    infinite-life fatigue only): a differential-evolution feasibility
    search locates a feasible seed, then trust-constr refines it to the
    true constrained optimum. Plain SLSQP multistart is not reliable on
    this tightly-constrained problem (two requirements bind at once at the
    true optimum), which is why this stage uses a different strategy from
    the axiomatic/morphological stages above."""
    treq = dict(req, treatment_S_se_mult=spec["S_se_multiplier"])

    def viol(x):
        return _feasibility_violation(x, treq, treatment, dd, dn)

    de_res = differential_evolution(viol, bounds=bounds, seed=seed, tol=1e-12, maxiter=800, popsize=30, polish=True)
    if viol(de_res.x) > 1e-6:
        return None
    nlc = NonlinearConstraint(lambda x: _full_cons_vec(x, treq, treatment, dd, dn), 0, np.inf)
    res = minimize(lambda x: _spring_cost(x, treq, spec["relative_cost_multiplier"]), de_res.x,
                    method="trust-constr", bounds=bounds, constraints=[nlc],
                    options={"maxiter": 8000, "gtol": 1e-13, "xtol": 1e-15})
    if not res.success or viol(res.x) > 1e-6:
        return None
    return res


def _solve_freq_alternative(req, treatment, spec, bounds, dd, dn, philosophy, cost_cap):
    """Maximize the fundamental natural frequency subject to every
    requirement except the frequency floor and its process-robustness
    re-check, a cap on cost, and the stated fatigue-life philosophy."""
    treq = dict(req, treatment_S_se_mult=spec["S_se_multiplier"])

    def cons_vec(x):
        base = _full_cons_vec(x, treq, treatment, dd, dn, philosophy=philosophy, include_freq_floor=False)
        return np.append(base, cost_cap - _spring_cost(x, treq, spec["relative_cost_multiplier"]))

    def viol(x):
        return float(np.sum(np.clip(-cons_vec(x), 0.0, None)))

    nlc = NonlinearConstraint(cons_vec, 0, np.inf)
    starts = [np.array([1.5, 13.0, 3.0]), np.array([1.6, 14.0, 4.0]), np.array([1.4, 10.0, 6.0]),
              np.array([1.8, 14.0, 3.0]), np.array([1.55, 14.0, 5.0]), np.array([1.45, 14.0, 4.5])]
    best = None
    for x0 in starts:
        res = minimize(lambda x: -_natural_frequency_hz(x, req["composite_density_kg_m3"], req["G_Nmm2"]), x0,
                        method="trust-constr", bounds=bounds, constraints=[nlc],
                        options={"maxiter": 8000, "gtol": 1e-13, "xtol": 1e-15})
        if not res.success or viol(res.x) > 1e-6:
            continue
        fn = _natural_frequency_hz(res.x, req["composite_density_kg_m3"], req["G_Nmm2"])
        if best is None or fn > _natural_frequency_hz(best.x, req["composite_density_kg_m3"], req["G_Nmm2"]):
            best = res
    return best


def _de_cross_check_min_cost(req, treatment, spec, bounds, dd, dn, cost_star, seed=23):
    """Independent differential-evolution solve of the actual minimum-cost
    objective (not just a feasibility search that then hands off to
    trust-constr, as _solve_min_cost above does): minimizes cost plus a
    large penalty for constraint violation directly, with its own seed
    (deliberately different from _solve_min_cost's own DE warm-start seed
    and from the authoring generator's cross-check seed), and confirms it
    lands close to the trust-constr optimum. A genuinely separate
    solver/search strategy, not a second call to the same routine."""
    treq = dict(req, treatment_S_se_mult=spec["S_se_multiplier"])

    def penalized(x):
        v = _feasibility_violation(x, treq, treatment, dd, dn)
        return _spring_cost(x, treq, spec["relative_cost_multiplier"]) + 1.0e4 * v

    res = differential_evolution(penalized, bounds=bounds, seed=seed, tol=1e-10, maxiter=600, popsize=40, polish=True)
    if _feasibility_violation(res.x, treq, treatment, dd, dn) > 1e-4:
        return False
    cost_found = _spring_cost(res.x, treq, spec["relative_cost_multiplier"])
    return abs(cost_found - cost_star) <= 0.03 * cost_star


def _de_cross_check_freq_alt(req, treatment, spec, bounds, dd, dn, philosophy, cost_cap, fn_star, seed=23):
    """Independent differential-evolution solve of the frequency-optimized
    alternative's actual objective (maximize f_n), penalized for constraint
    and cost-cap violation, confirming it lands close to the multistart
    trust-constr optimum _solve_freq_alternative found."""
    treq = dict(req, treatment_S_se_mult=spec["S_se_multiplier"])

    def penalized(x):
        v = _feasibility_violation(x, treq, treatment, dd, dn, philosophy=philosophy, include_freq_floor=False)
        v += max(0.0, _spring_cost(x, treq, spec["relative_cost_multiplier"]) - cost_cap) / max(cost_cap, 1.0)
        return -_natural_frequency_hz(x, req["composite_density_kg_m3"], req["G_Nmm2"]) + 1.0e5 * v

    res = differential_evolution(penalized, bounds=bounds, seed=seed, tol=1e-10, maxiter=600, popsize=40, polish=True)
    total_viol = _feasibility_violation(res.x, treq, treatment, dd, dn, philosophy=philosophy, include_freq_floor=False)
    total_viol += max(0.0, _spring_cost(res.x, treq, spec["relative_cost_multiplier"]) - cost_cap)
    if total_viol > 1e-3:
        return False
    fn_found = _natural_frequency_hz(res.x, req["composite_density_kg_m3"], req["G_Nmm2"])
    return abs(fn_found - fn_star) <= 0.03 * fn_star


def analyze_parametric_optimization(morph):
    problem = json.loads((DATA_DIR / "spring_optimization_problem.json").read_text())
    material = problem["material_options"][morph["best_combination"]["material"]]
    buckling_limit = problem["end_fixation_buckling_limits"][morph["best_combination"]["end_fixation"]]
    alpha_eff = _turner_effective_cte(material)
    tau_res = _thermal_residual_shear_Nmm2(
        material, problem["requirements"]["composite_process_temp_C"],
        problem["requirements"]["material_reference_temp_C"])
    rho_eff = _composite_density_kg_m3(material)
    req_base = dict(problem["requirements"])
    req_base.update({
        "G_Nmm2": material["G_Nmm2"], "buckling_limit": buckling_limit,
        "tau_res_Nmm2": tau_res, "composite_density_kg_m3": rho_eff,
    })

    # Process-robustness noise: recovered from the robust-design stage's own
    # raw measurements, not restated anywhere in spring_optimization_problem.json.
    df_taguchi = pd.read_csv(DATA_DIR / "taguchi_spring_robustness.csv")
    dd, dn = _derive_process_noise(df_taguchi, _recommended_setup_level(df_taguchi))

    bounds_d = tuple(problem["bounds"]["d_mm"])
    bounds_D = tuple(problem["bounds"]["D_mm"])
    bounds_Na = tuple(problem["bounds"]["Na"])
    bounds = [bounds_d, bounds_D, bounds_Na]

    # The selected material's own strength properties are not given directly
    # (unlike G above) -- they must be read off whichever row of
    # tempering_response clears the stated minimum Charpy toughness and,
    # jointly with a wire-treatment choice, gives the global minimum-cost
    # design. Two rows -- the lowest-temper one and one inside this alloy's
    # tempered-martensite-embrittlement band -- fail that toughness floor
    # despite each looking cheaper than the true winner on strength alone
    # (higher allowable/fatigue strength permits a smaller, cheaper spring),
    # so every (eligible row, treatment) combination must actually be solved
    # and compared, not shortcut by picking the strongest-looking row.
    charpy_floor = req_base["charpy_min_toughness_J"]
    eligible_rows = [r for r in problem["tempering_response"] if r["charpy_impact_J"] >= charpy_floor]

    candidates = {}
    for row in eligible_rows:
        req_row = dict(req_base, S_se_base_Nmm2=row["S_se_base_Nmm2"],
                       S_su_base_Nmm2=row["S_su_Nmm2"], tau_allow_Nmm2=row["tau_allow_Nmm2"])
        for treatment, spec in problem["wire_treatments"].items():
            best = _solve_min_cost(req_row, treatment, spec, bounds, dd, dn)
            if best is not None:
                candidates[(row["temper_temp_C"], treatment)] = (best, row, req_row)

    winner_key = min(candidates, key=lambda k: candidates[k][0].fun)
    temper_temp_C, winner = winner_key
    best, winner_row, req = candidates[winner_key]
    d, D, Na = best.x
    winner_spec = problem["wire_treatments"][winner]
    fn = _natural_frequency_hz(best.x, rho_eff, req["G_Nmm2"])
    freq_margin = fn / req["operating_actuation_frequency_hz"]

    # Genuinely independent second solve of the actual objective (not the
    # feasibility-search warm start _solve_min_cost's own DE call already
    # performs), with its own seed, confirming the trust-constr optimum
    # above is not an artifact of that one solver/seed combination.
    assert _de_cross_check_min_cost(req, winner, winner_spec, bounds, dd, dn, best.fun), (
        "independent differential-evolution cross-check of the minimum-cost "
        "design disagrees with the trust-constr optimum")

    # Frequency-optimized alternative: maximize f_n subject to every
    # requirement except the frequency floor itself (and its
    # process-robustness re-check), using the same treatment as the
    # cost-optimal design, with cost capped at a multiple of the
    # cost-optimal design's own cost. Which fatigue-life criterion governs
    # this alternative is a genuine judgment call (see requirements_text in
    # the data file) -- this reference solution uses the finite-life
    # (Basquin, rated-qualification-cycle) criterion, since this
    # alternative is explicitly being explored to see how much dynamic
    # margin is purchasable within the cost cap, i.e. it is a
    # performance-oriented design being qualified against a stated duty
    # cycle rather than shipped as the always-on, unbounded-life baseline
    # (that role stays with the minimum-cost design above, which always
    # uses the infinite-life criterion).
    philosophy = "finite_life"
    cost_cap = req["frequency_alternative_cost_cap_multiplier"] * best.fun
    best_alt = _solve_freq_alternative(req, winner, winner_spec, bounds, dd, dn,
                                        "finite" if philosophy == "finite_life" else "infinite", cost_cap)
    d_alt, D_alt, Na_alt = best_alt.x
    cost_alt = _spring_cost(best_alt.x, req, winner_spec["relative_cost_multiplier"])
    fn_alt = _natural_frequency_hz(best_alt.x, rho_eff, req["G_Nmm2"])
    alt_differs = not (abs(d_alt - d) < 1e-4 and abs(D_alt - D) < 1e-4 and abs(Na_alt - Na) < 1e-4)

    assert _de_cross_check_freq_alt(
        req, winner, winner_spec, bounds, dd, dn,
        "finite" if philosophy == "finite_life" else "infinite", cost_cap, fn_alt,
    ), ("independent differential-evolution cross-check of the "
        "frequency-optimized alternative disagrees with the multistart trust-constr optimum")

    param_opt = {
        "d_mm": round(float(d), 6),
        "D_mm": round(float(D), 6),
        "Na": round(float(Na), 6),
        "cost": round(float(best.fun), 8),
        "treatment": winner,
        "temper_temp_C": temper_temp_C,
        "constraints_satisfied": True,
        "composite_cte_eff_per_C": alpha_eff,
        "composite_density_kg_m3": round(float(rho_eff), 4),
        "natural_frequency_hz": round(float(fn), 6),
        "frequency_margin_ratio": round(float(freq_margin), 6),
        "frequency_optimized_alternative": {
            "d_mm": round(float(d_alt), 6),
            "D_mm": round(float(D_alt), 6),
            "Na": round(float(Na_alt), 6),
            "cost": round(float(cost_alt), 8),
            "natural_frequency_hz": round(float(fn_alt), 6),
            "frequency_margin_ratio": round(float(fn_alt / req["operating_actuation_frequency_hz"]), 6),
        },
        "frequency_alternative_differs_from_cost_optimum": bool(alt_differs),
        "frequency_alternative_fatigue_philosophy": philosophy,
    }
    # winner_row carries the strength properties (S_su/S_se_base/tau_allow)
    # this same tempering condition implies, for analyze_pareto to reuse --
    # the final-candidate screen re-derives feasibility against the same
    # already-fixed material and heat-treatment choice this stage made, the
    # same way it already reuses the fixed material and end-fixation choice.
    return param_opt, winner_row


# ---------------------------------------------------------------------------
# 4. Taguchi robust design
# ---------------------------------------------------------------------------
def analyze_taguchi():
    df = pd.read_csv(DATA_DIR / "taguchi_spring_robustness.csv")

    sn_by_run = {}
    mean_k_by_run = {}
    levels_by_run = {}
    for run_id, grp in df.groupby("run_id"):
        ks = grp["spring_rate_k_Nmm"].values
        mean_k, var_k = ks.mean(), ks.var(ddof=1)
        sn_by_run[int(run_id)] = float(10*np.log10(mean_k**2/var_k))
        mean_k_by_run[int(run_id)] = float(mean_k)
        row0 = grp.iloc[0]
        levels_by_run[int(run_id)] = {"A": int(row0["A_level"]), "B": int(row0["B_level"]),
                                       "C": int(row0["C_level"]), "E": int(row0["E_level"])}

    factor_level_avg = {}
    for factor in ("A", "B", "C", "E"):
        avgs = {}
        for lvl in (1, 2, 3):
            runs = [rid for rid, lv in levels_by_run.items() if lv[factor] == lvl]
            avgs[str(lvl)] = float(np.mean([sn_by_run[rid] for rid in runs]))
        factor_level_avg[factor] = avgs

    most_robust_levels = {f: int(max(factor_level_avg[f], key=factor_level_avg[f].get))
                           for f in ("A", "B", "C", "E")}

    A_LEVELS = {1: 1.2, 2: 1.4, 3: 1.6}
    B_LEVELS = {1: 10.0, 2: 12.0, 3: 14.0}
    C_LEVELS = {1: 8, 2: 10, 3: 12}
    G = 80000.0
    d = A_LEVELS[most_robust_levels["A"]]
    D = B_LEVELS[most_robust_levels["B"]]
    N = C_LEVELS[most_robust_levels["C"]]
    k_pred = G * d**4 / (8 * D**3 * N)

    T = 6.0
    A0, delta0 = 2.5, 1.0
    k_loss = A0 / delta0**2
    most_robust_loss = k_loss * (k_pred - T)**2

    losses_by_run = {rid: k_loss*(mk-T)**2 for rid, mk in mean_k_by_run.items()}
    best_on_target_run = min(losses_by_run, key=losses_by_run.get)

    most_robust_equals_best_on_target = (
        levels_by_run[best_on_target_run] == most_robust_levels
    )

    return {
        "sn_by_run_db": {str(k): round(v, 3) for k, v in sn_by_run.items()},
        "factor_level_sn_avg_db": {f: {lvl: round(v, 3) for lvl, v in avgs.items()}
                                    for f, avgs in factor_level_avg.items()},
        "most_robust_levels": most_robust_levels,
        "most_robust_predicted_k_Nmm": round(k_pred, 4),
        "most_robust_quality_loss": round(most_robust_loss, 4),
        "best_on_target_run_id": int(best_on_target_run),
        "best_on_target_levels": levels_by_run[best_on_target_run],
        "best_on_target_quality_loss": round(losses_by_run[best_on_target_run], 4),
        "most_robust_equals_best_on_target": bool(most_robust_equals_best_on_target),
    }


# ---------------------------------------------------------------------------
# 5. Multi-objective final-design selection (Pareto / TOPSIS / weighted sum)
# ---------------------------------------------------------------------------
def analyze_pareto(morph, temper_row):
    problem = json.loads((DATA_DIR / "spring_optimization_problem.json").read_text())
    material = problem["material_options"][morph["best_combination"]["material"]]
    buckling_limit = problem["end_fixation_buckling_limits"][morph["best_combination"]["end_fixation"]]
    tau_res = _thermal_residual_shear_Nmm2(
        material, problem["requirements"]["composite_process_temp_C"],
        problem["requirements"]["material_reference_temp_C"])
    rho_eff = _composite_density_kg_m3(material)
    req = dict(problem["requirements"])
    req.update({
        # Reuses the same tempering condition the parametric-optimization
        # stage already selected (see analyze_parametric_optimization) --
        # not re-decided per final candidate, the same way material and
        # end-fixation are fixed once by the concept-selection stage.
        "S_se_base_Nmm2": temper_row["S_se_base_Nmm2"], "S_su_base_Nmm2": temper_row["S_su_Nmm2"],
        "tau_allow_Nmm2": temper_row["tau_allow_Nmm2"], "G_Nmm2": material["G_Nmm2"],
        "buckling_limit": buckling_limit, "tau_res_Nmm2": tau_res,
        "composite_density_kg_m3": rho_eff,
    })
    treatments = problem["wire_treatments"]
    df = pd.read_csv(DATA_DIR / "pareto_candidate_designs.csv")

    df_taguchi = pd.read_csv(DATA_DIR / "taguchi_spring_robustness.csv")
    dd, dn = _derive_process_noise(df_taguchi, _recommended_setup_level(df_taguchi))

    def feasible(row):
        d, D, Na = row["d_mm"], row["D_mm"], row["Na"]
        treq = dict(req, treatment_S_se_mult=treatments[row["treatment"]]["S_se_multiplier"])
        gs = _full_cons_vec((d, D, Na), treq, row["treatment"], dd, dn)
        bounds_ok = 0.5 <= d <= 2.0 and 4.0 <= D <= 14.0 and 2.0 <= Na <= 30.0
        return bool(np.all(gs >= -1e-6)) and bounds_ok

    def row_cost(row):
        return _spring_cost((row["d_mm"], row["D_mm"], row["Na"]), req,
                             treatments[row["treatment"]]["relative_cost_multiplier"])

    def row_freq_margin(row):
        return _spring_frequency_margin_ratio((row["d_mm"], row["D_mm"], row["Na"]), req)

    df["feasible"] = df.apply(feasible, axis=1)
    df["cost"] = df.apply(row_cost, axis=1)
    df["freq_margin"] = df.apply(row_freq_margin, axis=1)
    feas = df[df["feasible"]].copy()

    def dominates(a, b):
        # Three objectives: minimize cost, maximize Na (durability), and
        # maximize freq_margin (dynamic/surge safety margin).
        not_worse = (a["cost"] <= b["cost"]) and (a["Na"] >= b["Na"]) and (a["freq_margin"] >= b["freq_margin"])
        strictly = (a["cost"] < b["cost"]) or (a["Na"] > b["Na"]) or (a["freq_margin"] > b["freq_margin"])
        return not_worse and strictly

    pareto_names = []
    for _, row in feas.iterrows():
        if not any(dominates(orow, row) for _, orow in feas.iterrows()
                   if orow["candidate"] != row["candidate"]):
            pareto_names.append(row["candidate"])

    pset = feas[feas["candidate"].isin(pareto_names)].reset_index(drop=True)
    # Stated weights (instruction.md): cost 0.45, durability (Na) 0.35,
    # dynamic/frequency margin 0.20 -- cost remains the primary criterion,
    # matching the parametric-optimization stage's own objective, with
    # durability weighted above the dynamic-margin check.
    w_cost, w_dur, w_freq = 0.45, 0.35, 0.20
    costs = pset["cost"].values
    Ns = pset["Na"].values
    fms = pset["freq_margin"].values

    costs_n = costs / np.sqrt((costs**2).sum())
    Ns_n = Ns / np.sqrt((Ns**2).sum())
    fms_n = fms / np.sqrt((fms**2).sum())
    costs_w = costs_n * w_cost
    Ns_w = Ns_n * w_dur
    fms_w = fms_n * w_freq
    ideal = np.array([costs_w.min(), Ns_w.max(), fms_w.max()])
    anti = np.array([costs_w.max(), Ns_w.min(), fms_w.min()])
    s_plus = np.sqrt((costs_w - ideal[0])**2 + (Ns_w - ideal[1])**2 + (fms_w - ideal[2])**2)
    s_minus = np.sqrt((costs_w - anti[0])**2 + (Ns_w - anti[1])**2 + (fms_w - anti[2])**2)
    topsis_p = s_minus / (s_plus + s_minus)
    topsis_winner = pset["candidate"].iloc[int(np.argmax(topsis_p))]

    cost_norm = (costs.max() - costs) / (costs.max() - costs.min())
    N_norm = (Ns - Ns.min()) / (Ns.max() - Ns.min())
    fm_norm = (fms - fms.min()) / (fms.max() - fms.min())
    ws_score = w_cost * cost_norm + w_dur * N_norm + w_freq * fm_norm
    ws_winner = pset["candidate"].iloc[int(np.argmax(ws_score))]

    return {
        "feasible_candidates": sorted(feas["candidate"].tolist()),
        "pareto_optimal_candidates": sorted(pareto_names),
        "topsis_winner": topsis_winner,
        "weighted_sum_winner": ws_winner,
        "methods_agree": bool(topsis_winner == ws_winner),
    }


# ---------------------------------------------------------------------------
# 6. Cross-stage synthesis
# ---------------------------------------------------------------------------
def synthesize(morph, axio, param_opt, taguchi, pareto):
    if pareto["methods_agree"]:
        final_design = pareto["weighted_sum_winner"]
        pareto_sentence = (
            "both TOPSIS and the weighted-sum method independently agree that "
            f"{final_design} is the best compromise among cost, durability, and dynamic margin."
        )
    else:
        # TOPSIS and the weighted-sum method disagree on this three-objective
        # Pareto front. TOPSIS is taken as authoritative here: the
        # weighted-sum method's min-max normalization rescales each of the
        # three objectives independently over its own range before applying
        # the stated weights, which lets a candidate that is merely extreme
        # on the two most heavily weighted objectives (cost and dynamic
        # margin, 0.65 of the total weight combined) win outright even
        # though it is not the front's most balanced design overall; TOPSIS's
        # geometric distance to the ideal and anti-ideal points weighs a
        # design's standing across all three normalized objectives jointly,
        # rather than crediting strength on two axes independently of a
        # weakness on the third.
        final_design = pareto["topsis_winner"]
        pareto_sentence = (
            f"TOPSIS and the weighted-sum method disagree here -- TOPSIS favors "
            f"{pareto['topsis_winner']} while the weighted-sum method favors "
            f"{pareto['weighted_sum_winner']} -- and TOPSIS's winner is carried "
            "forward, since the weighted-sum method's per-criterion min-max "
            "normalization lets a design that is merely extreme on the two most "
            "heavily weighted objectives outscore a more balanced design across "
            "all three, whereas TOPSIS's geometric-distance ranking weighs a "
            "design's standing on every normalized objective jointly."
        )

    freq_alt = param_opt["frequency_optimized_alternative"]
    philosophy = param_opt["frequency_alternative_fatigue_philosophy"]
    philosophy_word = "finite" if philosophy == "finite_life" else "infinite"
    philosophy_sentence = (
        f"a {philosophy_word}-life fatigue-life criterion governs this alternative "
        + ("(Basquin's equation at the stated rated qualification cycle count) "
           if philosophy_word == "finite" else
           "(the same endurance-limit criterion the minimum-cost design uses) ")
        + ("since it is being explored specifically to see how much dynamic margin is "
           "purchasable within the cost cap -- a performance-oriented design worth "
           "qualifying against a stated duty cycle rather than assuming unbounded service "
           "life"
           if philosophy_word == "finite" else
           "to keep this alternative's own fatigue margin on the same conservative, "
           "unbounded-life footing as the minimum-cost design, rather than trading it away "
           "for additional dynamic margin")
    )
    if param_opt["frequency_alternative_differs_from_cost_optimum"]:
        freq_alt_sentence = (
            f"a separate frequency-optimized alternative (d={freq_alt['d_mm']}, "
            f"D={freq_alt['D_mm']}, N={freq_alt['Na']}, cost={freq_alt['cost']}, "
            f"natural frequency={freq_alt['natural_frequency_hz']} Hz) is a genuinely "
            "different design from the minimum-cost one, showing that minimizing cost "
            "and maximizing dynamic (surge) margin are competing objectives here, not "
            f"the same design under two names; {philosophy_sentence}"
        )
    else:
        freq_alt_sentence = (
            "the frequency-optimized alternative coincides with the minimum-cost "
            f"design itself, so minimizing cost already maximizes dynamic margin here; "
            f"{philosophy_sentence}"
        )

    explanation = (
        "Morphological analysis over the 108-combination chart, after excluding the "
        "incompatible sub-function pairings, identifies {combo} as the unique highest-"
        "scoring feasible concept (score {score} of {feas} feasible combinations). At the "
        "embodiment stage, Axiomatic Design first applies the Independence Axiom as a "
        "categorical gate: design Y is fully coupled and is rejected outright regardless "
        "of its information content, leaving X (decoupled) and Z (uncoupled) as the only "
        "candidates the Information Axiom may choose between. Design {axio_rec} carries "
        "the lower total information content ({axio_bits} bits) and is recommended. "
        "Constrained parametric optimization of the latch spring, using the material and "
        "end-fixation the concept-selection stage chose, gives a minimum-cost design "
        "(d={d}, D={D}, N={N}, treatment={treatment}, tempered at {temper} C) that satisfies "
        "every static, fatigue -- including the composite wire's own thermal residual stress "
        "from constituent CTE mismatch, on top of the cyclic service load -- buckling, and "
        "natural-frequency (surge-margin) requirement; that tempering condition is the "
        "cheapest of the ones clearing the stated minimum Charpy toughness, jointly with the "
        "wire-treatment choice, not the highest-strength condition outright. The wire's Turner-model effective "
        "CTE is {cte} per degree C and its rule-of-mixtures density is {rho} kg/m^3, giving "
        "a fundamental natural frequency of {fn} Hz against the required floor. Optimizing "
        "instead for dynamic margin, {freq_alt_sentence}. Of the catalog-constrained final "
        "candidates, screened against cost, durability, and dynamic margin together, Pareto "
        "dominance leaves {n_pareto} non-dominated options, and {pareto_sentence} "
        "Separately, a Taguchi robust-design study on the same spring family shows that "
        "maximizing the signal-to-noise ratio (most robust: levels {rob_levels}) does not "
        "select the same combination as minimizing quality loss against the target spring "
        "rate (best on-target: run {run_id}) -- robustness to noise and being on-target "
        "are different objectives, and this design does not achieve both at once."
    ).format(
        combo="-".join(morph["best_combination"].values()), score=morph["best_score"],
        feas=morph["feasible_combinations"], axio_rec=axio["recommended_design"],
        axio_bits=axio["information_content_bits"][axio["recommended_design"]],
        d=param_opt["d_mm"], D=param_opt["D_mm"], N=param_opt["Na"], treatment=param_opt["treatment"],
        temper=param_opt["temper_temp_C"],
        cte=param_opt["composite_cte_eff_per_C"], rho=param_opt["composite_density_kg_m3"],
        fn=param_opt["natural_frequency_hz"], freq_alt_sentence=freq_alt_sentence,
        n_pareto=len(pareto["pareto_optimal_candidates"]), pareto_sentence=pareto_sentence,
        rob_levels=taguchi["most_robust_levels"], run_id=taguchi["best_on_target_run_id"],
    )

    return {
        "recommended_concept": morph["best_combination"],
        "recommended_embodiment": axio["recommended_design"],
        "recommended_final_design": final_design,
        "robustness_and_on_target_are_different": not taguchi["most_robust_equals_best_on_target"],
        "explanation": explanation,
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    tprint("running morphological analysis ...")
    morph = analyze_morphological()
    tprint("running axiomatic design analysis ...")
    axio = analyze_axiomatic()
    tprint("running constrained parametric optimization ...")
    param_opt, temper_row = analyze_parametric_optimization(morph)
    tprint("running Taguchi robust-design analysis ...")
    taguchi = analyze_taguchi()
    tprint("running multi-objective final-design selection ...")
    pareto = analyze_pareto(morph, temper_row)
    tprint("building cross-stage synthesis ...")
    synth = synthesize(morph, axio, param_opt, taguchi, pareto)

    report = {
        "morphological": morph,
        "axiomatic": axio,
        "parametric_optimization": param_opt,
        "taguchi": taguchi,
        "pareto": pareto,
        "synthesis": synth,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_REPORT, "w") as fh:
        json.dump(report, fh, indent=2)

    findings = f"""# Findings: Multi-Method Design Synthesis for a Latch Spring

## 1. Concept selection (morphological analysis)

{morph['feasible_combinations']} of {morph['total_combinations']} combinations in the
morphological chart are feasible once the pairwise incompatibilities are excluded. The
highest-scoring feasible concept is **{"-".join(morph['best_combination'].values())}**
(score {morph['best_score']}).

## 2. Embodiment selection (axiomatic design)

Coupling classification: {axio['coupling_by_design']}. Design Y is coupled and is
rejected under the Independence Axiom regardless of its information content. Between the
two Independence-compliant designs, total information content is
{axio['information_content_bits']} bits; **{axio['recommended_design']}** is recommended
under the Information Axiom.

## 3. Parametric optimization

The constrained-optimization stage's minimum-cost design uses {param_opt['treatment']} wire
tempered at {param_opt['temper_temp_C']} C (the cheapest tempering condition clearing the
stated minimum Charpy toughness, jointly with the wire-treatment choice):
d={param_opt['d_mm']}, D={param_opt['D_mm']}, Na={param_opt['Na']}
(cost={param_opt['cost']}), with every static, fatigue, buckling, and natural-frequency
(surge-margin) requirement satisfied. The wire's Turner-model effective CTE is
{param_opt['composite_cte_eff_per_C']} per degree C and its rule-of-mixtures density is
{param_opt['composite_density_kg_m3']} kg/m^3; the fatigue check includes the composite's
own thermal residual stress from constituent CTE mismatch, in addition to the cyclic
service load. Its fundamental natural frequency is {param_opt['natural_frequency_hz']} Hz
(margin ratio {param_opt['frequency_margin_ratio']}). A separate frequency-optimized
alternative, using the same wire treatment and capped at
{param_opt['frequency_optimized_alternative']['cost']} in cost, reaches
{param_opt['frequency_optimized_alternative']['natural_frequency_hz']} Hz; this alternative
is {'a different design from' if param_opt['frequency_alternative_differs_from_cost_optimum'] else 'the same design as'}
the minimum-cost one, showing that minimizing cost and maximizing dynamic margin are
{'competing' if param_opt['frequency_alternative_differs_from_cost_optimum'] else 'not competing'} objectives here.
This alternative is checked against the **{param_opt['frequency_alternative_fatigue_philosophy'].replace('_', '-')}**
fatigue criterion (a judgment call specific to this alternative -- the minimum-cost design
above always uses the infinite-life criterion); see the synthesis section for the
justification.

## 4. Robust design (Taguchi)

Signal-to-noise ratios by run: {taguchi['sn_by_run_db']}. The most robust factor-level
combination is {taguchi['most_robust_levels']} (predicted k={taguchi['most_robust_predicted_k_Nmm']}
N/mm, quality loss={taguchi['most_robust_quality_loss']}), which is
{'the same as' if taguchi['most_robust_equals_best_on_target'] else 'different from'}
the combination with the lowest quality loss against target (run
{taguchi['best_on_target_run_id']}, loss={taguchi['best_on_target_quality_loss']}).

## 5. Final-design selection (Pareto / TOPSIS / weighted sum)

Screened against three objectives -- cost, durability (Na), and dynamic (frequency) margin.
Feasible candidates: {pareto['feasible_candidates']}. Pareto-optimal:
{pareto['pareto_optimal_candidates']}. TOPSIS winner: {pareto['topsis_winner']}.
Weighted-sum winner: {pareto['weighted_sum_winner']}
({'they agree' if pareto['methods_agree'] else 'they disagree'}).

## 6. Synthesis

{synth['explanation']}
"""
    with open(OUT_FINDINGS, "w") as fh:
        fh.write(findings)

    tprint("report written to", OUT_REPORT)
    tprint("findings written to", OUT_FINDINGS)
    tprint("morphological best:", morph["best_combination"], morph["best_score"])
    tprint("axiomatic recommended:", axio["recommended_design"], axio["coupling_by_design"])
    tprint("parametric optimum:", param_opt["d_mm"], param_opt["D_mm"], param_opt["Na"], param_opt["cost"])
    tprint("taguchi most robust vs best-on-target equal:", taguchi["most_robust_equals_best_on_target"])
    tprint("pareto winners:", pareto["topsis_winner"], pareto["weighted_sum_winner"], pareto["methods_agree"])


if __name__ == "__main__":
    main()
