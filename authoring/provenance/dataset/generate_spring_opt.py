#!/usr/bin/env python3
"""Generate environment/data/spring_optimization_problem.json.

The parametric-design stage for the latch's energy-storage subsystem: size a
helical compression spring (wire diameter d, mean coil diameter D, active
coil count Na) to deliver this latch's own stated force/deflection
requirement at minimum relative material cost, subject to standard
spring-design relations -- shear stress via the Wahl stress-concentration
factor, the spring-rate-derived force delivered at full deflection (bounded
both below, so the latch actually engages, and above, so it is not
needlessly over-built), a housing space limit, a manufacturability limit on
the spring index D/d, a fatigue check (a linear mean/alternating-stress
damage criterion) against the cyclic load the spring actually sees over
repeated latch actuation, a lateral-buckling slenderness limit, a
fundamental-natural-frequency floor against spring surge, and a
process-robustness requirement that reuses the robust-design stage's own
characterized manufacturing-tolerance noise -- a design that only satisfies
the static stress limit at its nominal dimensions can still be unsafe once
cyclic loading, elastic instability, resonant excitation, or ordinary
dimensional scatter around those same nominal dimensions is considered.

Six things make this stage depend on the concept-selection (morphological)
stage and the robust-design (Taguchi) stage rather than standing alone:

  1. The material properties used (shear modulus, allowable stress, fatigue
     strengths) are given as a small table keyed by the *material* variant
     code from the morphological chart's `material` sub-function, not as
     bare numbers -- the correct row is the one the morphological stage
     actually selected.
  2. The lateral-buckling slenderness limit is given as a table keyed by the
     `end_fixation` variant code from the same chart, for the same reason.
  3. The fatigue strength additionally depends on an operating-temperature
     derating and on a choice between two wire-treatment options (as
     supplied, or shot-peened) that trade a higher relative material cost
     for a higher fatigue strength -- the cheaper *feasible* option is not
     obvious without solving the sizing problem for both and comparing.
  4. The wire is a particulate metal-matrix composite (a metal-alloy matrix
     phase with a hard ceramic-like particulate reinforcement phase), and
     each material row gives the two phases' own thermal-expansion,
     stiffness, and mass-density properties rather than a single
     already-homogenized number. Deriving the composite's effective
     coefficient of thermal expansion, its thermal residual stress, and its
     mass density all from the same constituent data is part of correctly
     building the fatigue and dynamic-response constraints.
  5. The fundamental-natural-frequency floor depends on that same
     constituent-derived composite density and on the material's shear
     modulus, so it too is only fully determined once the concept-selection
     stage's material choice is known.
  6. A process-robustness requirement asks whether the sized design stays
     feasible under the same wire-diameter and active-coil manufacturing-
     tolerance noise the robust-design (Taguchi) stage already characterizes
     for this same spring family -- the magnitude of that noise is not
     restated here; it must be recovered from `taguchi_spring_robustness.csv`
     itself, the same way that stage's own analysis uses it.
  7. The selected material's strength-related properties (the static
     allowable stress, ultimate strength, and endurance limit that D1/D2
     above give directly) are not given as a single number at all: this
     matrix alloy is temper-hardened after consolidation, and
     `tempering_response` tabulates hardness, those same three strength
     properties, and Charpy V-notch impact toughness as a function of
     tempering temperature for this same alloy. Which condition applies is
     not stated -- it must clear a stated minimum Charpy toughness (two
     conditions do not, including one inside this alloy's classical
     tempered-martensite-embrittlement band, where toughness dips even
     though temper temperature, and so strength, is not at its lowest) and,
     among the conditions that do, give the global minimum-cost design
     jointly with the wire-treatment choice above -- the same kind of
     solve-and-compare, now over a second, compounding discrete choice.

The data file gives the underlying physical relations and this latch's own
numeric requirements as raw ingredients -- it does not pre-package them as
ready-to-use inequalities, and it does not walk through, in prose, which
derived quantity feeds into which constraint or how. Recognizing that a
constituent-mismatch residual stress belongs in the fatigue criterion's mean
term, that a rule-of-mixtures density belongs in the natural-frequency
relation, that the Taguchi study's own noise characterization belongs in a
process-robustness re-check of this stage's own design, and turning each
stated requirement into an explicit constraint function of (d, D, Na) is
part of the task. Separately, which fatigue-life philosophy governs the
frequency-optimized alternative design (an endurance-limit "infinite-life"
criterion, the same one the minimum-cost design uses, or a finite-life
criterion pinned to a stated rated qualification cycle count) is a genuine,
defensible-either-way engineering judgment call, not a computation with one
correct answer -- the minimum-cost design itself is deliberately insulated
from this choice and always uses the infinite-life criterion, so that this
stage's headline, most-checked result does not hinge on a judgment call.

This generator does not draw random data -- the "raw data" for this stage
*is* the problem formulation itself (objective, physical relations, variable
bounds, material/end-fixation options, and this latch's own
force/deflection/material/fatigue/dynamic requirements), posed directly from
first-principles spring-design, composite-micromechanics, and
vibration-of-springs relations rather than any external test case. The
self-check independently re-derives the global optimum -- across both wire
treatments, and separately the frequency-optimized alternative under each
fatigue-life philosophy -- with a bounded constrained solver (SciPy
trust-constr, warm-started from a differential-evolution feasibility
search), and separately cross-checks the same optima with an independent
differential-evolution solve of the actual objective (not just a feasibility
search), confirming both match the sealed ground truth, so the sealed
target is never taken on faith.
"""
import json
from pathlib import Path

import numpy as np
from scipy.optimize import NonlinearConstraint, differential_evolution, minimize

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = REPO / "environment" / "data" / "spring_optimization_problem.json"
TRUTH = REPO / "tests" / "ground_truth.json"

