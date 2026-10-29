from __future__ import annotations

from dataclasses import dataclass, field

import httpx
from services.queued_http import QueuedClient

from config import DETECT_TIMEOUT, KNOWN_PROVIDERS


@dataclass
class DetectionResult:
    """Результат определения провайдера и списка моделей.

    Attributes:
        base_url: Рабочий базовый URL API.
        provider_name: Человекочитаемое имя провайдера или домен.
        key_type: Тип ключа (PAYG / Free / Credits / Unknown).
        models: Список ID моделей с эндпоинта /models.
        error: Текст ошибки, если определить не удалось.
    """

    base_url: str
    provider_name: str
    key_type: str = "PAYG"
    models: list[str] = field(default_factory=list)
    error: str | None = None


async def detect_by_key(api_key: str) -> DetectionResult:
    """Не отправляет ключ неизвестного происхождения сторонним провайдерам."""
    return DetectionResult(
        base_url="",
        provider_name="Unknown",
        error="Пришли base URL вместе с ключом. По одному ключу надёжно определить сервер нельзя; публичный каталог не подтверждает доступ.",
    )


async def fetch_at(base_url: str, api_key: str) -> DetectionResult:
    """Проверяет ключ на явно указанном base_url (без перебора).

    Имя провайдера берём из домена URL.
    """
    base_url = base_url.rstrip("/")
    provider_name = base_url.split("//", 1)[-1].split("/", 1)[0]
    async with QueuedClient(timeout=DETECT_TIMEOUT) as client:
        from services.protocol_detect import native_catalog
        native_models, native_error = await native_catalog(client, base_url, api_key)
        models = native_models if native_models else await _fetch_models(client, base_url, api_key)
    if models is None and native_error:
        return DetectionResult(
            base_url=base_url,
            provider_name=provider_name,
            error=native_error + '. Это не доказывает, что ключ нерабочий.',
        )
    if models is None:
        return DetectionResult(
            base_url=base_url,
            provider_name=provider_name,
            error="Не удалось прочитать каталог /models. Это не доказывает, что ключ нерабочий: каталог может отсутствовать или быть недоступен.",
        )
    return DetectionResult(
        base_url=base_url,
        provider_name=provider_name,
        key_type=infer_key_type(api_key, models),
        models=models,
    )


async def _fetch_models(
    client: httpx.AsyncClient, base_url: str, api_key: str
) -> list[str] | None:
    """GET {base_url}/models. Список ID при успехе, None при любой ошибке."""
    try:
        r = await client.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if r.status_code != 200:
            return None
        data = r.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        ids = [m["id"] for m in items if isinstance(m, dict) and "id" in m]
        return ids
    except Exception:
        return None


def infer_key_type(api_key: str, models: list[str]) -> str:
    """Грубая эвристика типа ключа по префиксу и именам моделей."""
    prefixes = {
        "sk-ant-": "Anthropic API",
        "sk-or-v1-": "Credits",
        "gsk_": "Free tier",
        "r8_": "API",
    }
    for prefix, key_type in prefixes.items():
        if api_key.startswith(prefix):
            return key_type
    joined = " ".join(models).lower()
    if any(h in joined for h in ("free", "trial", "demo")):
        return "Free"
    return "PAYG"
