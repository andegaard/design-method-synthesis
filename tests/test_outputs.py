import csv
import itertools
import json
import math
import os
from math import erf, log2, sqrt

import pytest

OUT_FILE = os.environ.get("HARBOR_OUT_DIR", "/app/output") + "/design_report.json"
TRUTH_FILE = os.environ.get("HARBOR_TRUTH_DIR", "/tests") + "/ground_truth.json"
MD_FILE = os.environ.get("HARBOR_OUT_DIR", "/app/output") + "/findings.md"

MORPH_JSON = os.environ.get("MORPH_JSON", "/tests/morphological_chart.json")
AXIOM_JSON = os.environ.get("AXIOM_JSON", "/tests/axiomatic_design_candidates.json")
TAGUCHI_CSV = os.environ.get("TAGUCHI_CSV", "/tests/taguchi_spring_robustness.csv")
PARETO_CSV = os.environ.get("PARETO_CSV", "/tests/pareto_candidate_designs.csv")


def load_report():
    with open(OUT_FILE) as f:
        return json.load(f)


def load_truth():
    with open(TRUTH_FILE) as f:
        return json.load(f)


def nummap(d):
    return {int(k): v for k, v in d.items()}


# ---------------------------------------------------------------------------
# pure-stdlib reference recomputations (the verifier container has no numpy /
# pandas / scipy -- these mirror the authoring generators' logic exactly,
# using math.erf for the normal CDF in place of scipy.stats.norm).
# ---------------------------------------------------------------------------
def _enumerate_morph(chart):
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
    return total, feasible


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


def _norm_cdf(x):
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def _info_content(lsl, usl, mu, sigma):
    p = _norm_cdf((usl - mu) / sigma) - _norm_cdf((lsl - mu) / sigma)
    return -log2(p)


# This latch's own stated requirements (see instruction.md) -- hardcoded
# here, not read from environment/data, since the verifier only ever sees
# tests/ and the agent's own output. Material properties (including the
# composite constituent data below) are the row for material variant D3
# (particulate-reinforced Fe-Cr-alloy matrix wire) and the buckling limit is
# for end-fixation variant C3 (squared-and-ground ends) -- the pair the
# morphological stage always selects; this recomputation does not trust the
# report's own morphological section, it independently knows which row
# applies, the same way test_morphological_matches_raw_chart independently
# re-derives the winning combination itself.
F_OP_N = 55.0
DELTA_REQ_MM = 18.0
G_NMM2 = 79300.0
TAU_ALLOW_NMM2 = 620.0
D_MAX_MM = 14.0
C_MAX = 12.0
OVERSUPPLY = 1.5
F_MIN_N = 8.0
S_SE_BASE_NMM2 = 420.0
S_SU_BASE_NMM2 = 1350.0
SF_FATIGUE = 1.15
CLASH_MM = 2.0
R_CRIT = 4.5  # buckling slenderness limit for end-fixation C3

T_REF_C = 20.0
T_OP_C = 85.0
DERATE_FRAC_PER_C = 0.0015
_DERATE = 1.0 - DERATE_FRAC_PER_C * (T_OP_C - T_REF_C)
S_SU_NMM2 = S_SU_BASE_NMM2 * _DERATE

TREATMENTS = {"unpeened": {"S_se_mult": 1.0, "cost_mult": 1.0},
              "peened": {"S_se_mult": 1.35, "cost_mult": 1.20}}

# D3's matrix alloy is temper-hardened after consolidation; this is its full
# tempering-response table (hardness, the same three strength properties
# TAU_ALLOW_NMM2/S_SE_BASE_NMM2/S_SU_BASE_NMM2 above already hardcode for the
# winning row, and Charpy V-notch impact toughness, at each of several
# tempering temperatures) -- independently hardcoded here, same as everything
# else in this block, not read from the agent's report or the shipped data.
CHARPY_MIN_TOUGHNESS_J = 15.0
TEMPERING_RESPONSE = [
    {"temper_temp_C": 200.0, "hardness_HRC": 52.0, "S_su_Nmm2": 1520.0,
     "S_se_base_Nmm2": 473.0, "tau_allow_Nmm2": 698.0, "charpy_impact_J": 8.0},
    {"temper_temp_C": 300.0, "hardness_HRC": 49.0, "S_su_Nmm2": 1430.0,
     "S_se_base_Nmm2": 445.0, "tau_allow_Nmm2": 657.0, "charpy_impact_J": 6.5},
    {"temper_temp_C": 370.0, "hardness_HRC": 46.0, "S_su_Nmm2": 1350.0,
     "S_se_base_Nmm2": 420.0, "tau_allow_Nmm2": 620.0, "charpy_impact_J": 18.0},
    {"temper_temp_C": 430.0, "hardness_HRC": 42.0, "S_su_Nmm2": 1230.0,
     "S_se_base_Nmm2": 383.0, "tau_allow_Nmm2": 565.0, "charpy_impact_J": 28.0},
    {"temper_temp_C": 480.0, "hardness_HRC": 38.0, "S_su_Nmm2": 1100.0,
     "S_se_base_Nmm2": 342.0, "tau_allow_Nmm2": 505.0, "charpy_impact_J": 35.0},
    {"temper_temp_C": 540.0, "hardness_HRC": 34.0, "S_su_Nmm2": 980.0,
     "S_se_base_Nmm2": 305.0, "tau_allow_Nmm2": 450.0, "charpy_impact_J": 42.0},
    {"temper_temp_C": 600.0, "hardness_HRC": 30.0, "S_su_Nmm2": 860.0,
     "S_se_base_Nmm2": 268.0, "tau_allow_Nmm2": 395.0, "charpy_impact_J": 48.0},
]

