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
