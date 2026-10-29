import unittest
import tempfile
from pathlib import Path
from services.vault import Vault


class VaultTests(unittest.TestCase):
    def test_isolation_update_and_encryption(self):
        with tempfile.TemporaryDirectory() as d:
            v = Vault(d)
            rid = v.save(1, 'https://example.com/v1', 'secret-example', {'results': []})
            self.assertEqual(rid, v.save(1, 'https://example.com/v1/', 'secret-example', {'error': 'failed'}))
            self.assertIsNone(v.get(2, rid))
            self.assertEqual(v.get(1, rid)['result']['error'], 'failed')
            self.assertNotIn(b'secret-example', (Path(d)/'history.sqlite').read_bytes())
            v.note(2, rid, 'wrong')
            self.assertEqual(v.get(1, rid)['note'], '')
            v.delete(2, rid)
            self.assertIsNotNone(v.get(1, rid))
            v.delete(1, rid)
            self.assertIsNone(v.get(1, rid))
            v.db.close()

    def test_missing_secret_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            v = Vault(d)
            v.db.close()
            (Path(d)/'vault.key').unlink()
            with self.assertRaises(RuntimeError):
                Vault(d)
