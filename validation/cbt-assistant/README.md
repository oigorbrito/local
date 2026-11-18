# Validation tests: CBT Assistant safety gaps

File: `test_safety_gaps.py` (copy it into the CBT Assistant's `tests/` folder).

These tests describe required behaviour and are expected to FAIL against the
current code. They use a stubbed LLM and need no Ollama or network.

- `test_crisis_message_gets_emergency_resources` (pt, en): a message with suicidal
  intent must return an emergency contact (CVV 188 / SAMU 192). Current result:
  only the model's reply is returned.
- `test_summarizer_failure_is_not_silent`: a failed model call during summary must
  raise, not return the old (empty) summary as if it had succeeded. Current result:
  the error is logged and the old summary is returned.

Run (from the CBT project root):

    python -m pytest tests/test_safety_gaps.py -v

## Summarizer fix (applied as a patch)

`summarizer-fix.patch` changes `src/memory/summarizer.py` in the CBT Assistant:

- `_generate_summary` no longer returns the old summary when the model call fails;
  the exception propagates.
- `_process_summarization_locked` logs a warning and saves nothing, so the messages
  stay pending and the next trigger retries them.

`test_summarizer_retry.py` covers the retry path: a failed attempt saves nothing,
and the next attempt saves the summary and marks the messages done.

Apply from the CBT project root:

    patch -p1 < summarizer-fix.patch

Results offline, patched copy: 59 passed, 2 failed (the crisis tests, not covered by
this fix), 1 skipped (live Ollama test, Ollama not running). The live test was not
rerun with Ollama after the change.

Known trade-off: a failed update is retried on every chat turn while the threshold is
exceeded. On slow hardware that repeats the expensive call; a cooldown is not added yet.

## Live test with Ollama (patched copy)

`test_real_memory_summarization` (Ollama `qwen3.5:9b` on a 4-vCPU CPU host, no GPU,
network disabled, original 120 s client timeout):

- Three sequential runs, one Ollama server: **3 / 3 passed**, 55–89 s each.
  Raw output: `live-series-log.txt`.
- Each run makes two summarization steps (summary, then recursive update); the
  individual model calls took about 20–46 s.

Earlier failures of this test (120 s timeouts, one 500) were measured before the
patch with the original code. Several leftover Ollama servers were also running
at the same time, which exhausted memory. Those results are not used here.

Still open: the cooldown for repeated retries on slow hardware (see above).
