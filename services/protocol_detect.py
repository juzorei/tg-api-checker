import httpx

from services.protocols import request_spec, response_text

# 404/405 Unknown route / method — признак отсутствия endpoint, а не проблема ключа
_ROUTE_MISS = (404, 405, 501)


async def detect_protocol(client, base_url, key, model, preferred=None):
    """Определяет рабочий формат API по одному зонду на формат.

    Порядок: сохранённый preferred, затем chat, responses, anthropic, gemini.
    Ошибки авторизации/квоты не считаются несоответствием протокола:
    при первом таком ответе возвращается исходный формат.
    """
    from services.protocols import PROTOCOLS
    order = [p for p in ([preferred] if preferred else []) + list(PROTOCOLS) if p]
    for protocol in dict.fromkeys(order):
        url, headers, payload = request_spec(base_url, key, model, protocol, 16)
        try:
            response = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError:
            continue
        if response.status_code == 200:
            try:
                if response_text(response.json(), protocol).strip():
                    return protocol
            except (ValueError, TypeError, AttributeError, KeyError, IndexError):
                pass
        if response.status_code not in _ROUTE_MISS and response.status_code not in (400, 415, 422):
            # 401/403/402/429/423/5xx относятся к ключу или серверу — перебор не поможет
            return protocol
    return 'chat'


async def native_catalog(client, base_url, key):
    """Каталог для нативных Anthropic/Gemini, если OpenAI /models недоступен."""
    base_url = base_url.rstrip('/')
    host = base_url.split('//', 1)[-1].split('/', 1)[0].lower()
    try:
        if 'anthropic.com' in host:
            r = await client.get(
                base_url + '/v1/models',
                headers={'x-api-key': key, 'anthropic-version': '2023-06-01'},
            )
            if r.status_code == 200:
                data = r.json().get('data', [])
                return [m['id'] for m in data if isinstance(m, dict) and m.get('id')], None
            return [], f'Anthropic /models: HTTP {r.status_code}'
        if 'generativelanguage' in host or 'gemini' in host:
            r = await client.get(
                base_url + '/v1beta/models',
                headers={'x-goog-api-key': key},
            )
            if r.status_code == 200:
                data = r.json().get('models', [])
                return [m['name'].removeprefix('models/') for m in data if isinstance(m, dict) and m.get('name')], None
            return [], f'Gemini /models: HTTP {r.status_code}'
    except httpx.HTTPError as e:
        return [], f'Нативный каталог: {str(e)[:80]}'
    return [], None
