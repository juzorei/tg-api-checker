import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from handlers import history
from services.checking import check, report
from services.jobs import run
from services.model_tester import ModelTestResult
from services.provider_detector import DetectionResult
from services.vault import Vault


class FilterToggleTests(unittest.IsolatedAsyncioTestCase):
    async def test_check_without_filter_probes_all(self):
        models = ['gpt-4', 'llama-3.1', 'text-embedding-3', 'gpt-6']
        probe = AsyncMock(return_value=[ModelTestResult('gpt-6', True, 200, '')])
        with patch('services.checking.fetch_at', AsyncMock(return_value=DetectionResult('https://example.com/v1', 't', models=models))), patch('services.checking.test_models', probe), patch('services.checking.limits_summary', AsyncMock(return_value='x')):
            result = await check('https://example.com/v1', 'fake', use_filter=False)
        self.assertEqual(probe.await_args.args[2], models)
        self.assertEqual(result['skipped'], {})

    def test_report_marks_filter_disabled(self):
        record = {'key': 'fake', 'url': 'https://example.com/v1', 'result': {'provider': 't', 'models': ['gpt-4', 'gpt-6'], 'results': [], 'filter_disabled': True}}
        text = report(record)
        self.assertIn('Фильтр версий отключён', text)
        self.assertNotIn('Пропущено фильтром', text)

    async def test_jobs_without_filter_probes_all(self):
        with tempfile.TemporaryDirectory() as d:
            vault = Vault(d)
            try:
                rid = vault.save(1, 'https://example.com/v1', 'fake', {'models': ['gpt-4', 'gpt-6'], 'results': []})
                probe = AsyncMock(return_value=[ModelTestResult('gpt-4', True, 200, '')])
                with patch('services.jobs.test_models', probe):
                    await run(vault, 1, rid, ['gpt-4', 'gpt-6'], 'chat', AsyncMock(), use_filter=False)
                self.assertEqual(probe.await_count, 2)
            finally:
                vault.db.close()

    async def test_toggle_button_saves_flag(self):
        store = Mock()
        record = {'result': {'models': ['gpt-4'], 'results': []}, 'url': 'https://example.com', 'key': 'fake'}
        store.get.return_value = record
        call = SimpleNamespace(from_user=SimpleNamespace(id=123), data='h:filter:1', answer=AsyncMock(), message=Mock())
        with patch('handlers.history.vault', return_value=store), patch('handlers.history.edit', AsyncMock()), patch('handlers.history.report', return_value='r'):
            await history.callback(call)
        self.assertTrue(record['result']['filter_disabled'])
        store.save.assert_called_once()