# D3's composite constituent data (particulate metal-matrix wire: matrix
# phase + reinforcement phase) -- needed for Turner's effective-CTE model
# and the constituent-mismatch thermal residual stress that feeds into g6.
MATRIX_ALPHA_PER_C = 1.08e-5
MATRIX_K_NMM2 = 172000.0
MATRIX_E_NMM2 = 207000.0
REINFORCEMENT_ALPHA_PER_C = 5.6e-6
REINFORCEMENT_K_NMM2 = 265000.0
REINFORCEMENT_VOL_FRACTION = 0.24
T_PROCESS_C = 600.0

# Same D3 composite's mass-density constituents (rule of mixtures), and this
# latch's own dynamic (spring-surge) requirement -- independently hardcoded
# here, same as everything else in this block.
MATRIX_DENSITY_KG_M3 = 7750.0
REINFORCEMENT_DENSITY_KG_M3 = 4930.0
F_OPERATING_HZ = 20.0
FREQ_SAFETY_MARGIN = 15.0
FREQ_FLOOR_HZ = FREQ_SAFETY_MARGIN * F_OPERATING_HZ
FREQ_ALT_COST_CAP_MULTIPLIER = 1.15

# Process-robustness noise magnitudes (see taguchi_spring_robustness.csv's
# own "low"/"high" noise-condition offsets) and finite-life (Basquin)
# fatigue background data -- independently hardcoded here, same as
# everything else in this block; the solving agent must recover the first
# two from the raw CSV itself, not from anywhere in the shipped data.
DD_NOISE_MM = 0.015
DN_NOISE = 0.2
TAU_F_PRIME_NMM2 = 1650.0
B_EXP = -0.09
RATED_QUALIFICATION_CYCLES = 50000


def _turner_effective_cte():
    Vr = REINFORCEMENT_VOL_FRACTION
    Vm = 1.0 - Vr
    num = Vm*MATRIX_K_NMM2*MATRIX_ALPHA_PER_C + Vr*REINFORCEMENT_K_NMM2*REINFORCEMENT_ALPHA_PER_C
    den = Vm*MATRIX_K_NMM2 + Vr*REINFORCEMENT_K_NMM2
    return num/den


def _thermal_residual_shear_Nmm2():
    Vr = REINFORCEMENT_VOL_FRACTION
    sigma_res = ((Vr/(1.0-Vr)) * MATRIX_E_NMM2
                 * (MATRIX_ALPHA_PER_C - REINFORCEMENT_ALPHA_PER_C) * (T_PROCESS_C - T_REF_C))
    return sigma_res / math.sqrt(3.0)


def _composite_density_kg_m3():
    Vr = REINFORCEMENT_VOL_FRACTION
    Vm = 1.0 - Vr
    return Vm*MATRIX_DENSITY_KG_M3 + Vr*REINFORCEMENT_DENSITY_KG_M3


def _natural_frequency_hz(x, rho_kg_m3=None, G_nmm2=G_NMM2):
    if rho_kg_m3 is None:
        rho_kg_m3 = RHO_EFF_D3
    d, D, Na = x
    return 1.0e6 * (2.0 / math.pi) * (d / (Na * D**2)) * math.sqrt(G_nmm2 / (32.0*rho_kg_m3))


ALPHA_EFF_D3 = _turner_effective_cte()
TAU_RES_NMM2 = _thermal_residual_shear_Nmm2()
RHO_EFF_D3 = _composite_density_kg_m3()


def _wahl(C):
    return (4*C - 1)/(4*C - 4) + 0.615/C


def _S_se_eff(treatment):
    return S_SE_BASE_NMM2 * _DERATE * TREATMENTS[treatment]["S_se_mult"]


def _tau_a_allow_basquin():
    return TAU_F_PRIME_NMM2 * (2.0 * RATED_QUALIFICATION_CYCLES) ** B_EXP


