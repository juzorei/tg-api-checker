import asyncio
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from services.checking import check
from services.model_tester import ModelTestResult
from services.provider_detector import DetectionResult
from services.protocol_detect import detect_protocol


class RateLimitStopTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_host_uses_gemini_protocol(self):
        probe = AsyncMock(return_value=[ModelTestResult('gemini-4-argon', True, 200, 'ok', 'gemini')])
        with patch('services.checking.fetch_at', AsyncMock(return_value=DetectionResult('https://generativelanguage.googleapis.com/v1beta', 't', models=['gemini-4-argon']))), patch('services.checking.test_models', probe), patch('services.checking.limits_summary', AsyncMock(return_value='x')):
            result = await check('https://generativelanguage.googleapis.com/v1beta', 'fake')
        self.assertEqual(result['protocol'], 'gemini')

    async def test_429_does_not_lock_protocol(self):
        def respond(request):
            url = str(request.url)
            if url.endswith('/chat/completions'):
                return httpx.Response(429, text='rate limited')
            if url.endswith('/:generateContent') or ':generateContent' in url:
                return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': 'OK'}]}}]})
            return httpx.Response(404)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            protocol = await detect_protocol(client, 'https://example.com/v1beta', 'fake', 'gemini-4')
        self.assertEqual(protocol, 'gemini')

    async def test_sample_stops_after_repeated_rate_limit(self):
        calls = []
        async def probe(url, key, models, count, protocol='chat'):
            calls.append(list(models))
            return [ModelTestResult(m, False, 429, 'rate limited') for m in models]
        with patch('services.checking.fetch_at', AsyncMock(return_value=DetectionResult('https://example.com/v1', 't', models=[f'm{i}' for i in range(20)]))), patch('services.checking.test_models', side_effect=probe), patch('services.checking.limits_summary', AsyncMock(return_value='x')), patch('services.checking.sleep', new_callable=AsyncMock):
            result = await check('https://example.com/v1', 'fake')
        self.assertLess(len(result['results']), 20)
        self.assertEqual(len(calls), 3)
