import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from services.checking import check, report
from services.jobs import run
from services.vault import Vault
from services.model_tester import ModelTestResult
from services.provider_detector import DetectionResult


class PolicyIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_check_filters_before_sample(self):
        models = ['gpt-4'] * 25 + ['gpt-6']
        probe = AsyncMock(return_value=[ModelTestResult('gpt-6', True, 200, '')])
        with patch('services.checking.fetch_at', AsyncMock(return_value=DetectionResult('https://example.com/v1', 'test', models=models))), patch('services.checking.test_models', probe), patch('services.checking.limits_summary', AsyncMock(return_value='unknown')):
            result = await check('https://example.com/v1', 'fake')
        self.assertEqual(probe.await_args.args[2], ['gpt-6'])
        self.assertIn('gpt-4', result['models'])
        self.assertIn('gpt-4', result['skipped'])

    async def test_resume_skips_old_models_and_uses_whole_catalog(self):
        with tempfile.TemporaryDirectory() as d:
            v = Vault(d)
            try:
                rid = v.save(1, 'https://example.com/v1', 'fake', {'models': ['kimi-k2', 'kimi-k3', 'gpt-4', 'gpt-6'], 'results': []})
                jid = v.job_create(1, rid, {'models': ['kimi-k2', 'gpt-4', 'gpt-6'], 'results': [], 'protocol': 'chat'})
                resume = v.jobs(1, rid)[0]
                probe = AsyncMock(return_value=[ModelTestResult('gpt-6', True, 200, '')])
                with patch('services.jobs.test_models', probe):
                    await run(v, 1, rid, [], 'chat', AsyncMock(), resume)
                self.assertEqual(probe.await_count, 1)
                self.assertEqual(probe.await_args.args[2], ['gpt-6'])
                self.assertEqual(v.jobs(1,rid)[0]['data']['models'], ['gpt-6'])
                self.assertEqual(v.jobs(1,rid)[0]['id'], jid)
            finally:
                v.db.close()

    def test_report_separates_skipped_from_unchecked(self):
        text = report({'key':'fake', 'url':'https://example.com/v1', 'result': {'provider':'test','models':['gpt-4','gpt-6'], 'results':[]}})
        self.assertIn('Пропущено фильтром: 1', text)
        self.assertIn('не проверено: 1', text)
