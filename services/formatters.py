from __future__ import annotations

import html

from config import FAILING_LINES_LIMIT
from services.model_tester import ModelTestResult

# Короткие русские описания HTTP кодов для строк моделей
_ERROR_LABELS: dict[int, str] = {
    400: "запрос отклонён",
    401: "неверный ключ",
    402: "недостаточно средств",
    403: "доступ ограничен",
    404: "модель не найдена",
    422: "слишком большой запрос",
    429: "лимит запросов",
}


def short_error(status: int | None, msg: str) -> str:
    """Короткое описание ошибки для строки модели."""
    if status in _ERROR_LABELS:
        return _ERROR_LABELS[status]
    if status is not None and status >= 500:
        return "ошибка сервера"
    if status is None:
        return "таймаут" if ("timeout" in msg.lower() or "timed out" in msg.lower()) else "сбой сети"
    return f"ошибка {status}"


def format_check_result(
    provider_name: str,
    key_type: str,
    api_key: str,
    base_url: str,
    total_models: int,
    results: list[ModelTestResult],
) -> str:
    """Собирает главный отчёт в стиле скрина (HTML).

    Args:
        provider_name: Имя провайдера или домен.
        key_type: Тип ключа из эвристики.
        api_key: Ключ как прислал пользователь (показываем целиком, как в оригинале).
        base_url: Рабочий эндпоинт.
        total_models: Всего моделей по /models.
        results: Результаты пробов выборки.

    Returns:
        HTML строка для Telegram.
    """
    esc = html.escape
    provider_domain = esc(provider_name.split(" ")[0].split("//")[-1])
    tested = len(results)
    ok_count = sum(1 for r in results if r.ok)

    lines: list[str] = [
        f"🔑 Чек API — <b>{esc(provider_name)}</b>",
        "",
        f"<code>{esc(api_key)}</code>",
        "",
        "📋 Описание:",
        f"▪️ Провайдер: {provider_domain}",
        f"▪️ Тип ключа: {esc(key_type)}",
        "▪️ План: —",
        "",
        f"📦 Доступно моделей ({total_models}):",
        f"<code>{esc(_preview_models(results, total_models))}</code>",
        "",
        f"💬 Отвечают модели: {ok_count} из {tested}",
    ]

    failing = [r for r in results if not r.ok]
    for r in failing[:FAILING_LINES_LIMIT]:
        icon = "🚫" if (r.status_code or 0) in (401, 403) else "❌"
        lines.append(
            f"{icon} {esc(r.model_id)} — {r.status_code or '—'} · "
            f"{esc(short_error(r.status_code, r.error_msg))}"
        )
    if len(failing) > FAILING_LINES_LIMIT:
        lines.append(f"… и ещё {len(failing) - FAILING_LINES_LIMIT} без ответа")

    lines += [
        "",
        "🌐 Основной эндпоинт:",
        f"✅ {esc(base_url)}",
        "",
    ]

    if ok_count > 0:
        status_line = f"🟢 ключ жив, модели отвечают · {tested} проб · {provider_domain}"
    else:
        status_line = f"🟡 ключ жив, чат не ответил · {tested} проб · {provider_domain}"
    lines.append(status_line)

    return "\n".join(lines)


def _preview_models(results: list[ModelTestResult], total: int) -> str:
    """Превью списка моделей: первые ~5 ID, обрезанные по длине."""
    ids = [r.model_id for r in results]
    if not ids:
        return ""
    text = ",".join(ids[:5])
    if total > 5:
        text += ",…"
    return text[:200]


def format_models_page(provider_name: str, models: list[str], page: int, page_size: int) -> str:
    """Страница полного списка моделей для кнопки 'Все модели'."""
    esc = html.escape
    total_pages = max(1, (len(models) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    chunk = models[start : start + page_size]

    header = f"📋 {esc(provider_name)} — все модели ({len(models)})"
    body = f"<code>{esc(', '.join(chunk))}</code>"
    footer = f"Стр. {page + 1} из {total_pages}"
    return f"{header}\n\n{body}\n\n{footer}"
