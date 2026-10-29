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
    422: "неподдерживаемые параметры запроса",
    423: "Locked — сервер заблокировал запрос; причина зависит от провайдера",
    429: "ограничение частоты или квоты",
}


def short_error(status: int | None, msg: str) -> str:
    """Короткое описание ошибки для строки модели."""
    if status in _ERROR_LABELS:
        return _ERROR_LABELS[status]
    if status is not None and status >= 500:
        return "ошибка сервера"
    if status is None:
        return "таймаут" if ("timeout" in msg.lower() or "timed out" in msg.lower()) else "сбой сети"
    if status == 200:
        return "HTTP 200 без корректного текста модели"
    return f"ошибка {status}"


def format_check_result(
    provider_name: str,
    key_type: str,
    api_key: str,
    base_url: str,
    total_models: int,
    results: list[ModelTestResult],
    limits_text: str = "не раскрываются сервером",
    skipped_count: int = 0,
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
        f"🌐 Base URL: <code>{esc(base_url)}</code>",
        f"🔑 Ключ: <code>{esc(api_key)}</code>",
        "",
        f"💳 Лимиты: {esc(limits_text)}",
        "",
        f"📦 Ответившие модели ({ok_count}):",
        _preview_models([r for r in results if r.ok], ok_count) or "Ни одна из проверенных не ответила.",
        "",
        f"💬 Отвечают модели: {ok_count} из {tested}",
    ]

    lines.append(f"В каталоге: {total_models} · не проверено: {max(0, total_models - skipped_count - tested)}")
    if skipped_count:
        lines.append(f"⏭ Пропущено фильтром: {skipped_count} · причины в «Пропущенные»")
    from collections import Counter

    errors = Counter(
        (r.status_code, (r.error_msg or short_error(r.status_code, '')).replace(api_key, '[ключ скрыт]'))
        for r in results if not r.ok
    )
    if errors:
        lines.extend(['', '⚠️ Причины ошибок:'])
        for (status, reason), count in errors.most_common(4):
            code = f'HTTP {status}' if status else 'сеть/таймаут'
            lines.append(f'• {count} × {code}: {esc(reason[:160])}')
        hidden = sum(errors.values()) - sum(count for _, count in errors.most_common(4))
        if hidden:
            lines.append(f'• Ещё {hidden} ошибок с другими причинами')

    lines.append("")

    if ok_count > 0:
        status_line = f"🟢 ключ жив, модели отвечают · {tested} проб · {provider_domain}"
    else:
        status_line = f"🟡 Каталог получен, доступ к чату не подтверждён · {tested} проб"
    lines.append(status_line)

    return "\n".join(lines)


def _preview_models(results: list[ModelTestResult], total: int) -> str:
    """Превью с отдельным копируемым ID каждой модели."""
    ids = [r.model_id for r in results[:10]]
    lines = [f"<code>{html.escape(model_id)}</code>" for model_id in ids]
    if total > len(ids):
        lines.append(f"… ещё {total - len(ids)} — кнопка «Все модели»")
    return "\n".join(lines)


def format_models_page(provider_name: str, models: list[str], page: int, page_size: int) -> str:
    """Страница полного списка моделей для кнопки 'Все модели'."""
    esc = html.escape
    total_pages = max(1, (len(models) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    chunk = models[start : start + page_size]

    header = f"📋 {esc(provider_name)} — все модели ({len(models)})"
    body = "\n".join(f"<code>{esc(model_id)}</code>" for model_id in chunk)
    footer = f"Стр. {page + 1} из {total_pages}"
    return f"{header}\n\n{body}\n\n{footer}"
