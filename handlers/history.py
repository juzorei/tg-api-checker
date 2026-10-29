import asyncio
from pathlib import Path
from html import escape
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton as Button, InlineKeyboardMarkup as Keyboard
from aiogram.exceptions import TelegramBadRequest
from services.vault import Vault
from services.checking import check, report
from services.queued_http import QueuedClient
from services.diagnostics import diagnose
from services.model_policy import select_models

router = Router()
router.message.filter(F.chat.type == 'private')
router.callback_query.filter(F.message.chat.type == 'private')
_vault = None
batches = {}
notes = {}
busy = set()


def vault():
    global _vault
    if _vault is None:
        _vault = Vault(Path(__file__).resolve().parents[1] / 'data')
    return _vault


def keyboard(rid):
    return Keyboard(inline_keyboard=[
        [Button(text='🔎 Проверить все модели', callback_data=f'h:fullask:{rid}')],
        [Button(text='Перепроверить', callback_data=f'h:check:{rid}'), Button(text='Все модели', callback_data=f'h:models:{rid}:0')],
        [Button(text='Диагностика', callback_data=f'h:pick:{rid}:0'), Button(text='Заметка', callback_data=f'h:note:{rid}')],
        [Button(text='Формат API', callback_data=f'h:protocol:{rid}'), Button(text='Продолжить', callback_data=f'h:resume:{rid}')],
        [Button(text='Рабочие', callback_data=f'h:good:{rid}:0'), Button(text='Ошибки', callback_data=f'h:bad:{rid}:0'), Button(text='Непроверенные', callback_data=f'h:untested:{rid}:0')],
        [Button(text='Повтор ошибок', callback_data=f'h:retry:{rid}'), Button(text='TXT', callback_data=f'h:export:{rid}'), Button(text='История', callback_data=f'h:runs:{rid}')],
        [Button(text='Пропущенные', callback_data=f'h:skipped:{rid}:0'), Button(text='Удалить', callback_data=f'h:delete:{rid}')]])


async def edit(message, text, markup=None):
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if 'message is not modified' not in str(exc).lower():
            raise


async def execute(uid, url, key):
    result = await check(url, key)
    return vault().save(uid, url, key, result)


async def single(message, uid, url, key):
    progress = await message.reply('⏳ Проверяю…')
    rid = await execute(uid, url, key)
    await edit(progress, report(vault().get(uid, rid)), keyboard(rid))


@router.message(Command('keys'))
async def keys(message):
    await show_list(message, message.from_user.id, 0, send=True)


