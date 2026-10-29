import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from services.vault import Vault
from services.jobs import run
from services.model_tester import ModelTestResult


class JobFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_error_does_not_stop_catalog(self):
        for status, error in [(401, 'invalid upstream key'), (429, 'insufficient_quota')]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                vault = Vault(directory)
                rid = vault.save(1, 'https://example.com/v1', 'fake', {'models': ['bad', 'good'], 'results': []})
                async def probe(url, key, models, count, protocol):
                    name = models[0]
                    return [ModelTestResult(name, name == 'good', status if name == 'bad' else 200, error if name == 'bad' else '')]
                with patch('services.jobs.test_models', side_effect=probe), patch('services.jobs.MAX_CONCURRENT_TESTS', 1):
                    await run(vault, 1, rid, ['bad', 'good'], 'chat', AsyncMock())
                job = vault.jobs(1, rid)[0]
                vault.db.close()
                self.assertEqual(job['state'], 'completed')
                self.assertEqual([r['model_id'] for r in job['data']['results']], ['bad', 'good'])
                vault.db.close()
