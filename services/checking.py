from dataclasses import asdict
from services.provider_detector import fetch_at
from services.model_tester import test_models, ModelTestResult
from services.diagnostics import limits_summary
from services.formatters import format_check_result
from services.queued_http import QueuedClient
from config import TEST_SAMPLE_SIZE, MAX_CONCURRENT_TESTS, DETECT_TIMEOUT
from html import escape
from services.model_policy import select_models

from asyncio import sleep  # тестируемая точка для патчей


async def check(url, key, full=False, progress=None, protocol='chat'):
    detection = await fetch_at(url, key)
    if detection.error or not detection.models:
        return {'error': detection.error or 'Каталог пуст', 'models': [], 'results': [], 'protocol': protocol}
    detection.models = list(dict.fromkeys(detection.models))
    eligible, skipped = select_models(detection.models)
    probe = next(iter(eligible), None)
    if probe:
        async with QueuedClient(timeout=DETECT_TIMEOUT) as client:
            from services.protocol_detect import detect_protocol
            protocol = await detect_protocol(client, detection.base_url, key, probe, preferred=protocol)
    if full:
        results = []
        if progress:
            await progress(0, len(eligible))
        for start in range(0, len(eligible), MAX_CONCURRENT_TESTS):
            chunk = eligible[start:start + MAX_CONCURRENT_TESTS]
            results.extend(await test_models(detection.base_url, key, chunk, len(chunk), protocol=protocol))
            if progress:
                await progress(len(results), len(eligible))
    else:
        sample = eligible[:TEST_SAMPLE_SIZE]
        results = []
        width = min(MAX_CONCURRENT_TESTS, len(sample)) if sample else 0
        position = 0
        while position < len(sample):
            chunk = sample[position:position + width]
            position += len(chunk)
            batch = await test_models(detection.base_url, key, chunk, len(chunk), protocol=protocol)
            results.extend(batch)
            if any(r.status_code in (401, 403) or 'insufficient_quota' in r.error_msg for r in batch):
                results.extend(await test_models(detection.base_url, key, sample[position:], len(sample) - position, protocol=protocol))
                break
            if any(r.status_code == 429 or r.status_code == 423 and 'concurrent' in r.error_msg.lower() for r in batch):
                width = 1
                await sleep(5)
    async with QueuedClient(timeout=8) as client:
        quota = await limits_summary(client, url, key)
    return {'models': detection.models, 'skipped': skipped, 'results': [asdict(r) for r in results], 'provider': detection.provider_name, 'quota': quota, 'protocol': protocol}


def report(record):
    result = record['result']
    key = record['key']
    if result.get('error'):
        return f"🌐 <code>{escape(record['url'])}</code>\n🔑 <code>{escape(key)}</code>\n⚠️ {escape(result['error'])}"
    eligible, skipped = select_models(result['models'])
    results = [r for r in result['results'] if r['model_id'] in eligible]
    return format_check_result(result['provider'], '', key, record['url'], len(eligible) + len(skipped), [ModelTestResult(**{k:v for k,v in r.items() if k in ModelTestResult.__dataclass_fields__}) for r in results], result.get('quota', 'не раскрыты'), skipped_count=len(skipped))
