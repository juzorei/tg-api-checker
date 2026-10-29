from urllib.parse import quote

PROTOCOLS = ('chat', 'responses', 'anthropic', 'gemini')


def request_spec(base, key, model, protocol, tokens=128):
    base = base.rstrip('/')
    headers = {'Authorization': f'Bearer {key}'}
    if protocol == 'chat':
        return base + '/chat/completions', headers, {'model': model, 'messages': [{'role': 'user', 'content': 'Reply briefly: OK'}], 'max_tokens': tokens}
    if protocol == 'responses':
        return base + '/responses', headers, {'model': model, 'input': 'Reply briefly: OK', 'max_output_tokens': tokens}
    if protocol == 'anthropic':
        return base + '/messages', {'x-api-key': key, 'anthropic-version': '2023-06-01'}, {'model': model, 'messages': [{'role': 'user', 'content': 'Reply briefly: OK'}], 'max_tokens': tokens}
    if protocol == 'gemini':
        name = model.removeprefix('models/')
        return base + '/models/' + quote(name, safe='') + ':generateContent', {'x-goog-api-key': key}, {'contents': [{'parts': [{'text': 'Reply briefly: OK'}]}], 'generationConfig': {'maxOutputTokens': tokens}}
    raise ValueError('Unknown API protocol')


def response_text(body, protocol):
    if protocol == 'chat':
        text = body['choices'][0]['message'].get('content')
        return text if isinstance(text, str) else ''
    if protocol == 'responses':
        if body.get('status') in ('failed', 'cancelled', 'queued', 'in_progress'):
            return ''
        return ''.join(part.get('text', '') for item in body.get('output', []) if item.get('type') == 'message' for part in item.get('content', []) if part.get('type') == 'output_text')
    if protocol == 'anthropic':
        return ''.join(part.get('text', '') for part in body.get('content', []) if part.get('type') == 'text')
    if protocol == 'gemini':
        return ''.join(part.get('text', '') for candidate in body.get('candidates', []) for part in candidate.get('content', {}).get('parts', []) if not part.get('thought'))
    raise ValueError('Unknown API protocol')