def _fatigue_g(x, treatment, philosophy="infinite"):
    """Linear mean/alternating shear-stress damage criterion.
    philosophy="infinite" (the only one the minimum-cost design is ever
    checked against) uses the endurance limit S_se; philosophy="finite"
    (only ever valid for the frequency-optimized alternative) uses the
    Basquin-derived allowable at the rated qualification cycle count."""
    d, D, Na = x
    C = D / d
    Kw = _wahl(C)
    Fa = (F_OP_N - F_MIN_N) / 2.0
    Fm = (F_OP_N + F_MIN_N) / 2.0
    tau_a = 8*Fa*D*Kw/(math.pi*d**3)
    tau_m = 8*Fm*D*Kw/(math.pi*d**3) + TAU_RES_NMM2
    if philosophy == "infinite":
        allow_a = _S_se_eff(treatment)
    else:
        allow_a = _tau_a_allow_basquin() * TREATMENTS[treatment]["S_se_mult"]
    return tau_a/allow_a + tau_m/S_SU_NMM2 - 1.0/SF_FATIGUE


def _g1(x):
    d, D, Na = x
    C = D / d
    return 8*F_OP_N*D*_wahl(C)/(math.pi*d**3) - TAU_ALLOW_NMM2


def _g2(x):
    d, D, Na = x
    k = G_NMM2*d**4/(8*D**3*Na)
    return F_OP_N - k*DELTA_REQ_MM


def _g3(x):
    d, D, Na = x
    k = G_NMM2*d**4/(8*D**3*Na)
    return k*DELTA_REQ_MM - OVERSUPPLY*F_OP_N


def _g4(x):
    d, D, Na = x
    return D - D_MAX_MM


def _g5(x):
    d, D, Na = x
    return D/d - C_MAX


def _g7(x):
    d, D, Na = x
    Ls = (Na + 2.0)*d
    L0 = Ls + DELTA_REQ_MM + CLASH_MM
    return L0/D - R_CRIT


def _g8(x):
    return FREQ_FLOOR_HZ - _natural_frequency_hz(x)


def _g9_fatigue(x, treatment, philosophy="infinite"):
    d, D, Na = x
    return _fatigue_g((d - DD_NOISE_MM, D, Na), treatment, philosophy=philosophy)


def _g9_buckling(x):
    d, D, Na = x
    return _g7((d + DD_NOISE_MM, D, Na + DN_NOISE))


def _g9_freq(x):
    d, D, Na = x
    return _g8((d - DD_NOISE_MM, D, Na + DN_NOISE))


def _spring_g(x, treatment, philosophy="infinite", include_freq_floor=True):
    """Every requirement, as positive-is-*violated* margins (matching the
    original convention: feasible means every entry <= tol): five
    static/geometric, the fatigue criterion (under the given philosophy),
    buckling, then their process-robustness re-checks, and -- unless
    include_freq_floor is False, for the frequency-optimized alternative --
    the frequency floor and its own process-robustness re-check."""
    out = [_g1(x), _g2(x), _g3(x), _g4(x), _g5(x),
           _fatigue_g(x, treatment, philosophy=philosophy), _g7(x),
           _g9_fatigue(x, treatment, philosophy=philosophy), _g9_buckling(x)]
    if include_freq_floor:
        out += [_g8(x), _g9_freq(x)]
    return out


def _spring_cost(x, treatment):
    d, D, Na = x
    vol = (math.pi**2 / 4.0) * d**2 * D * (Na + 2.0)
    return vol * TREATMENTS[treatment]["cost_mult"]


def _pareto_feasible(x, treatment, tol=1e-6):
    d, D, Na = x
    bounds_ok = 0.5 <= d <= 2.0 and 4.0 <= D <= 14.0 and 2.0 <= Na <= 30.0
    return all(g <= tol for g in _spring_g(x, treatment)) and bounds_ok


def _sn_by_run(rows):
    by_run = {}
    for r in rows:
        by_run.setdefault(r["run_id"], []).append(r["spring_rate_k_Nmm"])
    out = {}
    for run_id, ks in by_run.items():
        mean_k = sum(ks) / len(ks)
        var_k = sum((k - mean_k) ** 2 for k in ks) / (len(ks) - 1)
        out[run_id] = 10 * math.log10(mean_k**2 / var_k)
    return out


# ---------------------------------------------------------------------------
def test_report_files_exist():
    assert os.path.exists(OUT_FILE), "design_report.json not produced"
    assert os.path.exists(MD_FILE), "findings.md not produced"


def test_findings_covers_five_stages():
    # instruction.md requires findings.md to cover all five stages; a report
    # that only reproduces design_report.json's numbers under one heading,
    # or never mentions a stage by name, must fail here. Coverage only --
    # not a strict textual ordering, since a findings.md that legitimately
    # cross-references stages (e.g. a synthesis summary up front, or a
    # methods-used aside) shouldn't fail on word order alone.
    with open(MD_FILE) as f:
        text = f.read().lower()
    topics = ["morpholog", "axiomatic", "parametric", "taguchi", "pareto"]
    for topic in topics:
        assert topic in text, f"findings.md never mentions {topic!r}"


