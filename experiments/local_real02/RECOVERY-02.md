# LOCAL-REAL-02 / RECOVERY-02

One-shot, bounded repair stage for the earlier Windows real-code campaign. This is not a new fair three-way benchmark or proof of model superiority.

Input: original evidence at C:\Users\igorb\local-real-code-20261026-111812, completion evidence at C:\Users\igorb\local-real-code-20261026-111812-phi-completion, and the original benchmark.py and test_real_case.py from D:\projetos\real-model-pilot-v2.

The script checks source, prompt, oracle, model weights and original-report hashes. It permits one repair each for Qwen3.5 4B and Phi-4 Mini because both have recoverable prior code. Qwen2.5-Coder 7B had only a generation timeout and is recorded as NO_CANDIDATE_AFTER_TIMEOUT; no new first-stage attempt is silently introduced.

Generated code is never run on the Windows host. It is evaluated within a Docker container using no network, a read-only root filesystem, non-root account, dropped capabilities, resource limits and a single temporary read-only input mount. Docker preflight must pass the original failing and reference passing cases before any inference. Sandboxing mitigates risk, but is not a security guarantee. The Ollama server should not be shared during the run.

Run: python -B D:\projetos\local-recovery02\recovery02.py --base D:\projetos\real-model-pilot-v2 --evidence C:\Users\igorb\local-real-code-20261026-111812 --completion C:\Users\igorb\local-real-code-20261026-111812-phi-completion --seconds 240

Prerequisites: Docker Desktop, Ollama, Python, trusted local Docker image python:3.12-slim (pull explicitly if not present), and the two untouched historical evidence folders.

Output: new directory ending -recovery02, with report.json and one prompt/answer per eligible model. Previous evidence remains unchanged. Interrupted campaigns remain IN_PROGRESS; the script does not retry or overwrite their directory.

Validation: nine offline tests passed in the authoring environment using mocks, including a full simulated orchestration. No new model calls, Docker boot, or Windows execution has been performed by the author. A separate local RECOVERY-01 report was not ingested.

Governance: draft PR, no automatic merge.