# This latch's own requirements, independent of material/treatment choice.
F_OP_N = 55.0          # force the spring must deliver at full engagement (N)
DELTA_REQ_MM = 18.0    # deflection over which F_OP_N must be delivered (mm)
D_MAX_MM = 14.0        # housing bore clearance (mm)
C_MAX = 12.0           # maximum spring index D/d (manufacturability limit)
OVERSUPPLY = 1.5       # a design may deliver at most this multiple of F_OP_N
F_MIN_N = 8.0          # residual preload the spring cycles down to in service (N)
SF_FATIGUE = 1.15      # required fatigue safety factor
CLASH_MM = 2.0         # working clearance left in the free length beyond full deflection

# Operating environment: the latch spring sees an elevated ambient
# temperature relative to the temperature its material properties were
# characterized at, which derates both fatigue strengths linearly.
T_REF_C = 20.0
T_OP_C = 85.0
DERATE_FRAC_PER_C = 0.0015  # fractional strength loss per degree above T_ref

# The composite wire's consolidation/final-anneal temperature -- residual
# stress from constituent CTE mismatch locks in on cooldown from this
# temperature to T_REF_C, and is independent of the later operating
# temperature T_OP_C (that only derates strength, per above). It is also
# independent of the later tempering step below: tempering relaxes the
# matrix's own quench-hardening dislocation structure (which is exactly
# what TEMPERING_RESPONSE's temper-dependent strength/toughness values
# already capture), but the CTE-mismatch stress modeled here is a separate,
# coherent elastic state set purely by cooling from the stress-free,
# fully-consolidated state at T_PROCESS_C -- it re-establishes itself
# identically on any subsequent cooldown to T_REF_C as long as the part is
# never reheated above T_PROCESS_C in between. Every TEMPERING_RESPONSE
# condition (<=600 C) satisfies that, so tau_res is correctly independent
# of which temper temperature wins.
T_PROCESS_C = 600.0

# The latch actuates repeatedly in service; its spring must not be prone to
# surge (resonant amplification of the coil-to-coil wave set up by each
# actuation). F_OPERATING_HZ is this latch's own actuation rate;
# FREQ_SAFETY_MARGIN is the minimum ratio of the spring's own fundamental
# natural frequency to that actuation rate, a standard design rule of thumb
# for avoiding surge.
F_OPERATING_HZ = 20.0
FREQ_SAFETY_MARGIN = 15.0

# The frequency-optimized alternative (see requirements_text below) may cost
# up to this multiple of the minimum-cost design's own cost.
FREQ_ALT_COST_CAP_MULTIPLIER = 1.15

# Process-robustness noise magnitudes. These are NOT restated in the shipped
# data file -- they are exactly the same "low"/"high" noise-condition
# offsets generate_taguchi.py uses to build taguchi_spring_robustness.csv
# (mean coil diameter D is deliberately left noise-free there, and stays
# noise-free here for the same reason). Whoever solves this task must
# recover these two numbers from that CSV, not from this script.
DD_NOISE_MM = 0.015   # wire-diameter manufacturing-tolerance noise
DN_NOISE = 0.2        # active-coil manufacturing-tolerance noise

# Finite-life (Basquin) fatigue background data, for the frequency-optimized
# alternative's fatigue-life-philosophy judgment call only -- see
# requirements_text below. tau_a_allow(N) = TAU_F_PRIME_NMM2 * (2N)**B_EXP is
# Basquin's equation for the fully-reversed shear-fatigue-strength/life
# relation; RATED_QUALIFICATION_CYCLES is the actuation-cycle count this
# latch design is being qualified against, not a claim about how long any
# individual unit will actually be used.
TAU_F_PRIME_NMM2 = 1650.0
B_EXP = -0.09
RATED_QUALIFICATION_CYCLES = 50000

# Material properties, keyed by the `material` variant code in
# morphological_chart.json. Only the row matching the morphological stage's
# own winning combination applies to this latch. Each wire is a particulate
# metal-matrix composite: a metal-alloy matrix phase reinforced with a hard
# ceramic-like particulate phase. `*_base_Nmm2`/`G_Nmm2`/`tau_allow_Nmm2` are
# the composite's own already-homogenized mechanical properties (as a
# material datasheet would report them); `matrix_*`/`reinforcement_*` are
# the two constituent phases' own properties, needed to derive the
# composite's thermal and dynamic behavior -- a real composite datasheet
# reports mechanical properties directly but not always its thermal-mismatch
# or homogenized-density behavior, which is why both still have to be
# derived from the constituents. D3, the row the morphological stage always
# selects, omits its own `tau_allow_Nmm2`/`S_se_base_Nmm2`/`S_su_Nmm2` for a
# further reason -- see tempering_response below.
MATERIAL_OPTIONS = {
    "D1": {"name": "particulate-reinforced Ni-alloy matrix wire (low reinforcement fraction)",
           "G_Nmm2": 79000.0, "tau_allow_Nmm2": 590.0,
           "S_se_base_Nmm2": 380.0, "S_su_Nmm2": 1290.0,
           "matrix_alpha_per_C": 1.58e-5, "matrix_K_Nmm2": 158000.0, "matrix_E_Nmm2": 205000.0,
           "reinforcement_alpha_per_C": 6.9e-6, "reinforcement_K_Nmm2": 290000.0,
           "reinforcement_vol_fraction": 0.10,
           "matrix_density_kg_m3": 8400.0, "reinforcement_density_kg_m3": 4930.0},
    "D2": {"name": "particulate-reinforced Fe-alloy matrix wire (high reinforcement fraction)",
           "G_Nmm2": 69500.0, "tau_allow_Nmm2": 520.0,
           "S_se_base_Nmm2": 310.0, "S_su_Nmm2": 1100.0,
           "matrix_alpha_per_C": 1.72e-5, "matrix_K_Nmm2": 140000.0, "matrix_E_Nmm2": 193000.0,
           "reinforcement_alpha_per_C": 4.6e-6, "reinforcement_K_Nmm2": 310000.0,
           "reinforcement_vol_fraction": 0.22,
           "matrix_density_kg_m3": 7870.0, "reinforcement_density_kg_m3": 4930.0},
    "D3": {"name": "particulate-reinforced Fe-Cr-alloy matrix wire (moderate reinforcement fraction)",
           "G_Nmm2": 79300.0,
           # Unlike D1/D2 above, no tau_allow_Nmm2 / S_se_base_Nmm2 / S_su_Nmm2 here: this
           # matrix alloy's strength depends on its post-consolidation temper -- see
           # tempering_response below.
           "matrix_alpha_per_C": 1.08e-5, "matrix_K_Nmm2": 172000.0, "matrix_E_Nmm2": 207000.0,
           "reinforcement_alpha_per_C": 5.6e-6, "reinforcement_K_Nmm2": 265000.0,
           "reinforcement_vol_fraction": 0.24,
           "matrix_density_kg_m3": 7750.0, "reinforcement_density_kg_m3": 4930.0},
}
MATERIAL_SELECTED = "D3"  # matches morphological_chart.json's best_combination

