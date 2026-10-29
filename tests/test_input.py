import unittest
from handlers.api_check import parse_input


class InputTests(unittest.TestCase):
    def test_report(self):
        self.assertEqual(parse_input('⚡ Фаст-скан\n🌐 Endpoint:https://api.example.com/v1\n🔑 sk-test123456\n✅ working'), ('https://api.example.com/v1', 'sk-test123456'))

    def test_json(self):
        self.assertEqual(parse_input('{"base_url":"https://api.example.com/v1", "api_key":"opaque123456"}'), ('https://api.example.com/v1', 'opaque123456'))

    def test_markdown(self):
        self.assertEqual(parse_input('Адрес: (https://api.example.com/v1). Ключ: `sk-test123456`'), ('https://api.example.com/v1', 'sk-test123456'))

    def test_bearer(self):
        self.assertEqual(parse_input('Authorization: Bearer opaque123456'), (None, 'opaque123456'))

    def test_plain_pair(self):
        self.assertEqual(parse_input('https://api.example.com/v1 opaque123456'), ('https://api.example.com/v1', 'opaque123456'))

    def test_noise(self):
        self.assertEqual(parse_input('Привет, проверь этот отчёт'), (None, None))

    def test_ambiguous(self):
        with self.assertRaises(ValueError):
            parse_input('https://a.example/v1 https://b.example/v1 sk-test123456')

    def test_repeated(self):
        self.assertEqual(parse_input('sk-test123456 повтор sk-test123456'), (None, 'sk-test123456'))

    def test_url_only(self):
        self.assertEqual(parse_input('Endpoint: https://api.example.com/v1'), ('https://api.example.com/v1', None))
