import json
from html import escape
from urllib.parse import urlsplit

import httpx


async def diagnose(client, base_url, key, model):
    lines = [f'🔬 Модель: <code>{escape(model)}</code>', 'Эта диагностика не доказывает идентичность скрытой модели.']
    probes = [
        ('Следование инструкции', {'messages': [{'role': 'user', 'content': 'Reply exactly PONG'}]}),
        ('JSON mode', {'messages': [{'role': 'user', 'content': 'Return JSON: {"answer":42}'}], 'response_format': {'type': 'json_object'}}),
        ('Вызов инструмента', {'messages': [{'role': 'user', 'content': 'Call ping with no arguments.'}], 'tools': [{'type': 'function', 'function': {'name': 'ping', 'parameters': {'type': 'object', 'properties': {}}}}], 'tool_choice': {'type': 'function', 'function': {'name': 'ping'}}}),
    ]
    for name, payload in probes:
        try:
            response = await client.post(base_url.rstrip('/') + '/chat/completions', headers={'Authorization': f'Bearer {key}'}, json={'model': model, 'max_tokens': 128, **payload})
            if response.status_code != 200:
                lines.append(f'⚠️ {name}: HTTP {response.status_code} — тест не выполнен; это не доказательство подмены.')
                continue
            data = response.json()
            message = data['choices'][0]['message']
            content = message.get('content') or ''
            if name == 'JSON mode':
                try:
                    passed = json.loads(content) == {'answer': 42}
                except (ValueError, TypeError):
                    passed = False
            elif name == 'Вызов инструмента':
                calls = message.get('tool_calls') or []
                passed = any(c.get('function', {}).get('name') == 'ping' and json.loads(c['function'].get('arguments', 'null')) == {} for c in calls)
            else:
                passed = content.strip() == 'PONG'
            reported = str(data.get('model', 'не указан'))[:160]
            lines.append(f'{"✅" if passed else "⚠️"} {name}: {"пройден" if passed else "ожидаемый результат не получен"}\nID в ответе: <code>{escape(reported)}</code>')
        except httpx.HTTPError:
            lines.append(f'⚠️ {name}: сетевая ошибка или таймаут.')
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            lines.append(f'⚠️ {name}: некорректная структура ответа.')
    lines.append('Итог: для установления реальной модели недостаточно данных. ID сообщает сервер; он может быть псевдонимом.')
    return '\n\n'.join(lines)


async def limits_summary(client, base_url, key):
    from html import unescape

    report = await limits(client, base_url, key)
    selected = []
    for line in report.splitlines():
        if line.startswith(('<code>', 'Баланс:', 'limit:', 'limit_remaining:', 'usage:')):
            selected.append(unescape(line.replace('<code>', '').replace('</code>', '')))
        elif 'HTTP ' in line and not line.endswith('HTTP 200'):
            selected.append(line)
        elif 'ошибка' in line.lower() or 'неизвестен' in line:
            selected.append(line)
    return ' · '.join(selected)[:450] if selected else 'не раскрываются сервером'


async def limits(client, base_url, key):
    base_url = base_url.rstrip('/')
    lines = ['💳 Лимиты ключа', 'Лимиты могут относиться к аккаунту или endpoint, а не отдельно к ключу.']
    headers = {'Authorization': f'Bearer {key}'}
    try:
        response = await client.get(base_url + '/models', headers=headers)
        lines.append(f'GET /models: HTTP {response.status_code}')
        found = [(k, v) for k, v in response.headers.items() if k.lower().startswith(('x-ratelimit-', 'ratelimit-')) or k.lower() == 'retry-after']
        if found:
            lines.extend(f'<code>{escape(k[:100])}</code>: {escape(v[:150])}' for k, v in found[:16])
        else:
            lines.append('Сервер не раскрыл rate limits в ответе /models. Лимиты чата могут отличаться.')
        host = urlsplit(base_url).hostname
        if host == 'api.deepseek.com' and base_url in ('https://api.deepseek.com', 'https://api.deepseek.com/v1'):
            balance = await client.get('https://api.deepseek.com/user/balance', headers=headers)
            if balance.status_code == 200:
                entries = balance.json().get('balance_infos', [])
                if not entries:
                    lines.append('Баланс: данные не раскрыты.')
                for item in entries[:5]:
                    lines.append('Баланс: ' + escape(str(item.get('total_balance', 'не указан'))[:80]) + ' ' + escape(str(item.get('currency', ''))[:20]))
            else:
                lines.append(f'Баланс DeepSeek: HTTP {balance.status_code}, получить не удалось.')
        elif base_url == 'https://openrouter.ai/api/v1':
            balance = await client.get(base_url + '/key', headers=headers)
            if balance.status_code == 200:
                data = balance.json()['data']
                for field in ('limit', 'limit_remaining', 'usage', 'usage_daily', 'usage_monthly'):
                    if field in data:
                        value = 'не задан' if data[field] is None else str(data[field])[:80]
                        lines.append(f'{field}: {escape(value)}')
                lines.append('Источник: OpenRouter /key; значения кредитов, не количество токенов.')
            else:
                lines.append(f'Квота OpenRouter: HTTP {balance.status_code}, получить не удалось.')
        else:
            lines.append('Баланс и общая квота: не раскрываются через стандартный OpenAI API. Для этого провайдера адаптер не подключён.')
    except httpx.HTTPError:
        lines.append('Сетевая ошибка или таймаут. Остаток неизвестен.')
    except (ValueError, KeyError, TypeError, AttributeError):
        lines.append('Неожиданный ответ провайдера. Остаток неизвестен.')
    return '\n'.join(lines)