# D3's matrix alloy is temper-hardened after consolidation. tempering_response
# tabulates hardness, the same three strength properties D1/D2 give directly
# above, and Charpy V-notch impact toughness, each at a discrete tempering
# temperature -- a standard manufacturer tempering-response curve. The lowest-
# temper condition has the greatest strength but the least toughness, and one
# condition sits inside this alloy's classical tempered-martensite-
# embrittlement band (roughly 260-370 C for many low-alloy steels), where
# toughness dips even though temper temperature -- and hence strength -- is
# not at its lowest; neither is labeled unsafe here, but both fail
# CHARPY_MIN_TOUGHNESS_J. Every other condition clears it; the one actually
# used is whichever, combined with a wire-treatment choice, gives the global
# minimum-cost design.
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

# Lateral-buckling slenderness limit (free length / mean coil diameter),
# keyed by the `end_fixation` variant code. Better-restrained ends tolerate
# a more slender spring before it buckles laterally under axial load.
END_FIXATION_BUCKLING_LIMIT = {"C1": 2.6, "C2": 4.0, "C3": 4.5}
END_FIXATION_SELECTED = "C3"  # matches morphological_chart.json's best_combination

# Wire-treatment options: shot peening raises the fatigue (endurance) limit
# via residual compressive surface stress, at a higher relative material
# cost; it does not change the static allowable stress or ultimate strength,
# and it is independent of the composite's own processing-derived residual
# stress below (that is locked in before the finished wire is ever peened).
WIRE_TREATMENTS = {
    "unpeened": {"S_se_multiplier": 1.0, "relative_cost_multiplier": 1.0},
    "peened": {"S_se_multiplier": 1.35, "relative_cost_multiplier": 1.20},
}

_mat = MATERIAL_OPTIONS[MATERIAL_SELECTED]
G_NMM2 = _mat["G_Nmm2"]
_DERATE = 1.0 - DERATE_FRAC_PER_C * (T_OP_C - T_REF_C)
_R_CRIT = END_FIXATION_BUCKLING_LIMIT[END_FIXATION_SELECTED]

# Strength properties are NOT fixed at import time like G_NMM2 above -- which
# tempering condition wins is only known after the search in solve_reference()
# below, so these start as placeholders and are set by _apply_temper(), called
# once per (tempering condition, treatment) trial during that search and left
# set to the winner once it concludes.
TAU_ALLOW_NMM2 = None
S_SU_NMM2 = None
_S_SE_BASE_SELECTED = None
SELECTED_TEMPER_TEMP_C = None


def _apply_temper(row):
    """Point the module-level strength constants g1/_fatigue_g/_S_se_eff read
    at the given tempering_response row. tau_allow is not temperature-derated
    (matching the static-allowable-stress convention the material table
    already used); S_su and the pre-treatment S_se_base are, exactly as
    before."""
    global TAU_ALLOW_NMM2, S_SU_NMM2, _S_SE_BASE_SELECTED, SELECTED_TEMPER_TEMP_C
    TAU_ALLOW_NMM2 = row["tau_allow_Nmm2"]
    S_SU_NMM2 = row["S_su_Nmm2"] * _DERATE
    _S_SE_BASE_SELECTED = row["S_se_base_Nmm2"] * _DERATE
    SELECTED_TEMPER_TEMP_C = row["temper_temp_C"]


def eligible_temper_rows():
    """Tempering conditions clearing the stated minimum Charpy toughness --
    the only ones a correct solution ever solves the sizing problem for."""
    return [r for r in TEMPERING_RESPONSE if r["charpy_impact_J"] >= CHARPY_MIN_TOUGHNESS_J]


def turner_effective_cte(mat):
    """Turner's model: the composite's homogenized effective CTE, weighting
    each phase's own CTE by its volume fraction and bulk modulus."""
    Vr = mat["reinforcement_vol_fraction"]
    Vm = 1.0 - Vr
    num = (Vm * mat["matrix_K_Nmm2"] * mat["matrix_alpha_per_C"]
           + Vr * mat["reinforcement_K_Nmm2"] * mat["reinforcement_alpha_per_C"])
    den = Vm * mat["matrix_K_Nmm2"] + Vr * mat["reinforcement_K_Nmm2"]
    return num / den


def thermal_residual_shear_Nmm2(mat, t_process_C, t_ref_C):
    """Thermal residual stress locked into the matrix by the two phases'
    mismatched contraction on cooldown from t_process_C to t_ref_C (a
    standard constrained-mismatch estimate), converted from the resulting
    normal (axial) matrix stress to a shear-equivalent via the von Mises
    relation. Independent of wire treatment, of the later operating
    temperature T_OP_C, and of the tempering condition (a coherent
    CTE-mismatch elastic state, not the matrix's quench-hardening
    dislocation structure that tempering acts on -- see T_PROCESS_C)."""
    Vr = mat["reinforcement_vol_fraction"]
    sigma_res = ((Vr / (1.0 - Vr)) * mat["matrix_E_Nmm2"]
                 * (mat["matrix_alpha_per_C"] - mat["reinforcement_alpha_per_C"])
                 * (t_process_C - t_ref_C))
    return sigma_res / np.sqrt(3.0)


