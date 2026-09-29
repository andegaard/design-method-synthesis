# Design Method Synthesis for a Latch Spring

Carry a spring-loaded latch's energy-storage subsystem through a full design methodology:
morphological analysis for concept selection, Axiomatic Design for embodiment selection,
parametric optimization for detailed sizing, Taguchi robust design for tolerance
robustness, and multi-criteria decision-making (Pareto dominance, TOPSIS, and the
weighted-sum method) for final selection among catalog candidates. Produce the two
deliverables below.

## Data

All inputs are under `/app/data`. Nothing outside this directory may be used.

- `/app/data/morphological_chart.json`
- `/app/data/axiomatic_design_candidates.json`
- `/app/data/spring_optimization_problem.json`
- `/app/data/taguchi_spring_robustness.csv` -- per-run, per-noise-condition spring-rate
  measurements for an L9 array over factors A (wire diameter), B (mean coil diameter), and
  C (active coil count); predicting a run's spring rate from its factor levels uses the
  standard helical-spring-rate relation with shear modulus `G = 80000 N/mm^2`, a reference
  value for this study.
- `/app/data/pareto_candidate_designs.csv` -- candidate final `(d_mm, D_mm, Na, treatment)`
  designs.

## Quantities to determine

- Concept selection: the total number of combinations in the morphological chart; the
  number remaining feasible once every pairwise exclusion rule applies; the single
  highest-scoring feasible combination (sum of its four variants' scores) and its score.
- Embodiment selection: for each candidate `X`/`Y`/`Z`, classify its FR-DP matrix as
  `uncoupled`, `decoupled`, or `coupled`; apply Suh's Independence Axiom, then the
  Information Axiom, to recommend one, using each design's own tolerance data and the
  standard normal CDF for its probability of success.
- Parametric optimization: using the material and end-fixation the concept-selection
  stage recommends, derive the constraints from the given physical relations and
  requirements, and solve for the global minimum-cost design jointly across both
  wire-treatment options and every tempering condition in `tempering_response` clearing
  the stated minimum Charpy toughness. The material's constituent data also gives its
  effective CTE, thermal residual stress, and homogenized density, each feeding the fatigue
  and dynamic-response constraints. A feasible design must also withstand the
  wire-diameter/active-coil noise `taguchi_spring_robustness.csv` characterizes, re-checking
  fatigue, buckling, and frequency margin at each requirement's own worst-case noise
  direction. Report `d`, `D`, `Na`, the winning treatment and tempering temperature, the
  minimum cost, its CTE, density, and natural frequency, and confirm every requirement --
  process-robustness included -- is satisfied.
  Separately, find the maximum-natural-frequency design (same treatment and tempering
  condition, every other requirement including fatigue/buckling process-robustness but not
  the frequency floor's own, cost capped relative to the minimum-cost design's own cost); for this
  alternative alone, choosing between the two given fatigue criteria is a genuine judgment
  call with no single correct answer -- pick and justify one, and report whether the
  resulting design differs from the minimum-cost one.
- Robust design (Taguchi): each run's nominal-the-best SN ratio, across its three noise
  conditions; each factor's average SN at each of its three levels; the factor-level
  combination that maximizes SN, and its predicted spring rate at that combination's
  nominal dimensions, using the reference `G` above. Separately: the
  target spring rate is 6.0 N/mm and the quality-loss coefficient is 2.5; using each run's
  own mean measured rate (its three conditions) in place of the predicted rate, apply the
  standard Taguchi quadratic quality-loss function to determine which of the 9 runs
  minimizes loss. Report both quality-loss values and whether most-robust and lowest-loss
  coincide.
- Final design selection: re-verify the feasibility of every candidate against every
  parametric-optimization requirement, process-robustness included, using its own listed
  wire treatment and a 1e-6 numerical tolerance on each constraint. Among the feasible
  candidates, minimize cost, maximize `Na` (durability), and maximize the frequency margin
  ratio (natural frequency divided by
  `operating_actuation_frequency_hz`, same as `frequency_margin_ratio` above) as three
  competing objectives; determine the Pareto-optimal (non-dominated) subset under all three
  at once; then, using weights of 0.45 for cost, 0.35 for durability, and 0.20 for frequency margin,
  apply both TOPSIS (vector normalization) and the weighted-sum method (min-max
  normalization) to the Pareto-optimal set and report both winners and whether they agree.
  Ties at the top go to the lower-cost candidate. If the two methods disagree, choose and
  justify one as the final design in the synthesis explanation.
- Synthesis: state the recommended concept, embodiment, and final design, and whether the
  robust-design stage's two combinations differ. Explain your reasoning (>=150 characters),
  touching on: the concept-selection result; whether the recommended embodiment is coupled
  and its information content versus the alternatives; the parametric optimum's wire
  treatment, tempering condition, and composite CTE, and that its buckling,
  frequency-margin, and residual-stress-inclusive fatigue requirements are satisfied; the
  frequency-optimized alternative's fatigue-life-philosophy choice and whether it differs
  from the minimum-cost design; how the final-selection stage's three competing
  objectives (cost, durability, and frequency margin) trade off across the
  Pareto-optimal set, and the Pareto/TOPSIS/weighted-sum result and whether the two
  methods agree; and the robust-vs-on-target distinction.

## Deliverables

Write two files:

1. `/app/output/design_report.json` -- JSON with exactly these top-level keys:

   - `morphological` (object): `total_combinations`, `feasible_combinations` (ints);
     `best_combination` (object, the four sub-function keys -> chosen variant code);
     `best_score` (int)
   - `axiomatic` (object): `coupling_by_design` (object, `"X"`/`"Y"`/`"Z"` ->
     `"uncoupled"`/`"decoupled"`/`"coupled"`); `information_content_bits` (object, design
     code -> bits; a design failing the Independence Axiom is not a key here);
     `recommended_design` (one of `"X"`/`"Y"`/`"Z"`)
   - `parametric_optimization` (object): `d_mm`, `D_mm`, `Na`, `cost` (numbers);
     `treatment` (`"unpeened"` or `"peened"`); `temper_temp_C` (number);
     `composite_cte_eff_per_C` (number, Turner's
     model result, 1/degree C); `composite_density_kg_m3`, `natural_frequency_hz`,
     `frequency_margin_ratio` (numbers); `frequency_optimized_alternative` (object: `d_mm`,
     `D_mm`, `Na`, `cost`, `natural_frequency_hz`, `frequency_margin_ratio`);
     `frequency_alternative_differs_from_cost_optimum` (bool);
     `frequency_alternative_fatigue_philosophy` (`"infinite_life"` or `"finite_life"`);
     `constraints_satisfied` (bool)
   - `taguchi` (object): `sn_by_run_db` (object, run ID `"1"`..`"9"` -> SN in dB);
     `factor_level_sn_avg_db` (object, `"A"`/`"B"`/`"C"` -> {level `"1"`/`"2"`/`"3"` ->
     average SN}); `most_robust_levels` (object, `"A"`/`"B"`/`"C"` -> level, int);
     `most_robust_predicted_k_Nmm`, `most_robust_quality_loss` (numbers);
     `best_on_target_run_id` (int); `best_on_target_levels` (object like
     `most_robust_levels`); `best_on_target_quality_loss` (number);
     `most_robust_equals_best_on_target` (bool)
   - `pareto` (object): `feasible_candidates` (list of candidate codes satisfying every
     requirement); `pareto_optimal_candidates` (list, the non-dominated subset of the
     feasible candidates); `topsis_winner`, `weighted_sum_winner` (candidate codes);
     `methods_agree` (bool)
   - `synthesis` (object): `recommended_concept` (= `morphological.best_combination`);
     `recommended_embodiment` (= `axiomatic.recommended_design`);
     `recommended_final_design` (= the multi-criteria winner you settle on);
     `robustness_and_on_target_are_different` (bool); `explanation` (the paragraph
     described above)

2. `/app/output/findings.md` -- markdown summary reproducing the reported numbers and
   conclusions, covering concept selection, embodiment selection, parametric optimization,
   robust design, and final design selection.

Every reported value must be computed from the data in `/app/data` and be consistent with
the relations in "Quantities to determine." Do not modify any file in `/app/data`.

You have 9000 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
