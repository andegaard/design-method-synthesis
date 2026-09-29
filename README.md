# design-method-synthesis: design notes

This task asks an agent to carry one mechanical subsystem -- the energy-storage element
of a spring-loaded latch -- through a complete design methodology: concept selection,
embodiment selection, parametric optimization, robust design, and final-design selection,
using five different classical and modern design-theory methods rather than any one in
isolation. Several independent, individually-verifiable stages, no single one of which can
be guessed, skipped, or answered from a memorized constant, plus a synthesis stage that
must genuinely reconcile all five results rather than report five disconnected numbers.

## Difficulty

All data here -- the morphological chart, the three embodiment candidates, the spring
physics problem (including the composite wire's constituent-phase properties), the Taguchi
array, and the twelve final candidates -- is synthetic, authored from scratch for this task,
not drawn from any published case study, catalog, or textbook problem instance. It is
nonetheless physically realistic: every numeric value corresponds to a dimensionally and
physically plausible small helical compression spring, particulate metal-matrix composite
wire, and manufacturing tolerance, and the optimization stage's constraint set was
independently confirmed -- not assumed -- to admit a genuine, well-posed global optimum by
multistart nonlinear solves cross-checked against differential evolution.

A mechanical design engineer carrying a new spring-loaded subsystem from concept through
production release, at a product-development or components-manufacturing organization or
as a consulting design engineer serving one, performs essentially this sequence as a
matter of course: concept screening, embodiment selection under a coupling/information
axiom, first-principles sizing against a full static/fatigue/stability/dynamic requirement
set -- now additionally requiring composite-materials micromechanics where the wire itself
is a particle-reinforced composite, and a vibration check against spring surge -- tolerance-
robustness screening, and multi-criteria selection among supplier-catalog options. Chaining
exactly these five methods on one coherent subsystem is standard structured-design
practice; what makes this instance genuinely hard is that the parametric-optimization stage
is no longer a single-discipline problem, and that it is no longer a single-objective one
either. Deriving a feasible design requires combining three engineering disciplines that a
mechanical-design generalist does not automatically have all of at expert depth:
structural/fatigue spring design, composite-materials micromechanics (Turner's
homogenization model for effective CTE, and a constituent-CTE-mismatch thermal
residual-stress estimate converted through a von Mises shear-equivalence), and the dynamics
of spring surge (a rule-of-mixtures composite density feeding a fundamental-natural-
frequency check). No one discipline alone solves the stage; the residual-stress term
measurably changes which constraint binds at the true optimum, and the frequency-margin
floor is the sole reason an otherwise-attractive large-coil-count design is unsafe, so a
solution that gets the mechanical spring physics exactly right but omits or approximates
either the composite-materials or the dynamics derivation will converge on a design that
looks plausible and is not, in fact, correct. On top of that, the stage now asks for a
second, competing optimization -- the maximum-natural-frequency design under a cost cap --
so the agent must recognize and characterize a genuine trade-off between minimizing cost and
maximizing dynamic margin, not just report a single number.

Two further requirements push the stage past pure computation. First, a feasible design must
also survive the same wire-diameter/active-coil manufacturing noise the robust-design stage
characterizes -- but that noise's magnitude is never stated in `spring_optimization_problem.json`
or `instruction.md`; it exists only as an emergent property of the measured spring rates in
`taguchi_spring_robustness.csv`, so recovering it (and then re-checking fatigue, buckling, and
frequency margin at whichever noise direction is actually worst-case for each, since the three
do not all share one worst-case direction) requires treating an earlier stage's own raw data as
this stage's hidden input, not restating a number the task handed over. Second, the
frequency-optimized alternative must be checked against one of two given fatigue criteria
(the existing infinite-life endurance limit, or a stated finite-life Basquin relation against a
rated qualification-cycle count) -- and which one governs is a genuine engineering judgment
call with no single correct answer, not a value to compute. The task asks the agent to pick one
and justify it from the data provided (the rated cycle count, the performance-oriented intent
of this alternative design), and the grading accepts either self-consistent choice rather than
sealing one answer as correct.

The difficulty is intrinsic to the engineering content, not manufactured through obscure
wording: the parametric-optimization stage hands over no ready-made constraint set, and
neither `instruction.md` nor the data file writes out the closed-form equations for the
standard textbook relations it relies on (the Wahl factor, the spring-rate relation, the
peak-shear-stress relation, the linear/Goodman fatigue-damage criterion, Turner's
CTE-homogenization model, the rule-of-mixtures density relation, the spring-surge natural-
frequency relation, Suh's Information Axiom, and the Taguchi signal-to-noise and
quality-loss formulas) -- only the governing physical principle and the quantities it
depends on are named, so supplying the exact algebra is the agent's own contribution, not a
substitution exercise. (The two relations that are spelled out -- the composite's
task-specific thermal-residual-stress estimate and the free-length/buckling geometry -- are
not standard-named formulas any reference would supply verbatim, so leaving them implicit
would make the task ill-posed rather than harder.) Solving the stage correctly further
requires identifying which material and end-fixation row the concept-selection stage
already chose, deriving the composite wire's effective CTE, thermal residual stress, and
homogenized density from its matrix and reinforcement constituents, folding the residual
stress into the fatigue criterion and the density into a natural-frequency floor, deriving
all eleven resulting constraint functions from stated physics (five static/geometric, the
fatigue criterion, buckling, the frequency-margin floor, and process-robustness re-checks of
fatigue, buckling, and frequency margin), and actually solving and
comparing two wire-treatment options rather than picking one by inspection (the
cheaper-per-volume option is not the cheaper overall design here, and the size of its
advantage itself depends on the residual-stress derivation being done correctly) -- now
compounded by a second discrete choice, since the selected material's own strength
properties are not given directly either: they come from a tempering-response table keyed
to tempering temperature, and the tempering condition actually used must be solved and
compared jointly with the wire-treatment choice, not picked from the table by inspection (see
the tempering trap below). A
buckling requirement that is slack at the global optimum, and a
frequency-margin floor that is likewise slack there, each become the sole binding reason a
different large-coil-count candidate is infeasible, even though more coils otherwise reads
as a straightforward durability win -- so the final-candidate screening requires identifying
*which* of several distinct requirements actually limits each candidate, not just whether it
passes. The three rigorous multi-criteria methods in the final stage now weigh cost,
durability, and dynamic margin together with stated unequal weights, and TOPSIS and the
weighted-sum method genuinely disagree on the winning candidate on this data -- not merely
tie -- so a correct solution has to recognize that, understand why it happens, and make and
justify a choice rather than mechanically reporting one formula.
Full detail on every one of these is in `authoring/provenance/dataset_manifest.md`.

## Scientific grounding

Every stage applies a named, standard design-engineering or materials-science method to
one original, self-contained subsystem (the energy-storage element of a spring-loaded
latch) that was invented for this task: morphological analysis / cross-consistency
assessment for concept selection, Suh's Axiomatic Design (the Independence and Information
Axioms) for embodiment selection, first-principles constrained spring-design optimization
(the Wahl stress-concentration factor, the standard helical-spring rate relation, a linear
mean/alternating fatigue-damage criterion with temperature derating) combined with
particulate-composite micromechanics (Turner's effective-CTE homogenization model and a
constituent-CTE-mismatch thermal residual-stress estimate with a von Mises
shear-equivalence conversion), a lateral-buckling slenderness limit, and a fundamental-
natural-frequency (spring-surge) check built on a rule-of-mixtures composite density, for
the detailed geometry, Taguchi's parameter/robust design (an L9 orthogonal array,
nominal-the-best signal-to-noise ratio, quadratic quality loss) for manufacturing-tolerance
robustness, and Pareto dominance / TOPSIS / the weighted-sum method over three objectives
for the final design choice. These are named by method, the way a practicing engineer's own
brief would reference them, not spelled out as ready-to-use equations -- the task expects
the closed-form relations themselves (Wahl's factor, the spring-rate relation, Turner's
model, the fatigue interaction equation, the surge-frequency relation) to come from the
solver's own command of the discipline, the same command a design review would expect an
engineer to bring into the room rather than look up mid-meeting. All of the numeric content
-- the morphological chart's variants and scores, the three candidate FR-DP matrices and
their process data, the spring's material options (including each composite wire's matrix
and reinforcement constituent properties, including their densities), buckling limits,
wire-treatment options, force/deflection/fatigue requirements, and the actuation-rate/
frequency-margin requirement, the Taguchi array's factor levels and noise conditions, and
the twelve final-design candidates -- is original to this task: none of it is copied or
adapted from any external dataset, textbook problem, or published source; only the general
engineering and materials-science methods themselves (standard, public technique, like
linear regression, a free-body diagram, or a rule-of-mixtures estimate) are named.