def composite_density_kg_m3(mat):
    """Rule-of-mixtures homogenized mass density of the two-phase composite
    wire, weighting each phase's own density by its volume fraction."""
    Vr = mat["reinforcement_vol_fraction"]
    Vm = 1.0 - Vr
    return Vm * mat["matrix_density_kg_m3"] + Vr * mat["reinforcement_density_kg_m3"]


def natural_frequency_hz(x, rho_kg_m3, G_nmm2=None):
    """Fundamental natural frequency of a helical compression spring with
    both ends fixed against rotation (the standard spring-surge check),
    with d, D, Na, G in consistent units. d and D are given in mm, G in
    N/mm^2, and rho in kg/m^3 here, so the 1e6 factor below carries out the
    mm->m and N/mm^2->Pa unit conversions needed to return f_n in Hz."""
    if G_nmm2 is None:
        G_nmm2 = G_NMM2
    d, D, Na = x
    return 1.0e6 * (2.0 / np.pi) * (d / (Na * D**2)) * np.sqrt(G_nmm2 / (32.0 * rho_kg_m3))


ALPHA_EFF_SELECTED = turner_effective_cte(_mat)
TAU_RES_NMM2 = thermal_residual_shear_Nmm2(_mat, T_PROCESS_C, T_REF_C)
RHO_EFF_SELECTED = composite_density_kg_m3(_mat)
FREQ_FLOOR_HZ = FREQ_SAFETY_MARGIN * F_OPERATING_HZ

BOUNDS = {"d_mm": [0.5, 2.0], "D_mm": [4.0, 14.0], "Na": [2.0, 30.0]}