def test_required_fields():
    data = load_report()
    for key in ("morphological", "axiomatic", "parametric_optimization", "taguchi", "pareto", "synthesis"):
        assert key in data, f"missing top-level key {key}"
    morph, axio, popt, tag, par, syn = (
        data["morphological"], data["axiomatic"], data["parametric_optimization"],
        data["taguchi"], data["pareto"], data["synthesis"],
    )
    assert "total_combinations" in morph
    assert "feasible_combinations" in morph
    assert "best_combination" in morph
    assert "best_score" in morph
    assert "coupling_by_design" in axio
    assert "information_content_bits" in axio
    assert "recommended_design" in axio
    assert "d_mm" in popt and "D_mm" in popt and "Na" in popt
    assert "cost" in popt and "constraints_satisfied" in popt
    assert "treatment" in popt and popt["treatment"] in ("unpeened", "peened")
    assert "temper_temp_C" in popt and isinstance(popt["temper_temp_C"], (int, float))
    assert "composite_cte_eff_per_C" in popt and isinstance(popt["composite_cte_eff_per_C"], (int, float))
    assert "composite_density_kg_m3" in popt and isinstance(popt["composite_density_kg_m3"], (int, float))
    assert "natural_frequency_hz" in popt and isinstance(popt["natural_frequency_hz"], (int, float))
    assert "frequency_margin_ratio" in popt and isinstance(popt["frequency_margin_ratio"], (int, float))
    assert "frequency_alternative_differs_from_cost_optimum" in popt
    assert isinstance(popt["frequency_alternative_differs_from_cost_optimum"], bool)
    assert popt.get("frequency_alternative_fatigue_philosophy") in ("infinite_life", "finite_life"), \
        "frequency_alternative_fatigue_philosophy must be 'infinite_life' or 'finite_life'"
    alt = popt.get("frequency_optimized_alternative")
    assert isinstance(alt, dict), "frequency_optimized_alternative must be an object"
    for key in ("d_mm", "D_mm", "Na", "cost", "natural_frequency_hz", "frequency_margin_ratio"):
        assert key in alt and isinstance(alt[key], (int, float)), f"frequency_optimized_alternative missing {key!r}"
    assert "sn_by_run_db" in tag
    assert "factor_level_sn_avg_db" in tag
    assert "most_robust_levels" in tag
    assert "best_on_target_run_id" in tag
    assert "most_robust_equals_best_on_target" in tag
    assert "feasible_candidates" in par
    assert "pareto_optimal_candidates" in par
    assert "topsis_winner" in par and "weighted_sum_winner" in par
    assert "recommended_concept" in syn
    assert "recommended_embodiment" in syn
    assert "recommended_final_design" in syn
    assert "robustness_and_on_target_are_different" in syn
    assert "explanation" in syn


def test_explanation_content():
    # The structured fields (coupling, philosophy, both MCDM winners, methods_agree,
    # robust-vs-on-target flag, ...) grade the science. The free-text explanation is
    # deliberately not keyword-gated: an agent that reasons correctly but words it
    # differently from the reference must not fail here. Length only.
    data = load_report()
    expl = data["synthesis"]["explanation"]
    assert isinstance(expl, str) and len(expl) >= 150, "explanation too short"


# ------------------------------------------------------------ 1. morphological
def test_morphological_totals():
    data = load_report()
    truth = load_truth()
    morph = data["morphological"]
    assert morph["total_combinations"] == truth["morph_total_combinations"]
    assert morph["feasible_combinations"] == truth["morph_feasible_combinations"]


def test_morphological_best_combination():
    data = load_report()
    truth = load_truth()
    morph = data["morphological"]
    assert morph["best_combination"] == truth["morph_best_combination"]
    assert morph["best_score"] == truth["morph_best_score"]


def test_morphological_matches_raw_chart():
    # Anti-hardcoding gate: independently re-enumerate the chart (including
    # the pairwise exclusion rules) from the raw data file itself and check
    # the report actually reflects it, not a guessed or memorized answer.
    with open(MORPH_JSON) as f:
        chart = json.load(f)
    total, feasible = _enumerate_morph(chart)
    best_score, best_combo = feasible[0]

    data = load_report()
    morph = data["morphological"]
    assert morph["total_combinations"] == total
    assert morph["feasible_combinations"] == len(feasible)
    assert morph["best_score"] == best_score
    assert morph["best_combination"] == best_combo


# --------------------------------------------------------------- 2. axiomatic
def test_axiomatic_coupling_classification():
    data = load_report()
    truth = load_truth()
    coupling = data["axiomatic"]["coupling_by_design"]
    for name, expect in truth["axiomatic_coupling_true"].items():
        assert coupling.get(name) == expect, f"design {name}: {coupling.get(name)} vs {expect}"


def test_axiomatic_coupled_design_excluded_from_information_axiom():
    # design Y is fully coupled and must be rejected under the Independence
    # Axiom -- its information content must not even be compared, regardless
    # of the fact that Y's process data is the tightest of the three and
    # would otherwise look like the best choice.
    data = load_report()
    assert "Y" not in data["axiomatic"]["information_content_bits"]


