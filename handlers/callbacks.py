from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import MODELS_PAGE_SIZE
from handlers.api_check import last_check, run_check
from services.formatters import format_models_page

router = Router()


@router.callback_query(F.data.regexp(r"^(diagpick|diagrun|limits):"))
async def handle_diagnostics(callback: CallbackQuery) -> None:
    import httpx
    from services.diagnostics import diagnose, limits

    if not isinstance(callback.message, Message):
        await callback.answer("Сообщение недоступно.")
        return
    try:
        action, owner, number = callback.data.split(":")
        uid, index = int(owner), int(number)
    except (ValueError, AttributeError):
        await callback.answer("Некорректная кнопка.")
        return
    saved = last_check.get(uid)
    if uid != callback.from_user.id or not saved:
        await callback.answer("Чек недоступен. Пришли ключ заново.", show_alert=True)
        return
    if saved.get("busy"):
        await callback.answer("Проверка уже выполняется.")
        return
    await callback.answer()
    models = saved["models"]
    if action == "diagpick":
        page = max(0, min(index, max(0, (len(models) - 1) // 10)))
        rows = [[InlineKeyboardButton(text=m[:50], callback_data=f"diagrun:{uid}:{i}")] for i, m in enumerate(models) if page * 10 <= i < (page + 1) * 10]
        nav = []
        if page:
            nav.append(InlineKeyboardButton(text="◀", callback_data=f"diagpick:{uid}:{page - 1}"))
        if (page + 1) * 10 < len(models):
            nav.append(InlineKeyboardButton(text="▶", callback_data=f"diagpick:{uid}:{page + 1}"))
        nav.append(InlineKeyboardButton(text="К отчёту", callback_data=f"back:{uid}"))
        rows.append(nav)
        await callback.message.edit_text("Выбери модель. Нажатие запускает 3 потенциально платных запроса (до 128 выходных токенов каждый). Это диагностика возможностей, не доказательство подлинности.", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        return
    if action == "diagrun" and not 0 <= index < len(models):
        await callback.message.answer("Модель не найдена.")
        return
    saved["busy"] = True
    try:
        progress = await callback.message.answer("⏳ Получаю результаты…")
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            if action == "limits":
                text = await limits(client, saved["base_url"], saved["key"])
            else:
                text = await diagnose(client, saved["base_url"], saved["key"], models[index])
        await progress.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="К отчёту", callback_data=f"back:{uid}")]]))
    finally:
        saved.pop("busy", None)


@router.callback_query(F.data.startswith("recheck:"))
async def handle_recheck(callback: CallbackQuery) -> None:
    """Повторяет последний чек: заново детект + пробы."""
    assert callback.data is not None

    _, uid_str = callback.data.split(":", 1)
    uid = int(uid_str)
    if callback.from_user.id != uid:
        await callback.answer("Это не твой чек.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Сообщение устарело.", show_alert=True)
        return

    saved = last_check.get(uid)
    if not saved:
        await callback.answer("Нет сохранённого чека — пришли ключ заново.", show_alert=True)
        return

    await callback.answer("Перепроверяю...")
    await run_check(
        callback.message, uid=uid, api_key=saved["key"], base_url=saved.get("base_url")
    )


@router.callback_query(F.data.startswith("allmodels:"))
async def handle_all_models(callback: CallbackQuery) -> None:
    """Пагинированный полный список моделей последнего чека."""
    assert callback.data is not None

    _, uid_str, page_str = callback.data.split(":", 2)
    uid, page = int(uid_str), int(page_str)
    if callback.from_user.id != uid:
        await callback.answer("Это не твой чек.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Сообщение устарело.", show_alert=True)
        return

    saved = last_check.get(uid)
    if not saved or not saved.get("models"):
        await callback.answer("Нет сохранённого списка — пришли ключ заново.", show_alert=True)
        return

    models: list[str] = saved["models"]
    total_pages = max(1, (len(models) + MODELS_PAGE_SIZE - 1) // MODELS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    text = format_models_page(
        provider_name=saved.get("provider", "API"),
        models=models,
        page=page,
        page_size=MODELS_PAGE_SIZE,
    )
    await callback.answer()
    await callback.message.edit_text(
        text, reply_markup=_models_keyboard(uid, page, total_pages)
    )


@router.callback_query(F.data.startswith("back:"))
async def handle_back(callback: CallbackQuery) -> None:
    """Возврат из списка моделей к последнему отчёту."""
    assert callback.data is not None

    _, uid_str = callback.data.split(":", 1)
    uid = int(uid_str)
    if callback.from_user.id != uid:
        await callback.answer("Это не твой чек.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Сообщение устарело.", show_alert=True)
        return

    saved = last_check.get(uid)
    if not saved or not saved.get("report"):
        await callback.answer("Отчёт устарел — пришли ключ заново.", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text(
        saved["report"], reply_markup=saved.get("keyboard")
    )


def _models_keyboard(uid: int, page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=f"allmodels:{uid}:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶", callback_data=f"allmodels:{uid}:{page + 1}"))
    nav.append(InlineKeyboardButton(text="↩ К чеку", callback_data=f"back:{uid}"))
    return InlineKeyboardMarkup(inline_keyboard=[nav])