## Why five stages, and why they must be synthesized

Each stage applies a distinct, individually well-understood method; the task's difficulty
is that solving the third stage correctly requires reasoning that spans two disciplines at
once (structural spring design and composite-materials micromechanics), that an error or a
skipped nuance in any one stage is independently detectable, that the concept-selection
stage's material and end-fixation choice must be carried correctly into two later stages,
and that the final synthesis must correctly reuse each stage's own (already-graded) result
rather than inventing a second, disconnected answer for the same question.
`tests/test_outputs.py::test_synthesis_consistent_with_stage_results` enforces the latter
directly.

## The parametric-optimization stage gives physics, not a ready-made problem

`spring_optimization_problem.json` does not hand the agent a pre-packaged list of
inequality constraints, nor a single set of material properties, nor the closed-form
equations themselves. It *names* the underlying physical relations (the Wahl
stress-concentration factor, the peak-shear-stress relation, the spring-rate relation,
temperature-derated fatigue-stress relations, Turner's composite-CTE homogenization model,
a rule-of-mixtures density relation, a fundamental-natural-frequency relation, and a
lateral-buckling slenderness relation) and the quantities each one depends on, without
writing out their algebra -- an agent that does not already know, or cannot correctly
derive, the Wahl factor or the spring-surge frequency relation cannot solve this stage by
substitution alone. (The one relation still given as an explicit equation, the composite's
thermal-residual-stress estimate, is a task-specific micromechanics estimate rather than a
single universally-named textbook formula, so it is stated outright rather than left for
the agent to guess among several plausible variants.) A table of material options -- each a
two-phase particulate metal-matrix composite wire system, keyed by the morphological
chart's `material` variant codes -- a table of buckling limits keyed by its `end_fixation`
variant codes, two wire-treatment options with different fatigue and cost effects, and a
tempering-response table (hardness, the three strength properties, and Charpy V-notch
toughness by tempering temperature, for the selected material's own matrix alloy) round out
the data. Two of the three material rows give their strength properties directly; the
selected row does not -- it must be read off whichever tempering-response row clears a
stated Charpy toughness floor and, jointly with a wire-treatment choice, minimizes cost.
None of the composite-materials, dynamics, or heat-treatment relations is walked through in
`instruction.md` either -- they live only in the data file, exactly like the base spring
equations, and there only by name. Turning "the spring must not exceed the allowable
stress" or "the fatigue, buckling, and frequency-margin criteria must hold" into explicit
constraint functions -- using the material and end-fixation rows the concept-selection
stage actually selected, supplying and applying the correct closed-form relation for each
named principle, deriving that material's effective CTE, thermal residual stress, and
homogenized density from its own constituent phases, recognizing that the residual stress
belongs in the fatigue criterion's mean-stress term while the density belongs in the
frequency relation, and solving for the cheaper of two wire-treatment branches, now crossed
with every toughness-passing tempering condition, rather than assuming either -- is itself
part of solving this stage, not a step the instructions do for the agent. Recovering the
process-robustness noise magnitude from
`taguchi_spring_robustness.csv` (inverting the spring-rate relation against its per-run,
per-condition measurements) and deciding, with justification, which fatigue-life criterion
governs the frequency-optimized alternative are likewise the agent's own work -- neither is
handed over as a number or a rule in either `instruction.md` or the data files.

## Design decisions worth flagging

Full technical detail is in `authoring/provenance/dataset_manifest.md`; in brief:

- **The Independence Axiom gate.** One of three candidate embodiments (Y) is fully
  coupled -- it fails Suh's Independence Axiom outright -- but is deliberately given the
  tightest process-capability data of the three, so it would look like the best design by
  raw information content alone. A correct analysis rejects it on the coupling
  classification before information content is ever compared.
- **The robustness-vs-on-target distinction.** The Taguchi stage's factor-level
  combination that maximizes signal-to-noise (most robust to named manufacturing-tolerance
  noise) is deliberately not the same combination that minimizes quality loss against a
  stated target spring rate -- a genuine, physically grounded divergence, not an assumption
  the agent can shortcut.
- **The composite residual-stress trap.** The selected wire's matrix and reinforcement
  phases contract by different amounts on cooling from the composite's processing
  temperature, locking in a thermal residual stress that adds directly to the fatigue
  criterion's mean-stress term regardless of wire treatment or operating temperature. This
  is large enough to change which constraint binds at the global optimum (from static
  stress to fatigue) and to reshape both wire-treatment branches' costs -- a report that
  solves the mechanical spring-sizing problem correctly but treats the composite data as
  reference-only background will converge on a design that is measurably wrong, not just
  imprecise.
- **The tempering trap.** The selected material's wire is temper-hardened after
  consolidation, and its strength properties come from a tempering-response table, by
  tempering temperature, rather than being given directly. The lowest-temper row has the
  greatest strength (and so would size the cheapest spring) but the least Charpy toughness;
  a second row sits inside this alloy's classical tempered-martensite-embrittlement band
  (roughly 260-370 C for many low-alloy steels), where toughness dips even though temper
  temperature -- and so strength -- is not at its lowest. Both fail a stated minimum-Charpy-
  toughness requirement, and neither is labeled unsafe in the data; a report that reads
  "highest strength" or "higher temper is always tougher" off the table without checking
  every row's own toughness value against the floor picks a design that is measurably wrong.
  Every row that does clear the floor, plus both wire-treatment options, must actually be
  solved and compared -- the correct row is the cheapest of the toughness-passing ones, not
  the strongest one outright.
- **The wire-treatment trade-off.** Shot peening raises the fatigue endurance limit at a
  20% relative material-cost premium; on this dataset the peened design is still cheaper
  overall, because the fatigue margin it buys (including headroom against the residual-
  stress penalty above) allows a meaningfully smaller spring -- a result that is not
  obvious without solving both branches and comparing, and that flips at higher active-coil
  counts, where the unpeened branch becomes cheaper instead because the peened branch's
  thinner wire runs into the buckling limit first.
- **The fatigue trap.** Some of the final-design candidates satisfy every static/geometric
  requirement comfortably -- they would pass a check that stops there -- but fail the
  fatigue damage criterion once both the cyclic service load and the composite's own
  thermal residual stress are correctly included.
- **The buckling trap.** A separate candidate satisfies every static, force, fatigue, and
  frequency requirement with a comfortable margin and has the highest active-coil count of
  any candidate (the best-looking design by the durability proxy alone) -- but its large
  active coil count drives up the free length enough to violate the lateral-buckling
  slenderness limit. More coils is good for durability and fatigue margin, but past a point
  becomes laterally unstable; a screen that checks only stress and fatigue will wrongly
  accept it.
- **The surge trap, and its mirror image.** What used to be the largest-Na point on the
  two-objective Pareto frontier now fails the frequency-margin floor alone: its large mean
  diameter and coil count push its fundamental natural frequency below the required surge
  margin, even though every static, fatigue, and buckling requirement still passes
  comfortably. A different, slightly smaller candidate sits just inside that same boundary
  -- feasible on every requirement, but with the smallest dynamic margin of any feasible
  design -- showing the frequency floor is a real, precisely-located limit, not a coarse
  cutoff a screen could round away. Because raising Na and D helps durability but hurts
  dynamic margin while a larger d helps dynamic margin but raises cost, the three objectives
  genuinely pull the design in different directions, not just up or down a single dial.
- **The near-miss and the dominated point.** One candidate fails the force-delivery
  requirement by a small, easy-to-miss margin (it delivers just over the allowed upper
  bound); a different candidate is fully feasible on every requirement but is strictly
  dominated by another feasible candidate on all three objectives at once -- cheaper, more
  durable, *and* dynamically safer -- so a report that skips genuine Pareto-dominance
  filtering and returns every feasible candidate gets the final-selection stage wrong even
  when its feasibility screening was correct.
- **TOPSIS and the weighted-sum method disagree.** On the four genuinely Pareto-optimal
  candidates (screened against cost, durability, and dynamic margin together), TOPSIS
  (vector/Euclidean-norm normalized, the standard convention for that method) picks a clear
  winner by geometric distance to the ideal and anti-ideal points; the weighted-sum method
  (min-max normalized, the standard convention for that method, with the stated unequal
  weights -- 0.45 cost, 0.35 durability, 0.20 dynamic margin) picks a *different* candidate,
  because its per-criterion normalization lets a design that is merely extreme on the two
  most heavily weighted objectives outscore a more balanced design across all three, where
  TOPSIS's geometric-distance ranking weighs a design's standing on every normalized
  objective jointly. The two methods are not required to agree, and here they do not -- the
  report must say so and resolve it rather than silently picking whichever number happened
  to compute first.
- **The frequency-optimized alternative.** Separately from the minimum-cost design, the
  parametric-optimization stage asks for the maximum-natural-frequency design achievable
  under the same wire treatment and a 15%-of-cost budget increase. On this data the two
  designs are genuinely different geometries (a much larger mean diameter and a much smaller
  active-coil count trade against a thicker wire) -- and the cost cap is not even the
  binding limit on how much dynamic margin is purchasable; the housing-bore and
  force-delivery-cap requirements are. A report that assumes maximizing dynamic margin is
  the same problem as minimizing cost, just solved differently, will not notice either
  fact.
- **The process-robustness re-check reuses hidden data across stages.** A feasible
  parametric-optimization design must also survive the wire-diameter/active-coil
  manufacturing noise the Taguchi stage's own `taguchi_spring_robustness.csv` characterizes
  -- but that noise's magnitude (`~0.015` mm on wire diameter, `~0.2` coils on active-coil
  count) is never written down anywhere in `instruction.md` or
  `spring_optimization_problem.json`; it only exists as an emergent property of the raw,
  per-run, per-noise-condition spring-rate measurements, recoverable by inverting the
  standard spring-rate relation against them (the reference solution does this with a
  nonlinear least-squares fit, not a lookup). The three requirements it re-checks --
  fatigue, buckling, and the frequency-margin floor -- do not all fail in the same noise
  direction (thinner wire is worse for fatigue, but thicker wire plus more coils is worse
  for buckling and for frequency margin), so a correct re-check cannot apply one worst-case
  perturbation to all three at once. A design that is comfortably feasible at its own
  nominal dimensions can still fail this re-check; several final-design candidates are
  constructed to do exactly that (see Q2, Q3, Q9, and Q10 in `dataset_manifest.md`).
