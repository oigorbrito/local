import unittest
from model_profiles import PROFILES, select_profile

class ModelProfileTests(unittest.TestCase):
    def test_versioned_profile_coexists_with_historical_profiles(self):
        self.assertEqual(set(PROFILES), {'principal', 'alternativo', 'economico', 'principal-localizado'})
    def test_models(self):
        self.assertEqual(select_profile('principal').base_model, 'nemotron-3-nano:4b')
        self.assertEqual(select_profile('alternativo').base_model, 'qwen3.5:4b')
        self.assertEqual(select_profile('economico').base_model, 'qwen3.5:2b')
    def test_v1_policy_fingerprints_guard_against_silent_drift(self):
        expected = {
            "principal": "dfd3cf5ae7d667c7f819164a9a081c8de8db538d27fec43c155a8639dbe15886",
            "alternativo": "0f2e0603359b5647583807ae859c5efe8167e1328da4b5c84de2bd6762c84479",
            "economico": "450a1465a85cc54ba807c91dfa635f35b37c4b731aba1bfa49c64392b8f1e9b1"
        }
        for name, value in expected.items():
            self.assertEqual(PROFILES[name].version, "1.0.0")
            self.assertEqual(PROFILES[name].fingerprint, value)

    def test_v2_localized_schema_is_explicit_and_fingerprinted(self):
        legacy = select_profile('principal')
        current = select_profile('principal-localizado')
        self.assertEqual(legacy.manifest()['version'], '1.0.0')
        self.assertNotIn('output_schema', legacy.manifest())
        self.assertEqual(current.version, '2.0.0')
        self.assertEqual(current.output_schema, 2)
        self.assertEqual(current.manifest()['output_schema'], 2)
        self.assertIn('schema (integer 2)', current.system)
        self.assertNotIn('complete replacement source', current.system)
        self.assertNotEqual(current.fingerprint, legacy.fingerprint)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            select_profile('unknown')
