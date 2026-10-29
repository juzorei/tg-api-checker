import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpcore
from httpcore._backends.auto import AutoBackend


def validate_ip(value):
    address = ipaddress.ip_address(value)
    mapped = getattr(address, 'ipv4_mapped', None)
    if not address.is_global or (mapped and not mapped.is_global):
        raise ValueError('Внутренние и служебные IP запрещены')
    return str(address)


def validate_url(value):
    url = urlsplit(str(value))
    if url.scheme not in ('https', 'http') or not url.hostname or url.username is not None or url.password is not None:
        raise ValueError('Нужен HTTP(S) URL без логина и пароля')
    host = url.hostname.rstrip('.').lower()
    if host == 'localhost' or host.endswith(('.localhost', '.local')):
        raise ValueError('Локальные адреса запрещены')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return
    validate_ip(host)


class PublicNetworkBackend(AutoBackend):
    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        try:
            addresses = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout=timeout or 15)
            ips = list(dict.fromkeys(validate_ip(item[4][0]) for item in addresses))
        except (ValueError, OSError, asyncio.TimeoutError) as exc:
            raise httpcore.ConnectError('Адрес недоступен или запрещён политикой сети') from exc
        if not ips:
            raise httpcore.ConnectError('DNS не вернул адрес')
        # Connect to the validated numeric address; HTTPcore retains the original TLS SNI.
        return await super().connect_tcp(ips[0], port, timeout, local_address, socket_options)