- **The fatigue-life-philosophy judgment call.** The frequency-optimized alternative is
  checked against whichever of two given fatigue criteria the agent chooses: the same
  infinite-life endurance-limit criterion the minimum-cost design always uses, or a stated
  Basquin finite-life relation qualified against a given rated-cycle count. Nothing in the
  data dictates which one governs -- it is a genuine engineering judgment call, not a
  computation, and the task asks for it to be made and justified rather than looked up. On
  this dataset the two choices lead to two different, well-separated designs (the finite-life
  criterion is less conservative, buying both a lower cost and a higher frequency than the
  infinite-life choice), and the grading is self-consistent: it reads back whichever
  philosophy the report says it used and checks the corresponding sealed target, so either
  well-justified choice can be fully correct -- confirmed directly by constructing a second,
  swapped report that claims the other philosophy and verifying it also passes all 36 checks.

## Verification

The verifier reads only `/app/output/design_report.json` and `findings.md` against a
sealed reference (`tests/ground_truth.json`) with 36 checks. Every tolerance was chosen
deliberately, not left at a library default:

- Integer/exact fields (morphological totals, coupling classification, run IDs, factor
  levels) are checked exactly -- there is no ambiguity to tolerate.
- Information content is checked to within 0.01 bits, an order of magnitude tighter than
  the 0.14-bit gap between the two Independence-compliant candidates, so the tolerance
  cannot itself decide the winner.
