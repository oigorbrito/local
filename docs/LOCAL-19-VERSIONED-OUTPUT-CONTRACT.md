# LOCAL-19 — Versioned localized editing profile (Nemotron 4B)

## Purpose

The original LOCAL-16 `principal` profile v1.0.0 requires
`schema=1/file/content` in its frozen policy and request, while the
LOCAL-18 Ollama adapter requests `schema=2/file/old/new`.
This inconsistency is demonstrated by the source, but cannot be proven
to have caused the prior `EDIT_ANCHOR_NOT_UNIQUE` incident because
the original model reply was not persisted.

The new opt-in profile `principal-localizado` v2.0.0 makes the
localized response contract consistent across frozen profile policy,
request, Ollama prompt/schema, validation and replay. Its manifest
includes `output_schema: 2`, and its fingerprint differs from v1.
Historical `principal` v1.0.0 fingerprint, name and manifest remain
unchanged. The legacy transport behavior remains unchanged; do not
reinterpret old v1 evidence as a v2 run.

## Invariants

- Model: native `nemotron-3-nano:4b`, temperature 0, context 4096,
  `num_predict=2048`. No change to model weights.
- v2 must output only `{schema:2,file,old,new}`, where `old`
  appears *exactly once* in the version-pinned target file.
- Missing or duplicate anchors remain rejected, never auto-selected.
- `response.json` is preserved before patch replay for responses
  already returned by the Ollama adapter (via preceding LOCAL-18 fix).
  This does not yet preserve malformed or incomplete responses rejected
  within the transport adapter itself.
- Source trees are not modified by `generate` or `check`.
  Any functional execution of a model patch requires separately
  qualified isolation. No auto-retry, auto-apply or auto-merge.
- The frozen LOCAL-17 session `local17-session-20e1b6ed` is a consumed
  attempt. **Do not rerun it under the new profile and count it as new
  independent evidence.** Prepare a new, preregistered issue, with its
  own pinned Git commit and hidden independent evaluator.

## Example: a fresh, preregistered task

After selecting an unused clean disposable checkout and separate
evidence directory *outside* the checkout:

```powershell
python experiments/local07/local16_workflow.py new --repo <clean-checkout> --session <new-evidence-dir> --profile principal-localizado --task-file <frozen-task-file>
python experiments/local07/local16_workflow.py status --session <new-evidence-dir>
```

These preparation commands do not invoke Ollama. The separately
authorized one-shot command below **does invoke** the local model:

```powershell
python experiments/local07/local16_workflow.py generate --session <new-evidence-dir> --timeout 300
python experiments/local07/local16_workflow.py check --session <new-evidence-dir>
```

Record model digest, prompt hash, response hash, patch hash, output
tokens and task-level elapsed time before comparing with another
executor. No performance, quality or cost claim is established merely
by the offline protocol tests.

## Validation gates

`test_model_profiles`, `test_executor_bridge`, and
`test_local16_workflow` exercise policy identity, v2 request/replay,
and bounded offline generation. GitHub CI must validate on both
Ubuntu and Windows. A CI PASS validates the contract; it does not
establish success on real issues.
