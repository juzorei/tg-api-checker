from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
from services.queued_http import QueuedClient

from config import MAX_CONCURRENT_TESTS, TEST_TIMEOUT


@dataclass
class ModelTestResult:
    """Результат одного chat completion проба.

    Attributes:
        model_id: ID проверяемой модели.
        ok: Модель ответила 200.
        status_code: HTTP код ответа, None при сетевом сбое.
        error_msg: Короткое описание ошибки.
    """

    model_id: str
    ok: bool
    status_code: int | None
    error_msg: str
    protocol: str = 'chat'


TEST_PROMPT: list[dict] = [{"role": "user", "content": "Hi"}]


async def test_models(
    base_url: str,
    api_key: str,
    model_ids: list[str],
    sample_size: int,
    protocol: str = 'chat',
) -> list[ModelTestResult]:
    """Проверяет первые sample_size моделей параллельно.

    Args:
        base_url: Базовый URL API.
        api_key: API ключ.
        model_ids: Все доступные ID моделей.
        sample_size: Сколько моделей проверять.

    Returns:
        Ровно min(sample_size, len(model_ids)) результатов.
    """
    sample = model_ids[:sample_size]
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TESTS)
    async with QueuedClient(timeout=TEST_TIMEOUT) as client:
        tasks = [_test_one(client, semaphore, base_url, api_key, mid, protocol) for mid in sample]
        return list(await asyncio.gather(*tasks))


async def _test_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    base_url: str,
    api_key: str,
    model_id: str,
    protocol: str = 'chat',
) -> ModelTestResult:
    """Один проб chat completion с ограничением параллельности."""
    async with semaphore:
        try:
            from services.protocols import request_spec, response_text
            from config import MAX_OUTPUT_TOKENS
            url, headers, payload = request_spec(base_url, api_key, model_id, protocol, MAX_OUTPUT_TOKENS)
            r = await client.post(url, headers=headers, json=payload)
            if r.status_code == 400 and protocol == 'chat' and 'max_tokens' in r.text and 'unsupported' in r.text.lower():
                # Новые модели OpenAI не принимают max_tokens — пробуем max_completion_tokens.
                # Исходный 400 сохраняем, если повтор упал по сети или тоже вернул 400.
                try:
                    retry_url, retry_headers, retry_payload = request_spec(base_url, api_key, model_id, protocol, MAX_OUTPUT_TOKENS, token_param='max_completion_tokens')
                    retry = await client.post(retry_url, headers=retry_headers, json=retry_payload)
                except httpx.HTTPError:
                    retry = None
                if retry is not None and retry.status_code != 400:
                    url, headers, payload, r = retry_url, retry_headers, retry_payload, retry
            ok = False
            err = ""
            try:
                body = r.json()
                if r.status_code == 200:
                    content = response_text(body, protocol)
                    ok = isinstance(content, str) and bool(content.strip())
                    if not ok:
                        err = 'Пустой ответ: текст не получен (возможен малый лимит генерации)'
                else:
                    error = body.get('error', body)
                    if isinstance(error, dict):
                        err = ' · '.join(str(error[k]) for k in ('code', 'type', 'message', 'detail', 'reason') if error.get(k))
                        if not err:
                            err = 'Сервер не указал причину в стандартных полях ошибки'
                    else:
                        err = str(error)
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                if r.status_code == 200:
                    err = 'Некорректный JSON или структура ответа'
                else:
                    # Прокси и балансировщики отвечают HTML/текстом — показываем фрагмент вместо «не JSON».
                    # Вычищаем ключ ДО обрезки: иначе обрезанный фрагмент ключа уже не совпадёт с replace.
                    raw = ' '.join(r.text.strip().split()[:64])
                    if api_key:
                        raw = raw.replace(api_key, '[ключ скрыт]')
                    err = raw[:120] or 'Пустой ответ сервера'
            err = err.replace(api_key, '[ключ скрыт]')[:160]
            if r.status_code == 429 and r.headers.get('retry-after'):
                err += ' · Retry-After: ' + r.headers['retry-after'][:30]
            return ModelTestResult(
                model_id=model_id, ok=ok, status_code=r.status_code, error_msg=err, protocol=protocol
            )
        except httpx.TimeoutException:
            return ModelTestResult(model_id=model_id, ok=False, status_code=None, error_msg="timeout")
        except httpx.ConnectError:
            return ModelTestResult(model_id, False, None, 'Ошибка соединения (DNS/TLS/сервер недоступен)')
        except httpx.HTTPError:
            return ModelTestResult(model_id, False, None, 'Сетевая ошибка при чтении ответа')
