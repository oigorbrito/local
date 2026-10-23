import copy
import json
import tempfile
import unittest
from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("harness", ROOT / "scripts" / "harness.py")
h = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = h
spec.loader.exec_module(h)

class HarnessTests(unittest.TestCase):
    def base_state(self):
        return json.loads((ROOT / "policy" / "project-state.json").read_text(encoding="utf-8"))

    def test_bootstrap_does_not_treat_product_stage_as_maturity(self):
        s = self.base_state()
        s["product_stage"] = "MVP"
        s["osps_target_level"] = 1
        fs = h.findings(s, ROOT)
        self.assertTrue(any(x.control == "PRODUCT-STAGE" and x.status == h.INFO for x in fs))

    def test_release_activates_release_conditioned_checks(self):
        s = self.base_state()
        s["release"]["made"] = True
        fs = h.findings(s, ROOT)
        self.assertTrue(any(x.control == "OSPS-DO-01.01" and x.status == h.GAP for x in fs))

    def test_level_two_reassessment_is_signal_not_auto_promotion(self):
        s = self.base_state()
        s["maintainers_count"] = 2
        s["consistent_users"] = "small"
        s["osps_target_level"] = 1
        fs = h.findings(s, ROOT)
        self.assertTrue(any(x.control == "OSPS-MATURITY" and x.status == h.REASSESS for x in fs))
        self.assertEqual(s["osps_target_level"], 1)

    def test_external_controls_remain_unknown(self):
        s = self.base_state()
        fs = h.findings(s, ROOT)
        self.assertTrue(any(x.control == "OSPS-AC-03.01" and x.status == h.UNKNOWN for x in fs))

if __name__ == "__main__":
    unittest.main()
