from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

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


TEST_PROMPT: list[dict] = [{"role": "user", "content": "Hi"}]


async def test_models(
    base_url: str,
    api_key: str,
    model_ids: list[str],
    sample_size: int,
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
    async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
        tasks = [_test_one(client, semaphore, base_url, api_key, mid) for mid in sample]
        return list(await asyncio.gather(*tasks))


async def _test_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    base_url: str,
    api_key: str,
    model_id: str,
) -> ModelTestResult:
    """Один проб chat completion с ограничением параллельности."""
    async with semaphore:
        try:
            r = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model_id, "messages": TEST_PROMPT, "max_tokens": 5},
            )
            ok = r.status_code == 200
            err = ""
            if not ok:
                try:
                    body = r.json()
                    err = str(body.get("error", {}).get("message", ""))[:80]
                except Exception:
                    err = ""
            return ModelTestResult(
                model_id=model_id, ok=ok, status_code=r.status_code, error_msg=err
            )
        except httpx.TimeoutException:
            return ModelTestResult(model_id=model_id, ok=False, status_code=None, error_msg="timeout")
        except Exception as e:
            return ModelTestResult(
                model_id=model_id, ok=False, status_code=None, error_msg=str(e)[:80]
            )
