# Harbor pipeline review (run of 18 Sep)

Pasted by the author. The last trial summary (task__Xq85ZrC) was cut off in the paste.

## Stage results

| Stage | Check | Time | Result |
|---|---|---|---|
| Files | Structural checks: required files, task.toml policy, verifier isolation, blocked terms | 15:46 | PASSED |
| Files | AI check: instruction must be human-written | 15:46 | PASSED |
| Files | Similarity: must not duplicate an existing task | 15:46 | PASSED |
| Files | Reference verification: oracle = 1 every attempt, nop = 0 | 15:46 | PASSED |
| Files | Quality review: agentic rubric over the full bundle | 15:50 | PASSED |
| Pipeline | Anti-cheat probe: one adversarial trial | 16:05 | PASSED |
| Pipeline | Easiness probe: lighter screening pass | 16:30 | PASSED |
| Pipeline | Difficulty probe: frontier attempts, solved rarely but not never | 16:50 | PASSED |
| Pipeline | **Run audit**: judge review of probe trajectories | 17:35 | **FAILED** |

Run audit model: claude-fable-5-1.
Failure modes: specification completeness (7/8 trials); verifier correctness (8/8); meaningful difficulty (8/8).

| Criterion | Result |
|---|---|
| unearned credit | PASS, 0/8 trials |
| specification completeness | FAIL, 7/8 trials |
| solution discoverability | PASS, 0/8 trials |
| verifier correctness | FAIL, 8/8 trials |
| policy refusal | PASS, 0/8 trials |
| meaningful difficulty | FAIL, 8/8 trials |
| boundary fairness | FAIL (advisory), 8/8 trials |
| execution blocked | PASS, 0/8 trials |

## Trial summaries (as pasted)

- **task__7gjCkmU**: about 12 min of a 9000 s budget. The agent recovered the +/-0.015 mm and +/-0.2 coil noise by inverting the spring-rate relation against the Taguchi CSV. Every value matched ground_truth.json to 6-7 significant figures (cost 675.5931, fn 586.2752, Pareto set and both MCDM winners correct). 35/36 tests passed. The only failure was `test_explanation_content`, which requires the literal substring "durab". The agent wrote "max Na" instead of "durability", so reward was 0.
- **task__AxTyVmQ**: about 17 min of a 150 min budget. 33 numeric and categorical checks passed, agreeing with ground truth to about 1e-9 relative. Reward was 0 because `test_explanation_content` requires the literal "fatigue-life" or "fatigue life". The agent wrote "infinite-life criterion", "Basquin" and "endurance limit". Inserting that phrase makes the verifier pass 36/36. The auditor called this a brittle keyword gate fitted to the reference's own template sentence.
- **task__JdCDEER**: about 13 min. Matched ground truth on every quantitative and categorical check (cost 675.5931, f_n 586.275 Hz, peened/370 C, feasible Q4-Q8, Pareto Q4-Q7, TOPSIS Q7 vs WSM Q6, Taguchi A3/B2/C1 vs run 7). 35/36 passed. The only failure was `test_explanation_content`, which requires "durab" and "fatigue-life"/"fatigue life". Reward 0.
- **task__PeXVb3r**: about 13 min. Everything matched (cost 675.5931, infinite-life alternative 618.12 Hz). 35/36 passed. The only failure was `test_explanation_content`, which requires "durab". The 2,900-character explanation used "coil-count spread" and "integer 11 active coils". instruction.md's topic list never mentions durability or the three objectives, so the keyword is undisclosed.
- **task__Xq85ZrC**: about 14 min. Every numeric field matched ground truth essentially exactly. Truncated in the paste.

## Takeaway

The pipeline flagged 8/8 trials. Every trial was scientifically correct, and every one failed only the single all-or-nothing `test_explanation_content` keyword gate. The task therefore measures whether the explanation contains the reference's wording, not the science.
