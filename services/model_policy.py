import re


_VERSION = r'(\d{1,2}(?:(?:[._]|-)(?!\d{3})\d{1,2})*)(?!\d)'
_PATTERNS = (
    ('Llama', r'^llama'),
    ('Grok', r'^grok'),
    ('Qwen', rf'^qwen(?:[-_]?v?{_VERSION})?'),
    ('DeepSeek', rf'^deepseek(?:[-_]?v{_VERSION})?'),
    ('Claude', rf'^(?:claude[-_])?(?:opus|sonnet|haiku)[-_]?{_VERSION}'),
    ('Claude', rf'^claude[-_]?{_VERSION}'),
    ('GPT', rf'^gpt[-_]?{_VERSION}'),
    ('Gemini', rf'^gemini[-_]?{_VERSION}'),
    ('GLM', rf'^glm[-_]?{_VERSION}'),
    ('MiniMax', rf'^minimax[-_]?m[-_]?{_VERSION}'),
    ('Kimi', rf'^kimi[-_]?k[-_]?{_VERSION}'),
)

# Не-чатовые модели: генерация/анализ аудио, изображений, видео, эмбеддинги и т.п.
_NONCHAT = ('embedding', 'embed', 'rerank', 'tts', 'audio', 'speech', 'voice',
            'whisper', 'dall', 'image', 'imagen', 'sora', 'video', 'veo',
            'moderation', 'guard', 'realtime', 'live')

# Семейства, исключённые полностью (Llama/Grok), и минимальные версии остальных.
_EXCLUDE_ALL = {'Llama', 'Grok'}
_MINIMUM = {'Claude': 5, 'GPT': 6, 'Gemini': 4, 'Qwen': 4, 'DeepSeek': 4}
# Qwen/DeepSeek без распознанной версии (chat, reasoner, r1, latest) — отрезать;
# Claude/GPT/Gemini без версии (claude-latest) — сохранить.
_FULL_CUT_NO_VERSION = {'Qwen', 'DeepSeek'}


def _purpose_reason(name):
    tokens = set(re.split(r'[-_/.: ]+', name.lower()))
    for token in _NONCHAT:
        if token in tokens:
            return f'не-чатовая модель: {token}'
    return None


def family_version(model):
    name = model.rsplit('/', 1)[-1].lower()
    for family, pattern in _PATTERNS:
        match = re.match(pattern, name)
        if match:
            if match.re.groups == 0 or match.group(1) is None:
                return family, ()
            version = tuple(int(part) for part in re.split(r'[._-]', match.group(1)))
            return family, version + (0,) * (3 - len(version))
    return None, ()


def select_models(models):
    """Разделяет каталог на подходящие и пропущенные с причинами.

    Порядок правил: назначение модели (не-чатовые) → полное исключение
    семейства → минимальная версия → ветка GLM → новейшая версия MiniMax/Kimi.
    Неизвестные семейства и нераспознанные версии сохраняются.
    """
    models = list(dict.fromkeys(models))
    purpose = {model: _purpose_reason(model) for model in models}
    parsed = {model: family_version(model) for model in models}
    latest = {}
    for family, version in parsed.values():
        if family in ('MiniMax', 'Kimi'):
            latest[family] = max(latest.get(family, ()), version)
    allowed, skipped = [], {}
    for model in models:
        if purpose[model]:
            skipped[model] = purpose[model]
            continue
        family, version = parsed[model]
        reason = None
        if family in _EXCLUDE_ALL:
            reason = f'{family}: семейство исключено'
        elif family == 'GLM' and version[:2] != (5, 3):
            reason = 'GLM: разрешена только ветка 5.3'
        else:
            minimum = _MINIMUM.get(family)
            if minimum is not None and version:
                if version[0] < minimum:
                    reason = f'{family}: версия ниже {minimum}'
            elif minimum is not None and family in _FULL_CUT_NO_VERSION:
                reason = f'{family}: только версии {minimum}+; версия не распознана'
            elif family in latest and version < latest[family]:
                label = '.'.join(map(str, latest[family][:2]))
                reason = f'{family}: в каталоге есть более новая версия {label}'
        if reason:
            skipped[model] = reason
        else:
            allowed.append(model)
    return allowed, skipped


def selected_subset(models, catalog):
    _, skipped = select_models(list(catalog) + list(models))
    return [m for m in dict.fromkeys(models) if m not in skipped], skipped
