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

    try:
        base_url, api_key = parse_input(text)
    except ValueError:
        pending_base_url.pop(uid, None)
        await msg.answer("Найдено несколько адресов или ключей. Пришли одну пару URL + ключ.")
        return

    # URL без ключа — запоминаем и ждём ключ следующим сообщением
    if base_url and not api_key:
        pending_base_url[uid] = base_url
        await msg.answer("Теперь пришли API ключ для этого base URL.")
        return

    # Ключ без URL — подхватываем запомненный, если был
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

    if msg.chat.type != 'private':
        return
    if not base_url:
        await msg.answer('Пришли base URL вместе с ключом.')
        return
    from handlers.history import single
    await single(msg, uid, base_url, api_key)


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
