import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from config import MAX_CONCURRENT_TESTS
from services.model_tester import test_models

active = {}


async def run(vault, owner, rid, models, protocol, progress, resume=None):
    from config import MAX_MODELS_PER_RUN
    from services.model_policy import selected_subset
    record = vault.get(owner, rid)
    if not record:
        raise ValueError('Запись недоступна')
    models, skipped = selected_subset(resume['data']['models'] if resume else models, record['result'].get('models', []))
    if len(models) > MAX_MODELS_PER_RUN:
        raise ValueError(f'Превышен предел {MAX_MODELS_PER_RUN} моделей за запуск')
    identity = (owner, rid)
    if identity in active:
        raise ValueError('Проверка уже выполняется')
    stop = asyncio.Event()
    active[identity] = stop
    payload = dict(resume['data']) if resume else {'models': models, 'results': [], 'protocol': protocol}
    payload['models'] = models
    payload['results'] = [r for r in payload['results'] if r['model_id'] in models]
    payload['skipped'] = skipped
    jid = resume['id'] if resume else vault.job_create(owner, rid, payload)
    done = {r['model_id'] for r in payload['results']}
    pending = [m for m in payload['models'] if m not in done]
    state = 'running'
    width = MAX_CONCURRENT_TESTS
    try:
        await progress(len(done), len(payload['models']))
        while pending and not stop.is_set():
            chunk, pending = pending[:width], pending[width:]
            async def probe(model):
                result = (await test_models(record['url'], record['key'], [model], 1, protocol=payload['protocol']))[0]
                row = asdict(result)
                row['checked_at'] = datetime.now(timezone.utc).isoformat()
                payload['results'].append(row)
                vault.job_save(owner, jid, 'running', payload)
                return result
            results = await asyncio.gather(*(probe(m) for m in chunk))
            await progress(len(payload['results']), len(payload['models']))
            if any(r.status_code == 429 or r.status_code == 423 and any(s in r.error_msg.lower() for s in ('concurrent', 'одновременн')) for r in results):
                width = 1
                if pending:
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        pass
        if state == 'running':
            state = 'stopped' if stop.is_set() else 'completed'
    finally:
        if state == 'running':
            state = 'interrupted'
        vault.job_save(owner, jid, state, payload)
        current = vault.get(owner, rid)
        if current:
            result = current['result']
            indexed = {r['model_id']: r for r in result.get('results', [])}
            indexed.update({r['model_id']: r for r in payload['results']})
            result['results'] = list(indexed.values())
            result['job_state'] = state
            result['skipped'] = skipped
            vault.save(owner, current['url'], current['key'], result)
        active.pop(identity, None)
    return jid