- The parametric optimum's cost is checked within a 2% relative tolerance -- wide enough
  to absorb multistart-seed-level solver noise (independent re-solves agree to roughly
  1e-4% in practice) but far too tight to accept a design built on the wrong material row,
  end-fixation row, wire treatment, tempering condition, or an omitted/approximated
  composite residual-stress term, any of which shifts the cost by several percent or more.
  Its wire treatment and tempering condition are each checked exactly, and a dedicated check
  independently looks up whichever tempering condition the report names in a hardcoded copy
  of the tempering-response table and confirms it actually clears the stated minimum Charpy
  toughness -- catching a report that names a plausible-looking but wrong (trap) condition
  even if its cost happens to land close to the sealed value. The composite wire's
  Turner-model effective CTE is checked within an
  absolute tolerance of 1e-7 per degree C (about 1% relative), its homogenized density
  within 0.1 kg/m^3, and its fundamental natural frequency within a 2% relative tolerance --
  each cross-checked against an independent from-constituent-data recomputation. All eleven
  constraint functions (five static/geometric, fatigue, buckling, the frequency floor, and
  the three process-robustness re-checks) are also independently recomputed from the agent's
  own reported `(d, D, Na, treatment)` with a slack tolerance of 0.02 -- far looser than the
  sealed optimum's own tightest active margins (the oversupply cap and the fatigue
  process-robustness re-check are essentially exactly binding there, at ~1e-8 and ~1e-10
  respectively, a property of the true continuous optimum itself, not a reporting
  requirement) and sized to absorb ordinary reporting-precision rounding rather than demand
  the optimum's own knife-edge numerical precision -- rounding the reported design to four
  decimal places of a millimetre, for instance, shifts the tightest margins by no more than
  about 0.009, comfortably inside this tolerance, while a materially wrong design (the wrong
  wire treatment, or even a half-percent error in wire diameter) still produces a violation
  an order of magnitude or more above it. The frequency-optimized
  alternative's own natural frequency, cost, and feasibility against every non-frequency
  requirement (under whichever fatigue-life philosophy the report itself claims) are checked
  the same way, plus a check that it does not exceed the stated 1.15x cost cap and that it is
  flagged as genuinely different from the cost optimum. Because the philosophy choice is a
  genuine judgment call, the check reads the agent's own
  `frequency_alternative_fatigue_philosophy` field and grades against the matching one of two
  sealed targets, rather than fixing a single correct answer.
