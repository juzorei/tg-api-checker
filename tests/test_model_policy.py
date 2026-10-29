import unittest
from services.model_policy import select_models


class ModelPolicyTests(unittest.TestCase):
    def test_minimum_versions_and_aliases(self):
        old = ['anthropic/claude-opus-4-6-thinking', 'claude-3-5-sonnet-20241022', 'sonnet-4.5', 'gpt-4o', 'openai/gpt-5.6-sol', 'google/gemini-3.1-pro', 'glm-5.2', 'glm-5.30', 'glm-6']
        current = ['opus-5.5', 'claude-5-sonnet', 'openai/gpt-6-astra', 'gpt-6.1', 'gemini-4-argon', 'z-ai/glm-5.3-flash', 'GLM-5_3', 'glm-5.3.1']
        allowed, skipped = select_models(old + current)
        self.assertEqual(allowed, current)
        self.assertEqual(set(skipped), set(old))
        self.assertTrue(all(skipped.values()))

    def test_latest_available_numeric_version_not_lexical(self):
        catalog = ['minimax/minimax-m2.9', 'minimax-m3.1', 'MiniMax-M3.1-Flash', 'kimi-k2.5', 'moonshotai/kimi-k3.1-pro', 'kimi-k3.1-highspeed', 'kimi-k3.0']
        allowed, skipped = select_models(catalog)
        self.assertEqual(allowed, ['minimax-m3.1', 'MiniMax-M3.1-Flash', 'moonshotai/kimi-k3.1-pro', 'kimi-k3.1-highspeed'])
        self.assertEqual(len(skipped), 3)
        allowed, _ = select_models(['kimi-k3.9', 'kimi-k3.10'])
        self.assertEqual(allowed, ['kimi-k3.10'])

    def test_unknown_names_and_other_families_retained(self):
        catalog = ['custom-model', 'gpt-oss-120b', 'minimax-latest', 'kimi-latest', 'claude-latest', 'llama-3.1', 'qwen-2.5', 'deepseek-v3', 'provider/embedding-3', 'my-gpt-4-adapter']
        self.assertEqual(select_models(catalog), (catalog, {}))

    def test_latest_is_relative_to_catalog(self):
        self.assertEqual(select_models(['minimax-m2.5']), (['minimax-m2.5'], {}))

    def test_duplicates_dates_and_exact_model_ids(self):
        allowed, skipped = select_models(['claude-3-5-sonnet-20241022', 'kimi-k3-20261001', 'kimi-k3', 'kimi-k3'])
        self.assertEqual(allowed, ['kimi-k3-20261001', 'kimi-k3'])
        self.assertEqual(list(skipped), ['claude-3-5-sonnet-20241022'])
