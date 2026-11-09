import asyncio
import unittest
import httpx
from services.formatters import format_check_result
from services.model_tester import ModelTestResult, _test_one


class ErrorReadingTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_json_429_keeps_server_snippet(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(429, text='<html>Too Many Requests</html>'))) as client:
            result = await _test_one(client, asyncio.Semaphore(1), 'https://example.com/v1', 'secret-key', 'm')
        self.assertFalse(result.ok)
        self.assertIn('Too Many Requests', result.error_msg)
        self.assertNotIn('не в формате JSON', result.error_msg)

    async def test_key_straddling_truncation_is_redacted(self):
        key = 'secret-test-key'
        body = 'p' * 110 + key
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(429, text=body))) as client:
            result = await _test_one(client, asyncio.Semaphore(1), 'https://example.com/v1', key, 'm')
        self.assertNotIn('secret-tes', result.error_msg)
        self.assertNotIn(key, result.error_msg)

    def test_aggregated_line_readable(self):
        rows = [ModelTestResult(str(i), False, 429, '<html>Too Many Requests</html>') for i in range(20)]
        text = format_check_result('API', '', 'key', 'https://example.com/v1', 20, rows)
        self.assertIn('20 × HTTP 429: ограничение частоты или квоты', text)
        self.assertIn('Too Many Requests', text)
        self.assertNotIn('не в формате JSON', text)
