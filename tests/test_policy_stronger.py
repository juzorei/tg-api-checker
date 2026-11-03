import unittest
from services.model_policy import select_models


class StrongerPolicyTests(unittest.TestCase):
    def test_nonchat_purposes_excluded(self):
        models = ['text-embedding-3-large', 'bge-rerank-v2', 'tts-1-hd', 'whisper-1', 'audio/speech-model', 'dall-e-3', 'sora-2', 'veo-3', 'video-generator', 'image-gen-xl', 'imagen-4.0', 'claude-3-5-sonnet', 'gpt-6-astra']
        allowed, skipped = select_models(models)
        self.assertEqual(allowed, ['gpt-6-astra'])
        self.assertEqual([m for m in models if m in skipped], models[:12])  # claude-3-5 тоже под версией

    def test_families_fully_excluded(self):
        for model in ['llama-3.1-70b', 'llama-4-maverick', 'grok-4', 'grok-beta', 'qwen2.5-72b', 'qwen3-235b-a22b', 'qwen3-vl-plus']:
            allowed, skipped = select_models([model, 'gpt-6-astra'])
            self.assertEqual(allowed, ['gpt-6-astra'], model)
            self.assertIn(model, skipped)

    def test_qwen_unlocks_at_v4(self):
        allowed, skipped = select_models(['qwen4-max', 'qwen3-max'])
        self.assertEqual(allowed, ['qwen4-max'])
        self.assertEqual(list(skipped), ['qwen3-max'])

    def test_deepseek_only_v4_plus(self):
        for model in ['deepseek-v3', 'deepseek-v3.2', 'deepseek-r1', 'deepseek-chat', 'deepseek-reasoner']:
            allowed, _ = select_models([model])
            self.assertEqual(allowed, [], model)
        self.assertEqual(select_models(['deepseek-v4'])[0], ['deepseek-v4'])

    def test_chat_multimodal_not_overexcluded(self):
        models = ['glm-5.3v-flash', 'gpt-6.1-vision', 'claude-opus-5.5']
        allowed, skipped = select_models(models)
        self.assertEqual(sorted(allowed), ['claude-opus-5.5', 'glm-5.3v-flash', 'gpt-6.1-vision'])
        self.assertEqual(skipped, {})
