import unittest
from handlers.api_check import parse_input


class ParsingPriorityTests(unittest.TestCase):
    def test_report_with_provider_label_accepted(self):
        self.assertEqual(parse_input('Endpoint: https://example.com/v1\nПровайдер: example.com\n🔑 sk-demo123456'), ('https://example.com/v1', 'sk-demo123456'))

    def test_trailing_punctuation_after_key(self):
        self.assertEqual(parse_input('https://example.com/v1\nAPI key: sk-demo123456.'), ('https://example.com/v1', 'sk-demo123456'))

    def test_same_url_with_and_without_slash(self):
        self.assertEqual(parse_input('https://example.com/v1 https://example.com/v1/ sk-demo123456'), ('https://example.com/v1', 'sk-demo123456'))

    def test_model_name_with_dots_not_extra_endpoint(self):
        self.assertEqual(parse_input('Фулл-скан https://example.com/v1 sk-demo123456\nМодели: meta.llama, qwen2.5'), ('https://example.com/v1', 'sk-demo123456'))

    def test_genuinely_different_pairs_still_ambiguous(self):
        with self.assertRaises(ValueError):
            parse_input('https://one.example/v1 https://two.example/v1 sk-demo123456')
        with self.assertRaises(ValueError):
            parse_input('https://example.com/v1 sk-demo123456 sk-other89012')