PROBLEM = {
    "variables": ["d_mm", "D_mm", "Na"],
    "bounds": BOUNDS,
    "material_options": MATERIAL_OPTIONS,
    "end_fixation_buckling_limits": END_FIXATION_BUCKLING_LIMIT,
    "wire_treatments": WIRE_TREATMENTS,
    "tempering_response": TEMPERING_RESPONSE,
    "requirements": {
        "F_op_N": F_OP_N, "delta_req_mm": DELTA_REQ_MM,
        "D_max_mm": D_MAX_MM, "spring_index_max": C_MAX,
        "oversupply_factor": OVERSUPPLY, "F_min_N": F_MIN_N,
        "fatigue_safety_factor": SF_FATIGUE, "clash_allowance_mm": CLASH_MM,
        "operating_temp_C": T_OP_C, "material_reference_temp_C": T_REF_C,
        "strength_derating_fraction_per_C": DERATE_FRAC_PER_C,
        "composite_process_temp_C": T_PROCESS_C,
        "operating_actuation_frequency_hz": F_OPERATING_HZ,
        "frequency_safety_margin": FREQ_SAFETY_MARGIN,
        "frequency_alternative_cost_cap_multiplier": FREQ_ALT_COST_CAP_MULTIPLIER,
        "basquin_fatigue_strength_coefficient_Nmm2": TAU_F_PRIME_NMM2,
        "basquin_fatigue_strength_exponent": B_EXP,
        "rated_qualification_cycles": RATED_QUALIFICATION_CYCLES,
        "charpy_min_toughness_J": CHARPY_MIN_TOUGHNESS_J,
    },
    "objective": "minimize cost(d, D, Na, treatment) = "
                 "relative_cost_multiplier(treatment) * "
                 "(pi^2/4) * d^2 * D * (Na + 2)  "
                 "[relative material cost; squared-and-ground ends -> Na+2 "
                 "total coils]",
    "physical_relations": [
        "Wahl's stress-concentration factor for a round-wire helical "
        "spring applies wherever spring stress is computed below, as a "
        "function of the spring index C = D/d.",
        "Peak shear stress in the wire under an applied axial force F "
        "follows the standard closed-form relation for a round-wire "
        "helical compression spring, incorporating the Wahl factor above.",
        "Spring rate follows the standard closed-form relation for a "
        "round-wire helical compression spring (force per unit "
        "deflection), as a function of shear modulus G, wire diameter d, "
        "mean coil diameter D, and active coil count Na.",
        "Fatigue (infinite-life criterion): under a force that cycles "
        "between F_min and F_max, the mean and alternating force "
        "components are the average and half-range of F_min and F_max; "
        "the corresponding mean and alternating shear stresses follow the "
        "peak-shear-stress relation above. Because that relation is "
        "linear in force, the load line is proportional (passes through "
        "the origin), so the standard linear (modified-Goodman) "
        "shear-stress damage criterion for proportional loading applies: "
        "normalize the alternating stress against the endurance limit "
        "S_se and the mean stress against the ultimate shear strength "
        "S_su, sum the two ratios, and require the sum not exceed the "
        "reciprocal of the required safety factor n_f. The mean-stress "
        "term must use tau_m_total, the service mean shear stress tau_m "
        "plus the composite's own thermal residual shear stress tau_res "
        "defined below -- not tau_m alone.",
        "Fatigue (finite-life criterion, an alternative to the "
        "infinite-life criterion above): Basquin's equation relates the "
        "allowable fully-reversed alternating stress to a target cycle "
        "count via a fatigue-strength coefficient and exponent (given "
        "below); at a stated rated qualification cycle count it gives an "
        "allowable alternating stress in place of the endurance limit "
        "S_se in the same mean/alternating damage-sum criterion above, "
        "still subject to the same wire-treatment multiplier and safety "
        "factor. This finite-life criterion is not automatically the "
        "right or wrong choice relative to the infinite-life one above -- "
        "which one governs is stated in requirements_text below.",
        "Both fatigue strengths derate linearly with operating "
        "temperature above the temperature the material was "
        "characterized at, by strength_derating_fraction_per_C per "
        "degree C of temperature rise, applied to both S_se and S_su "
        "before any other adjustment; the finite-life allowable stress "
        "above is not itself temperature-derated by this factor, since "
        "it is not S_se, but does carry the same wire-treatment "
        "multiplier described next.",
        "Shot peening multiplies only the endurance limit S_se -- and, "
        "for a design using the finite-life criterion above, the "
        "Basquin-derived allowable alternating stress the same way -- by "
        "the treatment's S_se_multiplier (it does not affect tau_allow "
        "or S_su); the treatment's relative_cost_multiplier scales the "
        "objective's material cost per unit volume.",
        "Free length and lateral stability: solid height Ls = (Na+2)*d; "
        "free length L0 = Ls + delta_req_mm + clash_allowance_mm. A "
        "helical compression spring becomes unstable against lateral "
        "buckling once its slenderness ratio L0/D exceeds a critical "
        "value that depends on how the spring's ends are restrained "
        "against tipping -- more restraint tolerates a more slender "
        "spring before buckling.",
        "Composite effective CTE: each wire is a two-phase particulate "
        "composite (matrix phase m, reinforcement phase r, volume "
        "fractions V_m + V_r = 1). Its homogenized effective coefficient "
        "of thermal expansion follows Turner's classical self-consistent "
        "homogenization model, weighting each phase's own CTE by its "
        "volume fraction and its own bulk modulus.",
        "Composite thermal residual stress: because the matrix and "
        "reinforcement phases contract by different amounts on cooling "
        "from the composite's processing temperature "
        "composite_process_temp_C to the reference temperature "
        "material_reference_temp_C, a residual normal stress is locked "
        "into the matrix. Estimate it by the standard constrained-"
        "mismatch approach -- proportional to the reinforcement's volume "
        "ratio V_r/(1-V_r), the matrix phase's own Young's modulus E_m, "
        "and the two phases' CTE mismatch (alpha_m - alpha_r) times the "
        "temperature drop (T_process - T_ref) -- then convert that normal "
        "stress to a shear-equivalent by the von Mises relation. This "
        "residual shear stress tau_res adds directly to the mean shear "
        "stress tau_m in the fatigue criterion above; it is fixed by the "
        "composite's own processing history, so it applies regardless of "
        "wire treatment and does not depend on the later operating "
        "temperature T_op.",
        "Composite mass density: the homogenized density of the "
        "two-phase wire follows the standard rule of mixtures, weighting "
        "each phase's own mass density by its volume fraction.",
        "Fundamental natural frequency: a helical compression spring with "
        "both ends fixed against rotation has a classical spring-surge "
        "natural frequency, increasing with wire diameter d and with "
        "sqrt(shear modulus / mass density), and decreasing with mean "
        "coil diameter D and active coil count Na. Use the composite's "
        "own homogenized density rho_eff from above as the mass density, "
        "and take care with units -- d and D are given in mm, G in "
        "N/mm^2, and rho_eff in kg/m^3 -- to report the result in Hz.",
        "Process robustness: taguchi_spring_robustness.csv already "
        "characterizes this same spring family's wire-diameter and "
        "active-coil manufacturing-tolerance noise, as the named 'low' "
        "and 'high' offsets from each run's nominal d and Na (mean coil "
        "diameter D carries no noise in that study, deliberately). That "
        "same noise applies to any (d, D, Na) design at this stage, not "
        "only to the nine runs that CSV happens to tabulate.",
        "Heat treatment: the selected material's matrix alloy is temper-"
        "hardened after consolidation. tempering_response gives its "
        "static allowable stress, ultimate strength, and endurance limit "
        "-- the same three properties D1/D2 give directly in "
        "material_options -- plus hardness and Charpy V-notch impact "
        "toughness, at each of several discrete tempering temperatures. "
        "Each row stands on its own as a complete, internally consistent "
        "set of properties for that tempering condition; higher tempering "
        "temperature does not monotonically improve or worsen every "
        "property together.",
    ],
    "requirements_text": [
        "The spring must deliver at least F_op_N of force at a deflection "
        "of delta_req_mm, and must not deliver more than "
        "oversupply_factor * F_op_N at that same deflection.",
        "The peak static shear stress (at the fully engaged force F_op_N) "
        "must not exceed the allowable stress of the material selected in "
        "the concept-selection stage.",
        "In service the spring cycles between F_min_N and F_op_N on every "
        "latch actuation; the infinite-life fatigue damage criterion "
        "above must be satisfied with safety factor fatigue_safety_factor, "
        "using temperature-derated strengths at operating_temp_C, the "
        "composite wire's own thermal residual shear stress, and "
        "whichever wire-treatment option is used for that design -- this "
        "is the fatigue criterion the minimum-cost design (below) must "
        "satisfy; it is not a judgment call.",
        "The mean coil diameter D must fit within the housing bore, "
        "D <= D_max_mm.",
        "The spring index D/d must not exceed spring_index_max, or the "
        "spring cannot be reliably coiled by the intended process.",
        "The spring's slenderness ratio L0/D must not exceed the "
        "buckling limit for the end-fixation variant selected in the "
        "concept-selection stage.",
        "The spring's own fundamental natural frequency must be at least "
        "frequency_safety_margin times operating_actuation_frequency_hz, "
        "so that repeated latch actuation cannot excite spring surge.",
        "The minimum-cost design (and the frequency-optimized alternative "
        "below, on whichever of its own requirements do not concern the "
        "frequency floor itself) must also remain feasible under the "
        "process-robustness noise described above: re-evaluate the "
        "fatigue, buckling, and frequency-margin requirements at whichever "
        "combination of +/- that noise on d and Na is actually worst-case "
        "for each requirement separately -- the worst-case direction is "
        "not necessarily the same for all three, and identifying it for "
        "each is a matter of engineering reasoning about how that "
        "requirement responds to a thinner-or-thicker wire and a "
        "lower-or-higher coil count, not something stated here.",
        "Report the selected material's effective coefficient of thermal "
        "expansion from Turner's model, and its homogenized mass density, "
        "as part of the parametric-optimization result.",
        "Separately from the minimum-cost design, determine the "
        "maximum-natural-frequency design that uses the same wire "
        "treatment as the minimum-cost design and satisfies every "
        "requirement above except the frequency floor itself (and the "
        "process-robustness re-check of that floor specifically -- the "
        "process-robustness re-checks of fatigue and buckling still "
        "apply), while its cost does not exceed "
        "frequency_alternative_cost_cap_multiplier times the minimum-cost "
        "design's own cost -- and report whether this frequency-optimized "
        "alternative is actually a different design from the minimum-cost "
        "one. For this alternative design only, and not for the "
        "minimum-cost design, choosing between the infinite-life and "
        "finite-life fatigue criteria above is a genuine judgment call: "
        "the finite-life criterion is only as good as the rated "
        "qualification cycle count it is pinned to, and is a defensible "
        "choice precisely when that stated rating -- not an unbounded "
        "service life -- is what the design is actually being qualified "
        "against; state and justify whichever criterion is used for this "
        "alternative as part of the synthesis explanation.",
        "The tempering condition used for the selected material's wire "
        "must be chosen from tempering_response and must clear "
        "charpy_min_toughness_J; among the tempering conditions that do, "
        "and jointly with both wire-treatment options, the minimum-cost "
        "design above must be the global minimum over every combination "
        "of the two -- not assumed from the highest-strength condition "
        "alone, and not decided independently of the wire-treatment "
        "choice.",
    ],
    "notes": "d, D in mm, Na dimensionless (treated as continuous for "
             "optimization purposes). The relations and requirements above "
             "are given as physical facts, not as pre-derived inequality "
             "functions -- expressing them as constraints g(d, D, Na) <= 0, "
             "identifying which material and end-fixation rows apply, "
             "deriving the composite's effective CTE, thermal residual "
             "stress, and homogenized density from its constituent phases, "
             "recovering the process-robustness noise magnitudes from "
             "taguchi_spring_robustness.csv, and comparing both "
             "wire-treatment options is part of solving this stage.",
}


