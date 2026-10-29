import asyncio
import unittest
import httpx
from services.queued_http import QueuedClient, _hosts


class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_between_clients(self):
        _hosts.clear()
        active = 0
        peak = 0
        async def respond(request):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(.01)
            active -= 1
            return httpx.Response(200)
        async with QueuedClient(transport=httpx.MockTransport(respond)) as a, QueuedClient(transport=httpx.MockTransport(respond)) as b:
            await asyncio.gather(*( (a if i%2 else b).get('https://example.com/a') for i in range(25)))
        self.assertEqual(peak, 10)
        _hosts.clear()
