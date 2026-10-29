import unittest
from services.network_safety import validate_ip, validate_url


class NetworkSafetyTests(unittest.TestCase):
    def test_private_addresses_rejected(self):
        for value in ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '::ffff:127.0.0.1', '192.168.1.5']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_ip(value)

    def test_public_address(self):
        self.assertEqual(validate_ip('1.1.1.1'), '1.1.1.1')

    def test_url_credentials_rejected(self):
        for url in ['https://user:pass@example.com/v1', 'file:///tmp/test', 'https://localhost/v1']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)
