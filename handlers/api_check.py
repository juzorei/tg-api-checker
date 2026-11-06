from __future__ import annotations

import re
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import TEST_SAMPLE_SIZE
from services.formatters import format_check_result
from services.model_tester import test_models
from services.provider_detector import DetectionResult, detect_by_key, fetch_at

router = Router()
router.message.filter(F.chat.type == 'private')

# Последний чек пользователя: user_id -> {"key": ..., "base_url": ... | None}
last_check: dict[int, dict] = {}
# Пользователь прислал URL без ключа: user_id -> base_url
pending_base_url: dict[int, str] = {}


@router.message(Command("start"))
async def cmd_start(msg: Message) -> None:
    await msg.answer(
        "👋 <b>API Checker Bot</b>\n\n"
        "/keys — история ключей\n/batch — собрать пакет (до 50 пар)\n/cancel — отмена\n\n"
        "Ключи сохраняются зашифрованными для повторных проверок. Удаление — в /keys.\n\n"
        "Пришли base URL и API ключ — покажу модели и проверю ответы. Пробы могут расходовать баланс.\n\n"
        "Или одной строкой: <code>https://api.example.com/v1 sk-...</code>\n"
        "— проверю напрямую на этом base URL."
    )


@router.message(F.text)
async def handle_input(msg: Message) -> None:
    """Разбирает ввод: ключ, base URL, или URL + ключ одной строкой."""
    text = (msg.text or "").strip()
    if not text or text.startswith("/"):
        return
    uid = msg.from_user.id if msg.from_user else 0

    if msg.chat.type != 'private':
        return

    try:
        pairs = parse_pairs(text)
    except ValueError:
        # Ключ перед URL — прежний парсер принимает любой порядок
        try:
            base_url, api_key = parse_input(text)
        except ValueError:
            base_url = api_key = None
        if base_url and api_key:
            from handlers.history import single
            await single(msg, uid, base_url, api_key)
            return
        pending_base_url.pop(uid, None)
        await msg.answer(
            "Не удалось однозначно сопоставить адреса и ключи. "
            "Пришли пары URL + ключ, каждую с новой строки."
        )
        return

    if not pairs:
        # Ключ без URL или нераспознанный ввод — прежняя логика
        try:
            base_url, api_key = parse_input(text)
        except ValueError:
            pending_base_url.pop(uid, None)
            await msg.answer("Найдено несколько адресов или ключей. Пришли одну пару URL + ключ.")
            return
        if base_url and not api_key:
            pending_base_url[uid] = base_url
            await msg.answer("Теперь пришли API ключ для этого base URL.")
            return
        if api_key and not base_url and uid in pending_base_url:
            base_url = pending_base_url.pop(uid)
        elif uid in pending_base_url:
            pending_base_url.pop(uid)
        if not api_key:
            await msg.answer(
                "⚠️ Не понял ввод. Пришли API ключ (sk-...) или "
                "<code>https://base.url/v1 ключ</code> одной строкой."
            )
            return
        if not base_url:
            await msg.answer('Пришли base URL вместе с ключом.')
            return
        from handlers.history import single
        await single(msg, uid, base_url, api_key)
        return

    if len(pairs) == 1 and pairs[0][1] is None:
        pending_base_url[uid] = pairs[0][0]
        await msg.answer("Теперь пришли API ключ для этого base URL.")
        return

    pending_base_url.pop(uid, None)
    if len(pairs) == 1:
        from handlers.history import single
        await single(msg, uid, pairs[0][0], pairs[0][1])
        return

    from handlers.history import start_batch
    await start_batch(msg, uid, pairs)


