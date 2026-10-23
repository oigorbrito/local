# LOCAL — frozen restart protocol 01 (2026-10-23)

## Decision and scope

**Primary candidate executor: Little-Coder (Pi-based); control: upstream Aider.** These are research assignments, not an announced winner. SmallCode is a conditional second executor (project recommends 8B–35B). Agentless is evaluated separately for issue-repair workflows. No manual executor imitation and no new 6-task screen.

The Little-Coder README reports a matched-model Aider Polyglot evaluation, Qwen3.5 9B, 225 exercises, 45.56% versus vanilla Aider 19.11%. This is external project-reported evidence, not an independent measurement in this repository, and does **not** establish performance for 2–4B or the user's hardware.

Sources:
- https://github.com/itayinbarr/little-coder
- https://github.com/Doorman11991/smallcode
- https://github.com/Aider-AI/aider/blob/main/benchmark/README.md
- https://github.com/OpenAutoCoder/Agentless

## Existing evidence: NEVER rerun merely to produce another record

| Dataset/run | Models or scope | Result | Reuse classification |
|---|---|---|---|
| Previous six-task synthetic Python screen | DeepSeek 1.3B, Qwen2.5-Coder 3B/1.5B, Granite 2B, Qwen3 1.7B, Gemma3 1B | 5/6, 5/6, 4/6, 3/6, 1/6, 1/6 | Exploratory capability, NOT elimination |
| 40017286253 | Nemotron 4B, Phi4-mini 3.8B, Ministral 3B, Qwen2.5-Coder 7B, DeepSeek 6.7B | 5/6,5/6,5/6,5/6,4/6 | Exploratory; raw artifacts retained |
| 40017286253 | Qwen3.5 2B/4B, CodeGemma 2B | 0/6 each | Invalid/incompatible generation format needs separate diagnosis; not eliminated |
| 40014441296 | Qwen2.5-Coder 3B, three SWE-bench Lite dev issues | 0/3 official resolved; 3 patches applied | Negative small-sample result, NOT elimination |
| 40015184698 | Same 3 official issue reports | 3 target failures, 18 PASS_TO_PASS failures | Regression evidence, don't count as 18 issues |
| 40021666982 and 40022164842 | Aider four candidate jobs | No valid exercise execution (Git safe.directory; AIDER_DOCKER) | INVALID_INFRA |
| 40023146720 | Aider four candidate jobs | Wrong exercises directory duplicated | INVALID_INFRA |
| 40024766616 | Aider four candidate jobs, latest corrected path | Check final status/artifacts before scheduling anything | PENDING / classify after review |

All numbers above apply only to their original conditions. They must NOT be added to a pooled cross-harness leaderboard.

## Predeclared elimination and interpretation rules

**Gate I / validity: mandatory.** Model/version/quantization/runtime hashes, executor commit, exercise IDs, input and hidden-test protection, exit status, timing, test execution and raw artifacts. If benchmark did not actually run, state INVALID_INFRA (not model failure). Empty responses are INCOMPATIBLE_OR_UNDIAGNOSED, not a competence score.

**Gate II / target hardware: mandatory.** User target Windows 11, 16 GiB RAM, 4 GiB VRAM. Eliminate a **model+quantization+runtime configuration** only if measured peak total memory or reliable execution cannot meet the target after one documented compatibility adjustment. CPU fallback allowed if user's latency requirement is satisfied. A 7B model is not excluded by parameter count alone.

**Gate III / functional efficacy: mandatory, matched.** Start with same untouched, executable, independent tasks and same inference/interaction budget. For paired executor comparison, hold model, runtime, quantization, prompt/task selection and test environment fixed as far as technically possible. Report paired per-issue outcomes (resolved, unresolved, invalid, regression), not only aggregate counts. Source-author-reported scores are hypotheses only.

**Gate IV / elimination by inferior quality:** Do not eliminate based on n=3 or n=6, or a point estimate. For a frozen, held-out task set use paired bootstrap 95% confidence interval on resolution-rate difference. Predeclared *practical* margin: 10 percentage points. Eliminate only if the entire confidence interval establishes the candidate at least 10 points behind a feasible comparator. This is an operational margin, not a scientific universal. If statistical evidence insufficient: INCONCLUSIVE.

**Gate V / Pareto cost:** Compare quality, wall time, peak RAM, peak VRAM, and intervention count under same hardware. Never rank CPU-hosted runner timing as if measured on Windows GPU. A configuration dominated on validated quality **and** resource constraints is removable for this hardware target; retain full raw data.

## Work plan: one experimental block

1. Archive reference IDs and verify pending run 40024766616; **do not rerun completed jobs**.
2. Freeze a reproducible task manifest, including at least two project languages if supported; pilot ONE model against both unmodified Little-Coder and unmodified Aider, instrument whether exercises/tests actually ran. A pilot checks validity only; **not** a ranking.
3. If valid, run the remaining model/runner matrix as one batch. Initial shared candidates from existing 5/6: Nemotron Nano 4B, Phi4-mini 3.8B, Ministral 3B, Qwen2.5-Coder 7B; include Qwen3.5 2B/4B only after identifying previously empty output capture. Include 1.5B/3B baselines from historical evidence. All candidates that fail packaging/capacity are reported separately.
4. Expand paired, independently graded tasks for leading viable model+executor configurations; measure uncertainty. Confirm finalists on Windows 16 GiB/4 GiB. No silent cloud fallback or paid API keys; fail closed.
5. One evidence report and one draft PR; manual merge only. Absolutely no FineCore/FineCode modification.

## Current conclusion

No model is eliminated on coding ability; no winner is selected. Little-Coder is the principal *executor hypothesis* because published matched-model evidence is stronger than SmallCode's non-matched benchmark claims, **not** because it is proven fastest on 4 GB VRAM.
