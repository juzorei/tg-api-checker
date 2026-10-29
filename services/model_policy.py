import re


_VERSION = r'(\d{1,2}(?:(?:[._]|-)(?!\d{3})\d{1,2})*)(?!\d)'
_PATTERNS = (
    ('Claude', rf'^(?:claude[-_])?(?:opus|sonnet|haiku)[-_]?{_VERSION}'),
    ('Claude', rf'^claude[-_]?{_VERSION}'),
    ('GPT', rf'^gpt[-_]?{_VERSION}'),
    ('Gemini', rf'^gemini[-_]?{_VERSION}'),
    ('GLM', rf'^glm[-_]?{_VERSION}'),
    ('MiniMax', rf'^minimax[-_]?m[-_]?{_VERSION}'),
    ('Kimi', rf'^kimi[-_]?k[-_]?{_VERSION}'),
)


def family_version(model):
    name = model.rsplit('/', 1)[-1].lower()
    for family, pattern in _PATTERNS:
        match = re.match(pattern, name)
        if match:
            version = tuple(int(part) for part in re.split(r'[._-]', match.group(1)))
            return family, version + (0,) * (3 - len(version))
    return None, ()


def select_models(models):
    """Keep unknown versions; filter only explicitly recognised family/version IDs."""
    models = list(dict.fromkeys(models))
    parsed = {model: family_version(model) for model in models}
    latest = {}
    for family, version in parsed.values():
        if family in ('MiniMax', 'Kimi'):
            latest[family] = max(latest.get(family, ()), version)
    allowed, skipped = [], {}
    for model in models:
        family, version = parsed[model]
        reason = None
        minimum = {'Claude': 5, 'GPT': 6, 'Gemini': 4}.get(family)
        if minimum and version[0] < minimum:
            reason = f'{family}: версия ниже {minimum}'
        elif family == 'GLM' and version[:2] != (5, 3):
            reason = 'GLM: разрешена только ветка 5.3'
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
