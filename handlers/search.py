import re
import secrets
from html import escape
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton as Button, InlineKeyboardMarkup as Keyboard
from handlers.history import vault, edit
from services.jobs import run, active
from services.model_policy import select_models, selected_subset

router = Router()
router.message.filter(F.chat.type == 'private')
router.callback_query.filter(F.message.chat.type == 'private')
sessions = {}


def matches(query, model):
    words = re.findall(r'[a-z]+|[0-9]+', query.lower())
    tokens = re.findall(r'[a-z]+|[0-9]+', model.lower())
    if not words:
        return False
    position = 0
    for word in words:
        try:
            position = tokens.index(word, position) + 1
        except ValueError:
            return False
    return True


@router.message(Command('find'))
async def find(message):
    query = message.text.partition(' ')[2].strip()
    immediate = '--check' in query.split()
    query = ' '.join(w for w in query.split() if w != '--check')
    if not query:
        await message.answer('Пример: /find opus 5.5 или /find opus 5.5 --check (платные запросы).')
        return
    uid = message.from_user.id
    groups = []
    omitted = 0
    for record in vault().list(uid):
        eligible, skipped = select_models(record['result'].get('models', []))
        omitted += sum(matches(query, m) for m in skipped)
        models = [m for m in eligible if matches(query,m)]
        if models:
            groups.append((record['id'], models))
    token = secrets.token_hex(6)
    sessions[token] = {'owner':uid, 'groups':groups, 'running':False, 'stop':False}
    lines = [f'🔎 {escape(query)}: {sum(len(m) for _,m in groups)} совпадений. Поиск в сохранённых каталогах.']
    if omitted:
        lines.append(f'⏭ Совпадений пропущено фильтром версий: {omitted}')
    for rid, models in groups[:8]:
        record = vault().get(uid,rid)
        lines.append(f"#{rid} {escape(record['url'][:100])} · каталог {record['updated']}\n" + '\n'.join(escape(m) for m in models[:4]))
    if len(groups)>8:
        lines.append('В превью первые 8 API; проверка охватит все найденные записи.')
    status = await message.answer('\n\n'.join(lines), reply_markup=Keyboard(inline_keyboard=[[Button(text='Проверить найденные (платно)', callback_data=f'search:{token}')]]) if groups else None)
    if immediate and groups:
        await execute(status, token, uid)


async def execute(message, token, uid):
    session = sessions.get(token)
    if not session or session['owner'] != uid or session['running']:
        return
    groups = []
    for rid, models in session['groups']:
        record = vault().get(uid, rid)
        if record:
            eligible, _ = selected_subset(models, record['result'].get('models', []))
            if eligible:
                groups.append((rid, eligible))
    session['groups'] = groups
    total = sum(len(models) for _,models in groups)
    from config import MAX_MODELS_PER_RUN
    if total > MAX_MODELS_PER_RUN:
        await edit(message, f'Найдено {total} моделей, лимит запуска {MAX_MODELS_PER_RUN}. Уточни поиск.')
        return
    session['running'] = True
    session['stop'] = False
    session['results'] = []
    done = 0
    try:
        for rid, models in session['groups']:
            if session['stop']:
                break
            record = vault().get(uid,rid)
            if not record:
                continue
            async def progress(count, size):
                await edit(message, f'🔎 Проверено {done+count}/{total}', Keyboard(inline_keyboard=[[Button(text='Остановить', callback_data=f'stopsearch:{token}')]]))
            jid = await run(vault(),uid,rid,models,record['result'].get('protocol','chat'),progress)
            job = next(j for j in vault().jobs(uid, rid) if j['id'] == jid)
            for result in job['data']['results']:
                session['results'].append(dict(rid=rid, url=record['url'], model=result['model_id'], ok=result['ok'], status=result.get('status_code'), error=result.get('error_msg', '').replace(record['key'], '[ключ скрыт]')))
            done += len(job['data']['results'])
        text, markup = render_results(session['results'], 0, token, total, session['stop'])
        await edit(message, text, markup)
    finally:
        session['running'] = False


def render_results(results, page, token, total, stopped):
    pages = max(1, (len(results) + 4) // 5)
    page = max(0, min(page, pages - 1))
    good = sum(r['ok'] for r in results)
    lines = [f'🔎 {"Остановлено" if stopped else "Проверка завершена"}: {len(results)}/{total}', f'✅ Отвечают: {good} · ⚠️ Ошибки: {len(results)-good}']
    buttons = []
    for r in results[page*5:page*5+5]:
        status = '✅ отвечает' if r['ok'] else f'⚠️ {"HTTP " + str(r["status"]) if r["status"] else "сеть/таймаут"}'
        lines.append(f'<code>{escape(r["model"])}</code>\n🌐 {escape(r["url"][:200])}\n{status}' + (f' — {escape(r["error"][:180])}' if not r['ok'] and r['error'] else ''))
        if not any(row[0].callback_data == f'h:view:{r["rid"]}' for row in buttons):
            buttons.append([Button(text=f'Открыть API #{r["rid"]}', callback_data=f'h:view:{r["rid"]}')])
    nav = []
    if page:
        nav.append(Button(text='◀', callback_data=f'searchpage:{token}:{page-1}'))
    if page+1 < pages:
        nav.append(Button(text='▶', callback_data=f'searchpage:{token}:{page+1}'))
    if nav:
        buttons.append(nav)
    lines.append(f'Страница {page+1}/{pages}')
    return '\n\n'.join(lines), Keyboard(inline_keyboard=buttons)


@router.callback_query(F.data.startswith('searchpage:'))
async def results_page(call):
    try:
        _, token, raw = call.data.split(':')
        page = int(raw)
    except ValueError:
        await call.answer('Некорректная страница')
        return
    session = sessions.get(token)
    if not session or session['owner'] != call.from_user.id or 'results' not in session:
        await call.answer('Результат устарел. Повтори /find.', show_alert=True)
        return
    await call.answer()
    total = sum(len(models) for _, models in session['groups'])
    text, markup = render_results(session['results'], page, token, total, session['stop'])
    await edit(call.message, text, markup)


@router.callback_query(F.data.startswith('search:'))
async def start(call):
    await call.answer()
    await execute(call.message, call.data.split(':')[1], call.from_user.id)


@router.callback_query(F.data.startswith('stopsearch:'))
async def stop(call):
    session = sessions.get(call.data.split(':')[1])
    if session and session['owner'] == call.from_user.id:
        session['stop'] = True
        for rid,_ in session['groups']:
            event = active.get((call.from_user.id,rid))
            if event:
                event.set()
    await call.answer('Останавливаю')