def wahl(C):
    return (4*C - 1)/(4*C - 4) + 0.615/C


def _S_se_eff(treatment):
    return _S_SE_BASE_SELECTED * WIRE_TREATMENTS[treatment]["S_se_multiplier"]


def _tau_a_allow_basquin(N=RATED_QUALIFICATION_CYCLES):
    return TAU_F_PRIME_NMM2 * (2.0 * N) ** B_EXP


def cost(x, treatment):
    d, D, Na = x
    vol = (np.pi**2 / 4.0) * d**2 * D * (Na + 2.0)
    return vol * WIRE_TREATMENTS[treatment]["relative_cost_multiplier"]


def g1(x):
    d, D, Na = x
    C = D / d
    return 8*F_OP_N*D*wahl(C)/(np.pi*d**3) - TAU_ALLOW_NMM2


def g2(x):
    d, D, Na = x
    k = G_NMM2*d**4/(8*D**3*Na)
    return F_OP_N - k*DELTA_REQ_MM


def g3(x):
    d, D, Na = x
    k = G_NMM2*d**4/(8*D**3*Na)
    return k*DELTA_REQ_MM - OVERSUPPLY*F_OP_N


def g4(x):
    d, D, Na = x
    return D - D_MAX_MM


def g5(x):
    d, D, Na = x
    return D/d - C_MAX


def _fatigue_g(x, treatment, philosophy="infinite"):
    """Linear mean/alternating shear-stress damage criterion, against
    temperature-derated, treatment-adjusted strengths, with the composite's
    own thermal residual shear stress added to the service mean stress.
    philosophy="infinite" uses the endurance limit S_se (the criterion the
    minimum-cost design always uses); philosophy="finite" uses the
    Basquin-derived allowable at RATED_QUALIFICATION_CYCLES instead (only
    ever used for the frequency-optimized alternative)."""
    d, D, Na = x
    C = D / d
    Kw = wahl(C)
    Fa = (F_OP_N - F_MIN_N) / 2.0
    Fm = (F_OP_N + F_MIN_N) / 2.0
    tau_a = 8*Fa*D*Kw/(np.pi*d**3)
    tau_m = 8*Fm*D*Kw/(np.pi*d**3) + TAU_RES_NMM2
    if philosophy == "infinite":
        allow_a = _S_se_eff(treatment)
    elif philosophy == "finite":
        allow_a = _tau_a_allow_basquin() * WIRE_TREATMENTS[treatment]["S_se_multiplier"]
    else:
        raise ValueError(f"unknown fatigue-life philosophy {philosophy!r}")
    return tau_a/allow_a + tau_m/S_SU_NMM2 - 1.0/SF_FATIGUE


def g6(x, treatment):
    """Infinite-life fatigue criterion -- the only one the minimum-cost
    design is ever checked against."""
    return _fatigue_g(x, treatment, philosophy="infinite")


def g7(x):
    """Lateral-buckling slenderness limit for the selected end-fixation."""
    d, D, Na = x
    Ls = (Na + 2.0)*d
    L0 = Ls + DELTA_REQ_MM + CLASH_MM
    return L0/D - _R_CRIT


def g8(x):
    """Fundamental-natural-frequency floor against spring surge."""
    return FREQ_FLOOR_HZ - natural_frequency_hz(x, RHO_EFF_SELECTED)


def frequency_margin_ratio(x):
    return natural_frequency_hz(x, RHO_EFF_SELECTED) / F_OPERATING_HZ


