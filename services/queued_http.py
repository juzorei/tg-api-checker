import asyncio
from urllib.parse import urlsplit
import httpx

from config import MAX_CONCURRENT_TESTS

_global = asyncio.Semaphore(MAX_CONCURRENT_TESTS)
_hosts = {}


class QueuedClient(httpx.AsyncClient):
    def __init__(self, **kwargs):
        from services.network_safety import PublicNetworkBackend
        if 'transport' not in kwargs:
            transport = httpx.AsyncHTTPTransport(retries=0)
            transport._pool._network_backend = PublicNetworkBackend()
            kwargs['transport'] = transport
        kwargs['trust_env'] = False
        kwargs['follow_redirects'] = False
        super().__init__(**kwargs)

    async def send(self, request, **kwargs):
        from services.network_safety import validate_url
        try:
            validate_url(request.url)
        except ValueError as exc:
            raise httpx.ConnectError(str(exc), request=request) from exc
        kwargs['follow_redirects'] = False
        host = urlsplit(str(request.url)).hostname
        lock = _hosts.setdefault(host, asyncio.Semaphore(MAX_CONCURRENT_TESTS))
        async with lock:
            async with _global:
                return await super().send(request, **kwargs)