def test_axiomatic_information_content():
    data = load_report()
    truth = load_truth()
    info = data["axiomatic"]["information_content_bits"]
    tol = truth["axiomatic_info_tol_bits"]
    for name, expect in truth["axiomatic_info_bits_true"].items():
        assert name in info, f"missing information content for design {name}"
        assert abs(info[name] - expect) <= tol, f"design {name}: {info[name]} vs {expect}"


def test_axiomatic_recommended_design():
    data = load_report()
    truth = load_truth()
    assert data["axiomatic"]["recommended_design"] == truth["axiomatic_recommended_design_true"]


def test_axiomatic_matches_raw_candidates():
    # Anti-hardcoding gate: reclassify coupling and recompute information
    # content directly from the raw FR-DP matrices and process data, using a
    # pure stdlib normal CDF (erf-based, exact) so this does not depend on
    # scipy being installed in the verifier image.
    with open(AXIOM_JSON) as f:
        designs = json.load(f)["designs"]

    data = load_report()
    coupling = data["axiomatic"]["coupling_by_design"]
    info = data["axiomatic"]["information_content_bits"]

    info_true = {}
    for name, spec in designs.items():
        c = _classify_coupling(spec["matrix"])
        assert coupling.get(name) == c, f"design {name} coupling mismatch: {coupling.get(name)} vs {c}"
        if c != "coupled":
            info_true[name] = sum(_info_content(*spec["process_data"][fr]) for fr in ("FR1", "FR2", "FR3"))

    for name, expect in info_true.items():
        assert abs(info[name] - expect) <= 0.01, f"design {name}: {info[name]} vs recomputed {expect}"
    recommended = min(info_true, key=info_true.get)
    assert data["axiomatic"]["recommended_design"] == recommended


# ------------------------------------------------- 3. parametric optimization
def test_parametric_optimum_cost():
    data = load_report()
    truth = load_truth()
    got = data["parametric_optimization"]["cost"]
    expect = truth["spring_f_star_true"]
    tol = truth["spring_f_star_tol_rel"]
    assert abs(got - expect) <= tol * expect, f"cost {got} vs {expect}"


def test_parametric_optimum_treatment():
    # The cheaper of the two wire-treatment options is not obvious without
    # solving both branches: a report that never considers shot peening (or
    # picks it without checking whether it is actually cheaper once its
    # cost multiplier is included) will get this wrong even if its (d, D, Na)
    # happens to look plausible.
    data = load_report()
    truth = load_truth()
    assert data["parametric_optimization"]["treatment"] == truth["spring_treatment_true"]


def test_parametric_optimum_temper_selection():
    # The cheapest tempering condition is not the strongest one: the lowest-
    # temper row and one inside this alloy's tempered-martensite-
    # embrittlement band both look cheaper on strength alone but fail the
    # stated minimum Charpy toughness -- a report that picks either (or any
    # row not actually solved-and-compared against every other toughness-
    # passing row and both wire treatments) gets this field wrong even if
    # its cost happens to look close.
    data = load_report()
    truth = load_truth()
    got = data["parametric_optimization"]["temper_temp_C"]
    assert abs(got - truth["spring_temper_temp_C_true"]) <= 1e-6, \
        f"temper_temp_C {got} vs {truth['spring_temper_temp_C_true']}"


def test_parametric_optimum_temper_clears_toughness_floor():
    # Independent anti-trap gate: whatever tempering_temp_C the report names,
    # look up its row in the independently-hardcoded tempering-response table
    # above and confirm it actually clears CHARPY_MIN_TOUGHNESS_J -- this
    # fails a report that reports a plausible-sounding but wrong temperature
    # inside the trap band even if test_parametric_optimum_temper_selection's
    # exact-match check were somehow satisfied by a stale/rounded value.
    data = load_report()
    got_temp = data["parametric_optimization"]["temper_temp_C"]
    rows = [r for r in TEMPERING_RESPONSE if abs(r["temper_temp_C"] - got_temp) <= 1e-6]
    assert rows, f"temper_temp_C {got_temp} is not one of tempering_response's stated temperatures"
    assert rows[0]["charpy_impact_J"] >= CHARPY_MIN_TOUGHNESS_J, (
        f"selected tempering condition at {got_temp} C fails the minimum Charpy "
        f"toughness requirement ({rows[0]['charpy_impact_J']} J < {CHARPY_MIN_TOUGHNESS_J} J)")


def test_parametric_optimum_composite_cte():
    # The composite wire's effective CTE (Turner's model, weighting each
    # constituent phase's CTE by its volume fraction and bulk modulus) is a
    # required, independently-checkable result in its own right -- getting
    # the material row right elsewhere does not by itself confirm this was
    # actually derived rather than omitted or guessed.
    data = load_report()
    truth = load_truth()
    got = data["parametric_optimization"]["composite_cte_eff_per_C"]
    expect = truth["composite_cte_eff_true"]
    tol = truth["composite_cte_eff_tol"]
    assert abs(got - expect) <= tol, f"composite_cte_eff_per_C {got} vs {expect}"


