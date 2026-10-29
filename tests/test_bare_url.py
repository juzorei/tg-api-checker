import unittest
from handlers.api_check import parse_input


class BareUrlTests(unittest.TestCase):
    def test_bare_domain_and_key(self):
        self.assertEqual(parse_input('llmgateway.zendure.tech/litellm/v1\nsk-example123'), ('https://llmgateway.zendure.tech/litellm/v1', 'sk-example123'))

    def test_bare_url_only(self):
        self.assertEqual(parse_input('example.com/v1'), ('https://example.com/v1', None))

    def test_report(self):
        self.assertEqual(parse_input('Endpoint: example.com:8443/v1\nКлюч: sk-example123'), ('https://example.com:8443/v1', 'sk-example123'))

    def test_email_not_endpoint(self):
        self.assertEqual(parse_input('Почта user@example.com sk-example123'), (None, 'sk-example123'))

    def test_bare_fallback_still_ambiguity_within_fallback(self):
        with self.assertRaises(ValueError):
            parse_input('one.example/v1 two.example/v1 sk-example123')
