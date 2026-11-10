from urllib.parse import urlsplit

# Хосты, которые заведомо не являются OpenAI-совместимыми LLM API.
# Ключи для них не проверяются и не сохраняются в историю.
_NON_LLM = {
    'api.stripe.com': 'Stripe — платёжный API',
    'api.github.com': 'GitHub API',
    'api.telegram.org': 'Telegram Bot API',
    'api-inference.huggingface.co': 'Hugging Face Inference API (не OpenAI-совместимый)',
}


def non_llm_reason(url):
    """Возвращает причину, если хост заведомо не LLM API, иначе None."""
    host = (urlsplit(url).hostname or '').lower().rstrip('.')
    for known, reason in _NON_LLM.items():
        if host == known or host.endswith('.' + known):
            return reason
    return None
