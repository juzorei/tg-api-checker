import unittest
from unittest.mock import AsyncMock, patch
from services.checking import check
from services.model_tester import ModelTestResult
from services.provider_detector import DetectionResult


class ThrottleTests(unittest.IsolatedAsyncioTestCase):
    async def test_sample_throttles_after_rate_limit(self):
        calls = []
        async def probe(url, key, models, count, protocol='chat'):
            calls.append(list(models))
            return [ModelTestResult(m, False, 429, 'Too Many Requests' if not calls else 'retry') for m in models]
        with patch('services.checking.fetch_at', AsyncMock(return_value=DetectionResult('https://example.com/v1', 't', models=[f'm{i}' for i in range(25)]))), patch('services.checking.test_models', side_effect=probe), patch('services.checking.limits_summary', AsyncMock(return_value='x')), patch('services.checking.sleep', new_callable=AsyncMock):
            await check('https://example.com/v1', 'fake')
        self.assertEqual(len(calls[0]), 10)
        self.assertTrue(all(len(chunk) == 1 for chunk in calls[1:]), calls)
        self.assertEqual(len(calls), 11)