def g9_fatigue(x, treatment, philosophy="infinite"):
    """Process-robustness re-check of the fatigue criterion: worst-case
    direction is a thinner wire (raises both shear-stress components, and
    Na does not enter the fatigue relation at all, so the active-coil noise
    is irrelevant here)."""
    d, D, Na = x
    return _fatigue_g((d - DD_NOISE_MM, D, Na), treatment, philosophy=philosophy)


def g9_buckling(x):
    """Process-robustness re-check of the buckling limit: worst-case
    direction is a *thicker* wire (raises solid height Ls, hence free
    length) together with *more* active coils (raises Ls directly)."""
    d, D, Na = x
    return g7((d + DD_NOISE_MM, D, Na + DN_NOISE))


def g9_freq(x):
    """Process-robustness re-check of the frequency floor: f_n increases
    with d and decreases with Na, so the worst case is a *thinner* wire
    together with *more* active coils -- the opposite d-direction from the
    fatigue re-check above, since fatigue and frequency respond to wire
    diameter with opposite sign."""
    d, D, Na = x
    return g8((d - DD_NOISE_MM, D, Na + DN_NOISE))


CONSTRAINTS_STATIC = (g1, g2, g3, g4, g5, g7, g8)


def _full_cons_vec(x, treatment, philosophy="infinite", include_freq_floor=True):
    """Positive-is-feasible margins for every requirement (nominal +
    process-robustness), for the given fatigue-life philosophy. When
    include_freq_floor is False, the frequency floor itself and its
    process-robustness re-check are both omitted (used for the
    frequency-optimized alternative, which maximizes f_n rather than being
    bound by a floor on it)."""
    out = [-g1(x), -g2(x), -g3(x), -g4(x), -g5(x), -g7(x),
           -_fatigue_g(x, treatment, philosophy=philosophy),
           -g9_fatigue(x, treatment, philosophy=philosophy), -g9_buckling(x)]
    if include_freq_floor:
        out += [-g8(x), -g9_freq(x)]
    return np.array(out)


def _feasibility_violation(x, treatment, philosophy="infinite", include_freq_floor=True):
    gs = _full_cons_vec(x, treatment, philosophy=philosophy, include_freq_floor=include_freq_floor)
    return float(np.sum(np.clip(-gs, 0.0, None)))


def _bounds_list():
    return [tuple(BOUNDS["d_mm"]), tuple(BOUNDS["D_mm"]), tuple(BOUNDS["Na"])]


def solve_treatment(treatment, seed=0):
    """Independently re-solve the minimum-cost design for one wire
    treatment, against every requirement (g1-g9 above, infinite-life
    fatigue only): a differential-evolution feasibility search locates a
    feasible seed, then trust-constr refines it to the true constrained
    optimum."""
    bounds = _bounds_list()
    de_res = differential_evolution(
        lambda x: _feasibility_violation(x, treatment), bounds=bounds, seed=seed,
        tol=1e-12, maxiter=800, popsize=30, polish=True,
    )
    if _feasibility_violation(de_res.x, treatment) > 1e-6:
        return None
    nlc = NonlinearConstraint(lambda x: _full_cons_vec(x, treatment), 0, np.inf)
    res = minimize(lambda x: cost(x, treatment), de_res.x, method="trust-constr", bounds=bounds,
                    constraints=[nlc], options={"maxiter": 8000, "gtol": 1e-13, "xtol": 1e-15})
    if not res.success or _feasibility_violation(res.x, treatment) > 1e-6:
        return None
    return res


def solve_reference(seed=0):
    """Solve every (eligible tempering condition, wire treatment) pair --
    against every constraint, including the frequency floor and its
    process-robustness re-check -- and return the cheapest feasible one.
    'Eligible' means the tempering condition's own Charpy toughness clears
    CHARPY_MIN_TOUGHNESS_J; the two that do not are never even solved,
    exactly as a correct solution should exclude them before optimizing
    rather than after."""
    candidates = {}
    for row in eligible_temper_rows():
        _apply_temper(row)
        for treatment in WIRE_TREATMENTS:
            best = solve_treatment(treatment, seed=seed)
            if best is not None:
                candidates[(row["temper_temp_C"], treatment)] = (best, row)
    if not candidates:
        return None, None, None
    winner_key = min(candidates, key=lambda k: candidates[k][0].fun)
    best, winner_row = candidates[winner_key]
    _apply_temper(winner_row)  # leave module state on the winner, not the last row tried
    return winner_key[1], best, winner_row


_ALT_STARTS = [
    np.array([1.5, 13.0, 3.0]), np.array([1.6, 14.0, 4.0]), np.array([1.4, 10.0, 6.0]),
    np.array([1.8, 14.0, 3.0]), np.array([1.55, 14.0, 5.0]), np.array([1.45, 14.0, 4.5]),
]


def solve_frequency_optimized_alternative(treatment, philosophy, cost_cap):
    """Maximize the fundamental natural frequency subject to every
    requirement except the frequency floor and its process-robustness
    re-check (g8, g9_freq) -- since that is what's being maximized -- a cap
    on cost, and the stated fatigue-life philosophy, for a single fixed
    wire treatment."""
    bounds = _bounds_list()

    def cons_vec(x):
        base = _full_cons_vec(x, treatment, philosophy=philosophy, include_freq_floor=False)
        return np.append(base, cost_cap - cost(x, treatment))

    def viol(x):
        return float(np.sum(np.clip(-cons_vec(x), 0.0, None)))

    nlc = NonlinearConstraint(cons_vec, 0, np.inf)
    best = None
    for x0 in _ALT_STARTS:
        res = minimize(lambda x: -natural_frequency_hz(x, RHO_EFF_SELECTED), x0, method="trust-constr",
                        bounds=bounds, constraints=[nlc], options={"maxiter": 8000, "gtol": 1e-13, "xtol": 1e-15})
        if not res.success or viol(res.x) > 1e-6:
            continue
        fn = natural_frequency_hz(res.x, RHO_EFF_SELECTED)
        if best is None or fn > natural_frequency_hz(best.x, RHO_EFF_SELECTED):
            best = res
    return best


