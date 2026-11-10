import asyncio

import httpx

from services.model_tester import ModelTestResult

API = 'https://api.replicate.com/v1'
_TERMINAL = ('succeeded', 'failed', 'canceled')


def build_input(schema):
    """Минимальный валидный вход из openapi_schema модели.

    Возвращает None, если обязательные поля требуют файл/объект —
    такую модель generic-запросом не проверить.
    """
    if not isinstance(schema, dict):
        return None
    components = schema.get('components', {}).get('schemas', {})
    input_schema = components.get('Input') or {}
    props = input_schema.get('properties') or {}
    required = input_schema.get('required') or []
    if not props:
        return {}
    data = {}
    for name in required:
        spec = props.get(name) or {}
        if spec.get('format') in ('uri', 'binary'):
            return None
        if 'default' in spec:
            data[name] = spec['default']
        elif spec.get('enum'):
            data[name] = spec['enum'][0]
        else:
            kind = spec.get('type')
            if kind == 'string':
                data[name] = 'OK'
            elif kind == 'integer':
                data[name] = 1
            elif kind == 'number':
                data[name] = 1.0
            elif kind == 'boolean':
                data[name] = False
            elif kind == 'array':
                data[name] = []
            else:
                return None
    return data


async def list_models(client, key):
    """Список моделей Replicate и их openapi_schema."""
    models, schemas = [], {}
    url = API + '/models'
    try:
        while url and len(models) < 500:
            r = await client.get(url, headers={'Authorization': f'Bearer {key}'})
            if r.status_code != 200:
                return [], {}, f'Replicate /models: HTTP {r.status_code}'
            data = r.json()
            for item in data.get('results', []):
                owner, name = item.get('owner'), item.get('name')
                if not owner or not name:
                    continue
                model_id = f'{owner}/{name}'
                models.append(model_id)
                version = item.get('latest_version') or {}
                schemas[model_id] = version.get('openapi_schema') or {}
            url = data.get('next')
    except httpx.HTTPError as exc:
        return [], {}, f'Replicate: {str(exc)[:80]}'
    return models, schemas, None


def _result(model_id, status, body=None):
    body = body or {}
    ok = status == 'succeeded'
    error = '' if ok else str(body.get('error') or status)[:160]
    return ModelTestResult(model_id, ok, 200 if ok else None, error, 'replicate')


async def probe_many(client, key, items, timeout, progress=None):
    """Запускает predictions для моделей и опрашивает до завершения/таймаута."""
    results = []
    pending = []
    for model_id, schema in items:
        data = build_input(schema)
        if data is None:
            results.append(ModelTestResult(model_id, False, None, 'Нет пригодной схемы входа (нужны файлы/объекты)', 'replicate'))
            continue
        try:
            r = await client.post(f'{API}/models/{model_id}/predictions', headers={'Authorization': f'Bearer {key}'}, json={'input': data})
        except httpx.HTTPError as exc:
            results.append(ModelTestResult(model_id, False, None, f'Сеть: {str(exc)[:60]}', 'replicate'))
            continue
        if r.status_code not in (200, 201):
            try:
                detail = str(r.json().get('detail') or r.json().get('error') or '')[:120]
            except (ValueError, AttributeError):
                detail = r.text.strip()[:120]
            results.append(ModelTestResult(model_id, False, r.status_code, detail or f'HTTP {r.status_code}', 'replicate'))
            continue
        body = r.json()
        pending.append((model_id, body.get('id'), body.get('status', 'starting')))

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while pending and loop.time() < deadline:
        still = []
        for model_id, prediction_id, status in pending:
            if status in _TERMINAL:
                results.append(_result(model_id, status))
                continue
            try:
                r = await client.get(f'{API}/predictions/{prediction_id}', headers={'Authorization': f'Bearer {key}'})
                body = r.json() if r.status_code == 200 else {}
            except httpx.HTTPError:
                body = {}
            status = body.get('status', status)
            if status in _TERMINAL:
                results.append(_result(model_id, status, body))
            else:
                still.append((model_id, prediction_id, status))
        pending = still
        if pending:
            await asyncio.sleep(2)
    for model_id, _, status in pending:
        results.append(ModelTestResult(model_id, False, None, f'Не завершилась за {int(timeout)} с (статус {status})', 'replicate'))
    if progress:
        await progress(len(results), len(items))
    return results