def parse_pairs(text: str) -> list[tuple[str, str | None]]:
    """Извлекает все пары (base_url, api_key) из сообщения.

    URL и ключи связываются по порядку появления: каждый URL забирает
    ближайший следующий за ним ключ. Возвращает [] если URL нет вовсе,
    [(url, None)] если URL один и ключа нет.
    """
    url_pattern = r'https?://[^\s<>"\'`\]\[{}()]+'
    bare_pattern = r'''(?<![\w@./-])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}\b(?::[0-9]{1,5})?(?:/[^\s<>"'`\]\[{}()]*)?'''
    prefixed = r'(?<![\w-])(?:sk[-_]|nvapi-|vl-|gsk_|AIza|r8_)[A-Za-z0-9_-]{6,}(?![\w-])'
    labeled = r'''(?:api[_ -]?key|ключ|token|bearer)\b[\s"':=«»`]*([A-Za-z0-9_./+=-]{8,})'''
    emoji = r'🔑[\s`"\':]*([A-Za-z0-9_./+=-]{8,})'

    lines = text.splitlines()
    explicit = any(re.search(url_pattern, line, re.I) for line in lines)
    entries: list[tuple[int, int, str, str]] = []
    for idx, line in enumerate(lines):
        masked = re.sub(url_pattern, lambda m: ' ' * len(m.group(0)), line, flags=re.I)
        if not explicit:
            masked = re.sub(bare_pattern, lambda m: ' ' * len(m.group(0)), masked, flags=re.I)
        for m in re.finditer(url_pattern, line, re.I):
            entries.append((idx, m.start(), 'url', m.group(0).rstrip('.,;!')))
        if not explicit:
            for m in re.finditer(bare_pattern, line, re.I):
                entries.append((idx, m.start(), 'url', 'https://' + m.group(0).rstrip('.,;!')))
        for m in re.finditer(prefixed, masked):
            entries.append((idx, m.start(), 'key', m.group(0)))
        for m in re.finditer(labeled, masked, re.I):
            entries.append((idx, m.start(), 'key', m.group(1).rstrip('.,;!')))
        for m in re.finditer(emoji, masked):
            entries.append((idx, m.start(), 'key', m.group(1)))
        if re.search(url_pattern, line, re.I) or (not explicit and re.search(bare_pattern, line, re.I)):
            token = masked.strip().strip('"\'`')
            if re.fullmatch(r'[A-Za-z0-9_./+=-]{16,}', token) and '://' not in token:
                entries.append((idx, len(line), 'key', token))
    url_lines = {e[0] for e in entries if e[2] == 'url'}
    for idx, line in enumerate(lines):
        if idx - 1 in url_lines:
            token = line.strip().strip('"\'`')
            if re.fullmatch(r'[A-Za-z0-9_./+=-]{16,}', token) and '://' not in token:
                entries.append((idx, 0, 'key', token))
    seen: set[tuple[int, str, str]] = set()
    unique: list[tuple[int, int, str, str]] = []
    for entry in entries:
        marker = (entry[0], entry[2], entry[3])
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(entry)
    entries = unique
    entries.sort(key=lambda e: (e[0], e[1]))
    urls = [e for e in entries if e[2] == 'url']
    keys = [e for e in entries if e[2] == 'key']
    if not urls:
        return []
    pairs: list[tuple[str, str | None]] = []
    used: set[int] = set()
    for u in urls:
        match = next((k for k in keys if (k[0], k[1]) > (u[0], u[1]) and id(k) not in used), None)
        if match:
            used.add(id(match))
            pairs.append((u[3], match[3]))
        else:
            pairs.append((u[3], None))
    used_values = {k[3] for k in keys if id(k) in used}
    if any(id(k) not in used and k[3] not in used_values for k in keys):
        raise ValueError('Ключ без URL')
    if len(pairs) == 1 and pairs[0][1] is None:
        return pairs
    if any(k is None for _, k in pairs):
        raise ValueError('URL без ключа')
    return list(dict.fromkeys(pairs))