- Taguchi signal-to-noise ratios are checked within 0.05 dB and factor-level averages
  within 0.10 dB, both well under the smallest genuine factor-level effect in this dataset
  (about 0.6 dB for factor B), so rounding cannot be mistaken for a real effect.
- Final-candidate feasibility (now against all eleven requirements, process-robustness
  included), the Pareto-optimal set (now over three objectives), and both multi-criteria
  winners are checked individually, with a dedicated check that the explanation acknowledges
  it when TOPSIS and the weighted-sum method disagree, and that the synthesis section's
  final-design field is constrained to be whichever of the two winners the report itself
  settled on.

## Anti-hardcoding checks

Every data file here is small and human-readable, so a report could in principle reproduce
the sealed numeric targets without genuinely re-deriving them. `tests/test_outputs.py`
guards against this with eight recomputation checks (`test_morphological_matches_raw_chart`,
`test_axiomatic_matches_raw_candidates`, `test_taguchi_matches_raw_csv`,
`test_pareto_matches_raw_csv`, `test_parametric_optimum_composite_cte_matches_recomputation`,
`test_parametric_optimum_composite_density_matches_recomputation`,
`test_parametric_optimum_natural_frequency_matches_recomputation`,
`test_parametric_optimum_temper_clears_toughness_floor`) that independently
rebuild each stage's key result -- four from the raw data copies in `tests/`, four from
constituent material properties, tempering-response data, and requirement constants
hardcoded independently of both the agent's report and `environment/data` -- using only the
Python standard library (a
`math.erf`-based normal CDF stands in for `scipy.stats.norm`, since the separate-mode
verifier installs no scientific-computing packages). A report cannot pass by reproducing
the sealed numbers without a computation that also matches an independent from-data
re-derivation.