def test_parametric_optimum_composite_cte_matches_recomputation():
    # Anti-hardcoding gate: recompute Turner's model directly from the
    # constituent matrix/reinforcement properties (hardcoded here
    # independently of the agent's report, the same way F_OP_N and
    # TAU_ALLOW_NMM2 above are) and check the report's value matches --
    # catches a value that happens to be close to the sealed number without
    # having been derived from the actual constituent data.
    data = load_report()
    got = data["parametric_optimization"]["composite_cte_eff_per_C"]
    assert abs(got - ALPHA_EFF_D3) <= 1e-7, f"composite_cte_eff_per_C {got} vs recomputed {ALPHA_EFF_D3}"


def test_parametric_optimum_composite_density():
    data = load_report()
    truth = load_truth()
    got = data["parametric_optimization"]["composite_density_kg_m3"]
    expect = truth["composite_density_true"]
    tol = truth["composite_density_tol"]
    assert abs(got - expect) <= tol, f"composite_density_kg_m3 {got} vs {expect}"


def test_parametric_optimum_composite_density_matches_recomputation():
    # Anti-hardcoding gate: recompute the rule-of-mixtures density directly
    # from the constituent matrix/reinforcement densities.
    data = load_report()
    got = data["parametric_optimization"]["composite_density_kg_m3"]
    assert abs(got - RHO_EFF_D3) <= 0.05, f"composite_density_kg_m3 {got} vs recomputed {RHO_EFF_D3}"


def test_parametric_optimum_natural_frequency():
    # The fundamental natural frequency (spring-surge check) is a required,
    # independently-checkable result: a design whose (d, D, Na) happen to
    # satisfy the other constraints does not by itself confirm this was
    # actually derived.
    data = load_report()
    truth = load_truth()
    got = data["parametric_optimization"]["natural_frequency_hz"]
    expect = truth["natural_frequency_hz_true"]
    tol = truth["natural_frequency_hz_tol_rel"] * expect
    assert abs(got - expect) <= tol, f"natural_frequency_hz {got} vs {expect}"


def test_parametric_optimum_natural_frequency_matches_recomputation():
    # Anti-hardcoding gate: recompute the natural-frequency relation
    # directly from the agent's own reported (d, D, Na) and the
    # independently-hardcoded density/shear-modulus constants above. The
    # tolerances here are self-consistency checks, not accuracy checks (that
    # is test_parametric_optimum_natural_frequency above, at a 2% relative
    # tolerance against the sealed value) -- they exist to catch a value
    # that was not actually derived from the reported (d, D, Na) at all, so
    # they are sized to absorb ordinary reporting-precision rounding (whole
    # Hz; one decimal place on the margin ratio) rather than to demand the
    # solver's own near-machine-precision internal digits.
    data = load_report()
    popt = data["parametric_optimization"]
    x = (popt["d_mm"], popt["D_mm"], popt["Na"])
    fn_recomputed = _natural_frequency_hz(x)
    assert abs(popt["natural_frequency_hz"] - fn_recomputed) <= 1.0, \
        f"natural_frequency_hz {popt['natural_frequency_hz']} vs recomputed {fn_recomputed}"
    margin_recomputed = fn_recomputed / F_OPERATING_HZ
    assert abs(popt["frequency_margin_ratio"] - margin_recomputed) <= 0.06, \
        f"frequency_margin_ratio {popt['frequency_margin_ratio']} vs recomputed {margin_recomputed}"