def parse_input(text: str) -> tuple[str | None, str | None]:
    """Разбирает ввод пользователя.

    Returns:
        (base_url, api_key); любой элемент может быть None.
    """
    url_pattern = r'https?://[^\s<>"\'`\]\[{}()]+'
    urls = {u.rstrip('.,;!') for u in re.findall(url_pattern, text, re.I)}
    remaining = re.sub(url_pattern, ' ', text, flags=re.I)
    bare_pattern = r'''(?<![\w@./-])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}\b(?::[0-9]{1,5})?(?:/[^\s<>"'`\]\[{}()]*)?'''
    if not urls:
        # Bare domains are only a fallback when no explicit https URL was given:
        # pasted reports mention provider names and model IDs that look like domains.
        urls.update('https://' + u.rstrip('.,;!') for u in re.findall(bare_pattern, remaining, re.I))
        remaining = re.sub(bare_pattern, ' ', remaining, flags=re.I)
    keys = set(re.findall(r'(?<![\w-])(?:sk[-_]|nvapi-|vl-|gsk_|AIza|r8_)[A-Za-z0-9_-]{6,}(?![\w-])', remaining))
    labeled = r'''(?:api[_ -]?key|ключ|token|bearer)\b[\s"':=«»`]*([A-Za-z0-9_./+=-]{8,})'''
    keys.update(m.rstrip('.,;!') for m in re.findall(labeled, remaining, re.I))
    keys.update(re.findall(r'🔑[\s`"\':]*([A-Za-z0-9_./+=-]{8,})', remaining))
    if not keys:
        plain = remaining.strip().strip('"\'`')
        if re.fullmatch(r'[A-Za-z0-9_./+=-]{8,}', plain):
            keys.add(plain)
    # Один и тот же URL со слэшем и без — не два разных адреса
    normalized = {u.rstrip('/') for u in urls}
    if len(normalized) > 1 or len(keys) > 1:
        raise ValueError('Ambiguous credentials')
    return next(iter(normalized or urls), None), next(iter(keys), None)


async def run_check(
    msg: Message, uid: int, api_key: str, base_url: str | None
) -> None:
    """Определяет провайдера (или берёт заданный URL), тестирует модели, шлёт отчёт.

    Args:
        msg: Сообщение для ответа (обычное или сообщение из колбэка).
        uid: ID пользователя-владельца чека.
        api_key: API ключ.
        base_url: Явный base URL или None для автодетекта.
    """
    status_msg = await msg.answer("🔍 Определяю провайдера...")

    detection: DetectionResult
    if base_url:
        detection = await fetch_at(base_url, api_key)
    else:
        detection = await detect_by_key(api_key)

    if detection.error or not detection.models:
        detail = detection.error or "Модели не найдены."
        await status_msg.edit_text(f"❌ {detail}")
        return

    sample = min(TEST_SAMPLE_SIZE, len(detection.models))
    await status_msg.edit_text(
        f"✅ Провайдер: <b>{escape(detection.provider_name)}</b>\n"
        f"📦 Моделей: {len(detection.models)}\n"
        f"⏳ Тестирую {sample} моделей..."
    )

    results = await test_models(
        detection.base_url, api_key, detection.models, TEST_SAMPLE_SIZE
    )

    import httpx
    from services.diagnostics import limits_summary

    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
        quota = await limits_summary(client, detection.base_url, api_key)

    text = format_check_result(
        provider_name=detection.provider_name,
        key_type=detection.key_type,
        api_key=api_key,
        base_url=detection.base_url,
        total_models=len(detection.models),
        results=results,
        limits_text=quota,
    )
    keyboard = make_main_keyboard(uid)
    last_check[uid] = {
        "key": api_key,
        "base_url": detection.base_url,
        "models": detection.models,
        "provider": detection.provider_name,
        "report": text,
        "keyboard": keyboard,
    }
    await status_msg.edit_text(text, reply_markup=keyboard)


def make_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Перепроверить", callback_data=f"recheck:{user_id}"
                ),
                InlineKeyboardButton(
                    text="📋 Все модели", callback_data=f"allmodels:{user_id}:0"
                ),
            ],
            [
                InlineKeyboardButton(text="🔬 Проверить модель", callback_data=f"diagpick:{user_id}:0"),
            ],
        ]
    )
