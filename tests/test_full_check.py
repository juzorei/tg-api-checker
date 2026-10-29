import unittest
from unittest.mock import AsyncMock, patch
from services.checking import check
from services.provider_detector import DetectionResult
from services.model_tester import ModelTestResult


class FullCheckTests(unittest.IsolatedAsyncioTestCase):
    async def test_checks_all_models(self):
        models = [f'm{i}' for i in range(27)]
        async def test(url, key, names, count, protocol='chat'):
            return [ModelTestResult(n, True, 200, '') for n in names[:count]]
        progress = AsyncMock()
        with patch('services.checking.fetch_at', AsyncMock(return_value=DetectionResult('https://example.com/v1', 'test', models=models))), patch('services.checking.test_models', side_effect=test), patch('services.checking.limits_summary', AsyncMock(return_value='unknown')):
            result = await check('https://example.com/v1', 'fake', full=True, progress=progress)
        self.assertEqual(len(result['results']), 27)
        self.assertEqual([r['model_id'] for r in result['results']], models)
        progress.assert_awaited_with(27, 27)