def test_frequency_optimized_alternative():
    # The frequency-optimized alternative must actually differ from the
    # minimum-cost design (they do on this dataset), be feasible against
    # every requirement except the frequency floor and its process-
    # robustness re-check (which it is expected to exceed by construction,
    # since it is being maximized), respect the stated cost cap relative to
    # the minimum-cost design, and be checked against whichever fatigue-life
    # philosophy the report itself states it used -- this is a genuine
    # judgment call (see dataset_manifest.md), so there are two sealed
    # targets, one per philosophy, and the report is graded against
    # whichever one it actually claims, not a single fixed answer.
    data = load_report()
    truth = load_truth()
    popt = data["parametric_optimization"]
    alt = popt["frequency_optimized_alternative"]
    philosophy_key = popt["frequency_alternative_fatigue_philosophy"]
    philosophy = "infinite" if philosophy_key == "infinite_life" else "finite"
    truth_prefix = "freq_alt_infinite" if philosophy_key == "infinite_life" else "freq_alt_finite"

    assert popt["frequency_alternative_differs_from_cost_optimum"] == truth["freq_alternative_differs_true"]

    expect_fn = truth[f"{truth_prefix}_natural_frequency_hz_true"]
    tol_fn = truth["freq_alt_fn_tol_rel"] * expect_fn
    assert abs(alt["natural_frequency_hz"] - expect_fn) <= tol_fn, \
        f"frequency_optimized_alternative ({philosophy_key}) natural_frequency_hz {alt['natural_frequency_hz']} vs {expect_fn}"

    expect_cost = truth[f"{truth_prefix}_cost_true"]
    tol_cost = truth["freq_alt_cost_tol_rel"] * expect_cost
    assert abs(alt["cost"] - expect_cost) <= tol_cost, \
        f"frequency_optimized_alternative ({philosophy_key}) cost {alt['cost']} vs {expect_cost}"

    cost_cap = truth["freq_alt_cost_cap_multiplier"] * popt["cost"]
    assert alt["cost"] <= cost_cap + 0.01, \
        f"frequency_optimized_alternative cost {alt['cost']} exceeds the {truth['freq_alt_cost_cap_multiplier']}x cap {cost_cap}"

    x_alt = (alt["d_mm"], alt["D_mm"], alt["Na"])
    treatment = popt["treatment"]
    # Every requirement except the frequency floor itself and its
    # process-robustness re-check, under the report's own chosen philosophy.
    gs = _spring_g(x_alt, treatment, philosophy=philosophy, include_freq_floor=False)
    tol = truth["spring_constraint_tol"]
    for i, g in enumerate(gs, start=1):
        assert g <= tol, f"frequency_optimized_alternative ({philosophy_key}) g{i}({x_alt}) = {g} > {tol}"

    # Self-consistency, not accuracy (that is the tol_fn check above): sized
    # to absorb ordinary reporting-precision rounding (whole Hz), the same
    # as the minimum-cost design's own version of this check above.
    fn_alt_recomputed = _natural_frequency_hz(x_alt)
    assert abs(alt["natural_frequency_hz"] - fn_alt_recomputed) <= 1.0, \
        f"frequency_optimized_alternative natural_frequency_hz {alt['natural_frequency_hz']} vs recomputed {fn_alt_recomputed}"


def test_parametric_optimum_satisfies_constraints():
    # Recompute every constraint function (five static/geometric, the
    # infinite-life fatigue criterion, buckling, the frequency floor, and
    # each of fatigue/buckling/frequency's process-robustness re-checks)
    # directly from the reported (d, D, N, treatment) -- a design that
    # merely reports a low-looking cost without actually being feasible,
    # nominally or under the process-robustness noise, must fail here even
    # if the cost happens to be close to the true optimum. The minimum-cost
    # design is always checked against the infinite-life fatigue criterion
    # -- that choice is never a judgment call, unlike the alternative above.
    data = load_report()
    truth = load_truth()
    popt = data["parametric_optimization"]
    assert popt["constraints_satisfied"] is True
    x = (popt["d_mm"], popt["D_mm"], popt["Na"])
    treatment = popt["treatment"]
    tol = truth["spring_constraint_tol"]
    for i, g in enumerate(_spring_g(x, treatment, philosophy="infinite", include_freq_floor=True), start=1):
        assert g <= tol, f"g{i}({x}) = {g} > {tol}"

    cost = _spring_cost(x, treatment)
    expect = truth["spring_f_star_true"]
    rel_tol = truth["spring_f_star_tol_rel"]
    assert abs(cost - expect) <= rel_tol * expect, f"recomputed cost {cost} vs {expect}"


# ------------------------------------------------------------------ 4. taguchi
def test_taguchi_sn_by_run():
    data = load_report()
    truth = load_truth()
    sn = nummap(data["taguchi"]["sn_by_run_db"])
    true_sn = nummap(truth["taguchi_sn_by_run_true"])
    tol = truth["taguchi_sn_tol_db"]
    for rid, expect in true_sn.items():
        assert abs(sn[rid] - expect) <= tol, f"run {rid}: {sn[rid]} vs {expect}"


def test_taguchi_factor_level_averages():
    data = load_report()
    truth = load_truth()
    avg = data["taguchi"]["factor_level_sn_avg_db"]
    true_avg = truth["taguchi_factor_level_sn_avg_true"]
    tol = truth["taguchi_sn_tol_db"] * 2  # averaged over 3 runs each
    for factor, levels in true_avg.items():
        for lvl, expect in levels.items():
            got = avg[factor][lvl]
            assert abs(got - expect) <= tol, f"{factor}{lvl}: {got} vs {expect}"


def test_taguchi_most_robust_combination():
    data = load_report()
    truth = load_truth()
    tag = data["taguchi"]
    assert tag["most_robust_levels"] == truth["taguchi_most_robust_levels_true"]
    assert abs(tag["most_robust_predicted_k_Nmm"] - truth["taguchi_most_robust_k_true"]) \
        <= truth["taguchi_most_robust_k_tol"]
    assert abs(tag["most_robust_quality_loss"] - truth["taguchi_most_robust_loss_true"]) \
        <= truth["taguchi_loss_tol"]


