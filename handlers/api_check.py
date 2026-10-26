from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import TEST_SAMPLE_SIZE
from services.formatters import format_check_result
from services.model_tester import test_models
from services.provider_detector import DetectionResult, detect_by_key, fetch_at

router = Router()

# Последний чек пользователя: user_id -> {"key": ..., "base_url": ... | None}
last_check: dict[int, dict] = {}
# Пользователь прислал URL без ключа: user_id -> base_url
pending_base_url: dict[int, str] = {}


@router.message(Command("start"))
async def cmd_start(msg: Message) -> None:
    await msg.answer(
        "👋 <b>API Checker Bot</b>\n\n"
        "Пришли API ключ — определю провайдера, покажу модели и проверю их.\n\n"
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

    base_url, api_key = parse_input(text)

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

    await run_check(msg, uid=uid, api_key=api_key, base_url=base_url)


def parse_input(text: str) -> tuple[str | None, str | None]:
    """Разбирает ввод пользователя.

    Returns:
        (base_url, api_key); любой элемент может быть None.
    """
    tokens = text.split()
    if len(tokens) == 1:
        t = tokens[0]
        if t.lower().startswith(("http://", "https://")):
            return t, None
        return None, t
    url = next((t for t in tokens if t.lower().startswith(("http://", "https://"))), None)
    key = next((t for t in tokens if not t.lower().startswith(("http://", "https://"))), None)
    return url, key


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
        f"✅ Провайдер: <b>{detection.provider_name}</b>\n"
        f"📦 Моделей: {len(detection.models)}\n"
        f"⏳ Тестирую {sample} моделей..."
    )

    results = await test_models(
        detection.base_url, api_key, detection.models, TEST_SAMPLE_SIZE
    )

    text = format_check_result(
        provider_name=detection.provider_name,
        key_type=detection.key_type,
        api_key=api_key,
        base_url=detection.base_url,
        total_models=len(detection.models),
        results=results,
    )
    keyboard = make_main_keyboard(uid)
    last_check[uid] = {
        "key": api_key,
        "base_url": base_url,
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
            ]
        ]
    )