## A bug caught during authoring

An earlier draft of `tests/ground_truth.json` had `taguchi_best_on_target_run_true` set to
`8` -- the *most-robust* run -- while its paired field,
`taguchi_best_on_target_levels_true`, correctly held `{"A": 3, "B": 1, "C": 3}`, the factor
pattern for run `7`, not run `8`. Caught by cross-checking the two fields against each
other and against a fresh recomputation from `taguchi_spring_robustness.csv` before
`solution/solve.py` was ever written against the file; fixed to `7`.

## Test suite

36 checks in `tests/test_outputs.py`: file existence, required-field presence (including the
composite-density, natural-frequency, tempering-temperature, frequency-optimized-
alternative, and frequency-alternative-fatigue-philosophy fields), and a findings.md
coverage check (the five stages must all be mentioned by name); the synthesis explanation's
required content and length (requiring surge/frequency-margin language, naming of the
fatigue-life-philosophy judgment call, tempering-condition language, and coverage of all
three final-selection objectives); per-stage checks against sealed ground truth for all five
stages (morphological totals and best combination; axiomatic coupling classification, the
coupled-design exclusion gate, information content, and the recommended design; the
parametric optimum's cost, wire treatment, tempering condition (both checked exactly, the
tempering condition also independently confirmed to clear the stated Charpy toughness floor
in a hardcoded copy of the tempering-response table), composite effective CTE, composite
density, and natural frequency plus an independent recheck of every requirement -- five
static/geometric, fatigue including the thermal residual-stress term, buckling, the
frequency-margin floor, and its three process-robustness re-checks -- from the agent's own
reported design; the frequency-optimized alternative's own cost, natural frequency,
feasibility, cost cap, and whether it differs from the cost optimum, graded self-consistently
against whichever fatigue-life philosophy the report claims to have used; Taguchi
signal-to-noise ratios, factor-level averages, the most-robust combination, the
best-on-target run, and the robust-vs-on-target-are-different check; final-candidate
feasibility under all eleven requirements (process-robustness included), the three-objective
Pareto-optimal set, the TOPSIS/weighted-sum winners, and a dedicated check that a
disagreement between them is acknowledged in the explanation); the eight recomputation
checks described above; and a cross-field consistency check on the synthesis
section.

`python3 authoring/provenance/generate_ground_truth.py` regenerates every dataset file
that isn't already consistent with `tests/ground_truth.json` (idempotently), runs
`solution/solve.py`, and grades the result with the exact checks in
`tests/test_outputs.py`, in-process. A clean run ends `36/36 checks passed`.