def test_taguchi_best_on_target():
    data = load_report()
    truth = load_truth()
    tag = data["taguchi"]
    assert tag["best_on_target_run_id"] == truth["taguchi_best_on_target_run_true"]
    assert tag["best_on_target_levels"] == truth["taguchi_best_on_target_levels_true"]
    assert abs(tag["best_on_target_quality_loss"] - truth["taguchi_best_on_target_loss_true"]) \
        <= truth["taguchi_loss_tol"]


def test_taguchi_robust_and_on_target_are_distinct():
    # The central conceptual check of this stage: the factor-level
    # combination that maximizes signal-to-noise (most robust to the named
    # noise conditions) is NOT the same combination that minimizes quality
    # loss against the target spring rate. A report that assumes these
    # coincide (a common shortcut) must fail this check.
    data = load_report()
    truth = load_truth()
    assert data["taguchi"]["most_robust_equals_best_on_target"] == \
        truth["taguchi_most_robust_equals_best_on_target_true"]


def test_taguchi_matches_raw_csv():
    # Anti-hardcoding gate: recompute every run's signal-to-noise ratio
    # directly from the raw per-noise-condition measurements.
    with open(TAGUCHI_CSV, newline="") as f:
        rows = []
        for row in csv.DictReader(f):
            rows.append({
                "run_id": int(row["run_id"]),
                "spring_rate_k_Nmm": float(row["spring_rate_k_Nmm"]),
            })
    sn_true = _sn_by_run(rows)

    data = load_report()
    sn = nummap(data["taguchi"]["sn_by_run_db"])
    for rid, expect in sn_true.items():
        assert abs(sn[rid] - expect) <= 0.05, f"run {rid}: {sn[rid]} vs recomputed {expect}"


# -------------------------------------------------------------------- 5. pareto
def test_pareto_feasibility():
    # Q1 is a deliberate near-miss (infeasible by a small margin on one
    # constraint); Q10 is a similar near-miss on the frequency-margin floor
    # alone (Q12, by contrast, just barely clears it); Q7 and Q8 are clearly
    # infeasible. A report that trusts the candidate list at face value
    # rather than rechecking feasibility will get this wrong.
    data = load_report()
    truth = load_truth()
    got = sorted(data["pareto"]["feasible_candidates"])
    assert got == sorted(truth["pareto_feasible_candidates_true"]), \
        f"feasible candidates {got} vs {truth['pareto_feasible_candidates_true']}"


def test_pareto_optimal_set():
    data = load_report()
    truth = load_truth()
    got = sorted(data["pareto"]["pareto_optimal_candidates"])
    assert got == sorted(truth["pareto_optimal_candidates_true"])


def test_pareto_winners_and_agreement():
    data = load_report()
    truth = load_truth()
    par = data["pareto"]
    assert par["topsis_winner"] == truth["pareto_topsis_winner_true"]
    assert par["weighted_sum_winner"] == truth["pareto_weighted_sum_winner_true"]
    assert par["methods_agree"] == truth["pareto_methods_agree_true"]


def test_pareto_matches_raw_csv():
    # Anti-hardcoding gate: recheck every candidate's feasibility directly
    # against the raw (d, D, Na, treatment) values and the same constraint
    # functions used in the parametric-optimization stage.
    with open(PARETO_CSV, newline="") as f:
        rows = {r["candidate"]: (float(r["d_mm"]), float(r["D_mm"]), float(r["Na"]), r["treatment"])
                for r in csv.DictReader(f)}
    feas_true = sorted(name for name, (d, D, Na, t) in rows.items() if _pareto_feasible((d, D, Na), t))

    data = load_report()
    got = sorted(data["pareto"]["feasible_candidates"])
    assert got == feas_true, f"feasible candidates {got} vs recomputed {feas_true}"


# --------------------------------------------------------------- 6. synthesis
def test_synthesis_consistent_with_stage_results():
    # The synthesis must reuse each stage's own already-checked results, not
    # a second, independently invented answer. TOPSIS and the weighted-sum
    # method are not required to agree on this dataset (they do not); the
    # final recommendation must be whichever of the two the report itself
    # settled on, not a third value.
    data = load_report()
    par = data["pareto"]
    assert data["synthesis"]["recommended_concept"] == data["morphological"]["best_combination"]
    assert data["synthesis"]["recommended_embodiment"] == data["axiomatic"]["recommended_design"]
    assert data["synthesis"]["recommended_final_design"] in (par["topsis_winner"], par["weighted_sum_winner"])
    assert data["synthesis"]["robustness_and_on_target_are_different"] == \
        (not data["taguchi"]["most_robust_equals_best_on_target"])


def test_synthesis_addresses_method_disagreement():
    # The disagreement itself is graded structurally via pareto.methods_agree
    # (see test_pareto_winners_and_agreement); the recommended final design must
    # be one of the two winners (test_synthesis_consistent_with_stage_results).
    # No keyword check on the prose.
    data = load_report()
    assert data["pareto"]["methods_agree"] == (
        data["pareto"]["topsis_winner"] == data["pareto"]["weighted_sum_winner"]
    )