def _de_cross_check_reference(treatment, x_star, cost_star, seed=11):
    """Independent differential-evolution solve of the actual minimum-cost
    objective (not just a feasibility search): minimizes cost plus a large
    penalty for constraint violation, and confirms it lands close to the
    trust-constr optimum. A genuinely separate solver/search strategy from
    solve_treatment above, not merely a second call to the same routine."""
    bounds = _bounds_list()

    def penalized(x):
        v = _feasibility_violation(x, treatment)
        return cost(x, treatment) + 1.0e4 * v

    res = differential_evolution(penalized, bounds=bounds, seed=seed, tol=1e-10, maxiter=600, popsize=40, polish=True)
    if _feasibility_violation(res.x, treatment) > 1e-4:
        return False
    return abs(cost(res.x, treatment) - cost_star) <= 0.03 * cost_star


def _de_cross_check_alt(treatment, philosophy, cost_cap, fn_star, seed=11):
    """Independent differential-evolution solve of the frequency-optimized
    alternative's actual objective (maximize f_n), penalized for constraint
    violation, confirming it lands close to the trust-constr optimum."""
    bounds = _bounds_list()

    def penalized(x):
        v = _feasibility_violation(x, treatment, philosophy=philosophy, include_freq_floor=False)
        v += max(0.0, cost(x, treatment) - cost_cap) / max(cost_cap, 1.0)
        return -natural_frequency_hz(x, RHO_EFF_SELECTED) + 1.0e5 * v

    res = differential_evolution(penalized, bounds=bounds, seed=seed, tol=1e-10, maxiter=600, popsize=40, polish=True)
    total_viol = _feasibility_violation(res.x, treatment, philosophy=philosophy, include_freq_floor=False)
    total_viol += max(0.0, cost(res.x, treatment) - cost_cap)
    if total_viol > 1e-3:
        return False
    fn = natural_frequency_hz(res.x, RHO_EFF_SELECTED)
    return abs(fn - fn_star) <= 0.03 * fn_star


def check():
    if not OUT.exists() or not TRUTH.exists():
        return False
    truth = json.loads(TRUTH.read_text())
    on_disk = json.loads(OUT.read_text())
    if "basquin_fatigue_strength_coefficient_Nmm2" not in on_disk.get("requirements", {}):
        return False  # stale pre-process-robustness/fatigue-philosophy schema on disk
    if "tempering_response" not in on_disk:
        return False  # stale pre-heat-treatment schema on disk

    treatment, best, temper_row = solve_reference()
    if best is None:
        return False
    if treatment != truth["spring_treatment_true"]:
        return False
    if abs(temper_row["temper_temp_C"] - truth["spring_temper_temp_C_true"]) > 1e-6:
        return False
    if abs(best.fun - truth["spring_f_star_true"]) > 0.02 * truth["spring_f_star_true"]:
        return False
    if not _de_cross_check_reference(treatment, best.x, best.fun):
        return False
    if abs(ALPHA_EFF_SELECTED - truth["composite_cte_eff_true"]) > truth["composite_cte_eff_tol"]:
        return False
    if abs(RHO_EFF_SELECTED - truth["composite_density_true"]) > truth["composite_density_tol"]:
        return False

    cost_cap = FREQ_ALT_COST_CAP_MULTIPLIER * best.fun
    for philosophy, key in (("infinite", "freq_alt_infinite"), ("finite", "freq_alt_finite")):
        alt = solve_frequency_optimized_alternative(treatment, philosophy, cost_cap)
        if alt is None:
            return False
        alt_fn = natural_frequency_hz(alt.x, RHO_EFF_SELECTED)
        alt_cost = cost(alt.x, treatment)
        truth_fn = truth[f"{key}_natural_frequency_hz_true"]
        truth_cost = truth[f"{key}_cost_true"]
        if abs(alt_fn - truth_fn) > 0.05 * truth_fn:
            return False
        if abs(alt_cost - truth_cost) > 0.03 * truth_cost:
            return False
        if not _de_cross_check_alt(treatment, philosophy, cost_cap, alt_fn):
            return False
    return True


def main():
    if check():
        print(f"{OUT} already present and consistent with ground truth; not overwriting")
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(PROBLEM, indent=2))

    treatment, best, temper_row = solve_reference()
    print("independently re-solved global optimum:")
    print("  treatment* =", treatment)
    print("  temper* =", temper_row["temper_temp_C"], "C (HRC", temper_row["hardness_HRC"], ")")
    print("  x* =", best.x, "f* =", best.fun)
    print("  DE cross-check (reference):", _de_cross_check_reference(treatment, best.x, best.fun))
    print("  alpha_eff (Turner, D3) =", ALPHA_EFF_SELECTED)
    print("  tau_res (D3) =", TAU_RES_NMM2)
    print("  rho_eff (D3) =", RHO_EFF_SELECTED)
    print("  f_n(x*) =", natural_frequency_hz(best.x, RHO_EFF_SELECTED), "floor =", FREQ_FLOOR_HZ)

    cost_cap = FREQ_ALT_COST_CAP_MULTIPLIER * best.fun
    for philosophy in ("infinite", "finite"):
        alt = solve_frequency_optimized_alternative(treatment, philosophy, cost_cap)
        fn_alt = natural_frequency_hz(alt.x, RHO_EFF_SELECTED)
        print(f"frequency-optimized alternative ({philosophy}-life, same treatment, cost <= {cost_cap}):")
        print("  x_alt* =", alt.x, "cost_alt =", cost(alt.x, treatment), "f_n_alt =", fn_alt)
        print("  DE cross-check (alt):", _de_cross_check_alt(treatment, philosophy, cost_cap, fn_alt))

    print(f"wrote {OUT}")

    if not check():
        raise SystemExit("spring_optimization_problem.json FAILED self-check against ground truth")
    print("self-check passed")


if __name__ == "__main__":
    main()
