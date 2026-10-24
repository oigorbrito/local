import unittest
from model_profiles import PROFILES, select_profile

class ModelProfileTests(unittest.TestCase):
    def test_three_profiles(self):
        self.assertEqual(set(PROFILES), {'principal', 'alternativo', 'economico'})
    def test_models(self):
        self.assertEqual(select_profile('principal').base_model, 'nemotron-3-nano:4b')
        self.assertEqual(select_profile('alternativo').base_model, 'qwen3.5:4b')
        self.assertEqual(select_profile('economico').base_model, 'qwen3.5:2b')
    def test_invalid(self):
        with self.assertRaises(ValueError):
            select_profile('unknown')
