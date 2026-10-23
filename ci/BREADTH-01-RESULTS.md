# Breadth-first screen 01 — observed evidence

Run: https://github.com/oigorbrito/local/actions/runs/40017286253
Scope: six synthetic Python tasks, CPU on GitHub-hosted Ubuntu runner, Ollama, deterministic temperature 0. This is not a SWE-bench or hardware-target ranking.

| Model | Passed / 6 |
|---|---:|
| phi4-mini:3.8b | 5 |
| qwen2.5-coder:7b | 5 |
| nemotron-3-nano:4b | 5 |
| ministral-3:3b | 5 |
| deepseek-coder:6.7b | 4 |
| qwen3.5:2b | 0 (all six captured responses empty) |
| qwen3.5:4b | 0 (all six captured responses empty) |
| codegemma:2b | 0 (captured outputs not executable Python; one response was `ipynb`) |

The Qwen3.5 zero scores are output-capture/configuration failures until proven otherwise, not evidence of six incorrect solutions. CodeGemma also needs protocol compatibility assessment; no general model elimination warranted.

Previous screen baseline: deepseek-coder:1.3b 5/6; qwen2.5-coder:3b 5/6; qwen2.5-coder:1.5b 4/6; granite3.3:2b 3/6; qwen3:1.7b 1/6; gemma3:1b 1/6.

No winner should be selected from this tiny suite. Next step: compare model/runtime configurations in an existing real-code benchmark, use matched tasks and independent tests. Preserve raw outputs, distinguish not-generated from incorrect, and validate final candidates on user hardware.