async def show_list(message, uid, page, send=False, ids=None):
    records = vault().list(uid) if ids is None else [vault().get(uid, rid) for rid in ids]
    records = [r for r in records if r]
    page = max(0, min(page, max(0, (len(records)-1)//8)))
    lines = [f'📚 История: {len(records)} · страница {page+1}']
    rows = []
    for r in records[page*8:page*8+8]:
        eligible, _ = select_models(r['result'].get('models', []))
        results = [x for x in r['result'].get('results', []) if x['model_id'] in eligible]
        good = sum(x['ok'] for x in results)
        total = len(results)
        label = r['note'] or r['url']
        lines.append(f"#{r['id']} {escape(label[:80])} · {escape(r['key'][:4])}…{escape(r['key'][-4:])} · {good}/{total}")
        rows.append([Button(text=f"Отчёт #{r['id']}", callback_data=f"h:view:{r['id']}")])
    prefix = 'bpage' if ids is not None else 'page'
    nav = []
    if page:
        nav.append(Button(text='◀', callback_data=f'h:{prefix}:{page-1}'))
    if (page+1)*8 < len(records):
        nav.append(Button(text='▶', callback_data=f'h:{prefix}:{page+1}'))
    if nav:
        rows.append(nav)
    markup = Keyboard(inline_keyboard=rows)
    if send:
        await message.answer('\n'.join(lines), reply_markup=markup)
    else:
        await edit(message, '\n'.join(lines), markup)


@router.message(Command('batch'))
async def batch(message):
    uid = message.from_user.id
    if uid in batches and batches[uid].get('running'):
        await message.answer('Пакет выполняется. Сначала отмени его.')
        return
    status = await message.answer('📦 Пришли до 50 пар URL + ключ. Затем «Проверить всё». Запросы могут расходовать баланс.', reply_markup=batch_keyboard())
    batches[uid] = {'message': status, 'items': [], 'running': False, 'cancel': False, 'ids': []}


def batch_keyboard():
    return Keyboard(inline_keyboard=[[Button(text='Проверить всё', callback_data='h:batch:0'), Button(text='Отмена', callback_data='h:cancel:0')]])


@router.message(Command('cancel'))
async def cancel(message):
    uid = message.from_user.id
    notes.pop(uid, None)
    if uid in batches:
        batches[uid]['cancel'] = True
        await edit(batches[uid]['message'], 'Пакет отменён. Текущий запрос может завершиться.')
        if not batches[uid]['running']:
            batches.pop(uid, None)


@router.message(F.text, lambda m: m.from_user.id in notes or m.from_user.id in batches and not batches[m.from_user.id].get('done'))
async def collect(message):
    uid = message.from_user.id
    if uid in notes:
        vault().note(uid, notes.pop(uid), message.text)
        await message.answer('Заметка сохранена.')
        return
    batch = batches[uid]
    if batch['running']:
        return
    from handlers.api_check import parse_input
    try:
        url, key = parse_input(message.text)
    except ValueError:
        url, key = None, None
    if not url or not key:
        await edit(batch['message'], 'Нужна одна пара URL + ключ в каждом сообщении.', batch_keyboard())
        return
    pair = (url.rstrip('/'), key)
    if pair not in batch['items'] and len(batch['items']) < 50:
        batch['items'].append(pair)
    await edit(batch['message'], f"📦 Собрано {len(batch['items'])}/50 уникальных пар. Запросы могут расходовать баланс.", batch_keyboard())


@router.callback_query(F.data.startswith('h:'))
async def callback(call):
    uid = call.from_user.id
    parts = call.data.split(':')
    action = parts[1]
    try:
        rid = int(parts[2])
        page = int(parts[3]) if len(parts)>3 else 0
    except (ValueError, IndexError):
        await call.answer('Некорректная кнопка')
        return
    await call.answer()
    if action in ('page', 'bpage'):
        await show_list(call.message, uid, rid, ids=batches.get(uid, {}).get('ids', []) if action == 'bpage' else None)
        return
    if action in ('batch', 'cancel'):
        batch = batches.get(uid)
        if not batch or batch['message'].message_id != call.message.message_id:
            return
        if action == 'cancel':
            batch['cancel'] = True
            if not batch['running']:
                batches.pop(uid, None)
            await edit(call.message, 'Пакет отменён.')
            return
        if batch['running'] or not batch['items']:
            return
        batch['running'] = True
        try:
            for url, key in batch['items']:
                if batch['cancel']:
                    break
                try:
                    batch['ids'].append(await execute(uid, url, key))
                except Exception:
                    # Unexpected failures must remain visible without logging credentials.
                    await edit(call.message, 'Пакет остановлен из-за внутренней ошибки. Выполненные проверки сохранены.')
                    raise
                if not batch['cancel']:
                    await edit(call.message, f"⏳ Проверено {len(batch['ids'])}/{len(batch['items'])}", Keyboard(inline_keyboard=[[Button(text='Отмена', callback_data='h:cancel:0')]]))
            if not batch['cancel']:
                await show_list(call.message, uid, 0, ids=batch['ids'])
        finally:
            batch['running'] = False
            batch['done'] = True
            batch['items'] = []
        return
    record = vault().get(uid, rid)
    if not record:
        await call.message.answer('Запись недоступна или удалена.')
        return
    if action == 'stop':
        from services.jobs import active
        if (uid,rid) in active:
            active[(uid,rid)].set()
        return
    if action == 'protocol':
        from services.protocols import PROTOCOLS
        await edit(call.message, 'Выбери формат. Base URL должен включать версию API (например /v1 или /v1beta).', Keyboard(inline_keyboard=[[Button(text=p, callback_data=f'h:proto:{rid}:{i}')] for i,p in enumerate(PROTOCOLS)]))
        return
    if action == 'proto':
        from services.protocols import PROTOCOLS
        if 0 <= page < len(PROTOCOLS):
            record['result']['protocol'] = PROTOCOLS[page]
            vault().save(uid, record['url'], record['key'], record['result'])
            await edit(call.message, 'Формат: ' + PROTOCOLS[page], keyboard(rid))
        return
    if action == 'export':
        from aiogram.types import BufferedInputFile
        eligible, _ = select_models(record['result'].get('models', []))
        text = '\n'.join(r['model_id'] for r in record['result'].get('results', []) if r['ok'] and r['model_id'] in eligible)
        await call.message.answer_document(BufferedInputFile(text.encode(), filename='working-models.txt'))
        return
    if action == 'runs':
        rows = vault().jobs(uid,rid)[:10]
        text = '\n'.join(f"{r['created']} · {r['state']} · {len(r['data']['results'])}/{len(r['data']['models'])}" for r in rows)
        await edit(call.message, text or 'История запусков пока пуста.', keyboard(rid))
        return
    if action == 'delete':
        await edit(call.message, 'Удалить запись из истории?', Keyboard(inline_keyboard=[[Button(text='Удалить', callback_data=f'h:confirm:{rid}'), Button(text='Назад', callback_data=f'h:view:{rid}')]]))
    elif action == 'confirm':
        from services.jobs import active
        if (uid, rid) in busy or (uid,rid) in active:
            return
        vault().delete(uid, rid)
        await edit(call.message, 'Запись удалена.')
    elif action == 'note':
        notes[uid] = rid
        await call.message.answer('Пришли заметку (до 120 символов), /cancel для отмены.')
    elif action == 'view':
        await edit(call.message, report(record), keyboard(rid))
    elif action in ('models', 'pick', 'good', 'bad', 'untested', 'skipped'):
        models = record['result'].get('models', [])
        eligible, skipped = select_models(models)
        if action == 'skipped':
            models = list(skipped)
        elif action not in ('models', 'pick'):
            models = eligible
        outcomes = {r['model_id']:r for r in record['result'].get('results', [])}
        if action == 'good':
            models = [m for m in models if outcomes.get(m, {}).get('ok')]
        elif action == 'bad':
            models = [m for m in models if m in outcomes and not outcomes[m]['ok']]
        elif action == 'untested':
            models = [m for m in models if m not in outcomes]
        page = max(0, min(page, max(0, (len(models)-1)//10)))
        chunk = models[page*10:page*10+10]
        rows = []
        if action == 'pick':
            text = 'Выбор запускает 3 потенциально платных запроса. Это не доказательство подлинности.'
            rows = [[Button(text=m[:50], callback_data=f'h:diag:{rid}:{page*10+i}')] for i,m in enumerate(chunk)]
        else:
            outcomes = {r['model_id']: r for r in record['result'].get('results', [])}
            lines = ['📋 Модели и результаты']
            for m in chunk:
                outcome = outcomes.get(m)
                if m in skipped:
                    status = '⏭ ' + skipped[m]
                elif outcome is None:
                    status = 'не проверена'
                elif outcome['ok']:
                    status = '✅ отвечает'
                else:
                    status = '⚠️ ' + str(outcome.get('status_code') or 'сеть/таймаут') + ' · ' + (outcome.get('error_msg') or 'ошибка')[:120]
                lines.append(f'<code>{escape(m)}</code> — {escape(status)}')
            text = '\n'.join(lines)
        nav = []
        if page:
            nav.append(Button(text='◀', callback_data=f'h:{action}:{rid}:{page-1}'))
        if (page+1)*10<len(models):
            nav.append(Button(text='▶', callback_data=f'h:{action}:{rid}:{page+1}'))
        nav.append(Button(text='Назад', callback_data=f'h:view:{rid}'))
        rows.append(nav)
        await edit(call.message, text, Keyboard(inline_keyboard=rows))
    elif action == 'fullask':
        eligible, skipped = select_models(record['result'].get('models', []))
        await edit(call.message, f"Проверить все подходящие модели ({len(eligible)}, пропущено фильтром {len(skipped)} по сохранённому каталогу)? Каталог будет обновлён, фильтр применён заново. Один запрос на модель, до 128 выходных токенов. Проверка может быть платной и занять десятки минут.", Keyboard(inline_keyboard=[[Button(text='Запустить полный чек', callback_data=f'h:full:{rid}'), Button(text='Назад', callback_data=f'h:view:{rid}')]]))
    elif action in ('check', 'diag', 'full', 'resume', 'retry'):
        if (uid, rid) in busy:
            return
        busy.add((uid,rid))
        try:
            await edit(call.message, '⏳ Проверяю…')
            if action in ('check', 'full', 'resume', 'retry'):
                from services.jobs import run
                from services.provider_detector import fetch_at
                import time
                updated = 0.0
                async def progress(done, total):
                    nonlocal updated
                    now = time.monotonic()
                    if done == total or now - updated >= 3:
                        await edit(call.message, f'⏳ Проверка: {done} из {total} · параллельность до 10', Keyboard(inline_keyboard=[[Button(text='Остановить', callback_data=f'h:stop:{rid}')]]))
                        updated = now
                resume = None
                models = record['result'].get('models', [])
                if action == 'full':
                    detection = await fetch_at(record['url'], record['key'])
                    if detection.error:
                        await edit(call.message, escape(detection.error), keyboard(rid))
                        return
                    models = detection.models
                    record['result']['models'] = models
                    vault().save(uid, record['url'], record['key'], record['result'])
                elif action == 'check':
                    models = select_models(models)[0][:20]
                elif action == 'retry':
                    models = [r['model_id'] for r in record['result'].get('results', []) if not r['ok']]
                else:
                    resume = next((j for j in vault().jobs(uid,rid) if j['state'] in ('stopped','interrupted','blocked')), None)
                    if not resume:
                        await edit(call.message, 'Нет прерванной проверки.', keyboard(rid))
                        return
                await run(vault(), uid, rid, models, record['result'].get('protocol','chat'), progress, resume)
                text = report(vault().get(uid, rid))
            else:
                models = record['result'].get('models', [])
                if not 0<=page<len(models):
                    return
                _, skipped = select_models(models)
                if models[page] in skipped:
                    await edit(call.message, '⏭ ' + escape(skipped[models[page]]), keyboard(rid))
                    return
                async with QueuedClient(timeout=30) as client:
                    text = await diagnose(client, record['url'], record['key'], models[page])
            await edit(call.message, text, keyboard(rid))
        except ValueError as exc:
            await edit(call.message, escape(str(exc)), keyboard(rid))
        finally:
            busy.discard((uid,rid))
