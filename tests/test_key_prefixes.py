import unittest
from handlers.api_check import parse_input


class PrefixTests(unittest.TestCase):
    def test_forwarded_prefixes(self):
        for key in ('sk_example12345', 'nvapi-example12345', 'vl-example12345'):
            with self.subTest(key=key):
                self.assertEqual(parse_input(f'Фул-скан\nEndpoint: https://example.com/v2\n🔑 {key}\nworking'), ('https://example.com/v2', key))

    def test_key_marker(self):
        self.assertEqual(parse_input('Endpoint: https://example.com/v1\n🔑 opaque123456\nworking'), ('https://example.com/v1', 'opaque123456'))
