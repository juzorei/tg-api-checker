# tg-api-checker

<div align="center">

**Telegram bot that tells you which models behind an OpenAI-compatible proxy actually respond — before you waste tokens on them.**

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![aiogram 3](https://img.shields.io/badge/aiogram-3.x-2CA5E4?logo=telegram&logoColor=white)](https://aiogram.dev/)
[![Tests](https://img.shields.io/badge/tests-65%20passing-brightgreen)](#tests)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[Features](#features) · [Quick start](#quick-start) · [How it works](#how-it-works) · [Security](#security) · [README по-русски](README.ru.md)

</div>

---

Have a stack of API keys from different LLM gateways and aggregators? The catalog says 300+ models — but which ones actually answer, which error out, and which are stale relics you'd never call anyway? **tg-api-checker** probes every model (or a sample), reports exact HTTP errors and rate-limit causes, keeps an encrypted history of your keys, and lets you re-run or search across everything you've ever checked — right in Telegram.

```
🔑 API check — example-gateway.com
🌐 Base URL: https://example-gateway.com/v1
🔑 Key: sk-...

💳 Limits: not exposed by server

📦 Responding models (14):
`openai/gpt-6-astra`  `anthropic/claude-opus-5.5`  `google/gemini-4-argon` ...

💬 Respond: 14 of 20 tested
⏭ Skipped by version filter: 87 (reasons in the «Skipped» view)

⚠️ Error breakdown:
• 4 × HTTP 403: this model must be selected via a Claude/Codex agent
• 2 × HTTP 423: too many concurrent requests
```

## Features

- **Paste anything** — a bare key, `URL + key`, a whole forwarded report from another checker. The parser extracts the pair; if a message contains two *different* endpoints or keys, the bot asks instead of sending your key to the wrong server. Schemeless URLs (`llmgateway.example/v1`) work.
- **Model probes with real errors** — a 200 with empty text is not success; 401/403/423/429 each get a human-readable reason plus the server's own error message (key material redacted).
- **Version gate before spending anything** — Claude 5+, GPT 6+, Gemini 4+, GLM 5.3.x only; MiniMax/Kimi resolve to the newest version present in each catalog. Customizable in one file. Skipped models are listed with reasons, never silently dropped.
- **Encrypted key history** — keys and results stored in SQLite, encrypted with Fernet; the key `vault.key` lives separately from the DB. Recheck any key in one tap, no re-pasting.
- **Full catalog scans with stop/resume** — every probe is persisted; interrupt a 300-model scan, resume later from where it stopped (after a restart too — manually, never auto-spending).
- **Adaptive throttling** — starts at 10 concurrent requests; the first 429/423 with a concurrency hint drops to one-at-a-time with a 5s pause. One model's failure never halts the rest of the catalog.
- **Multi-protocol** — Chat Completions, Responses, Anthropic Messages, Gemini generateContent. The bot probes with one model to pick the working format; auth.quota errors never trigger protocol thrashing. Native Anthropic/Gemini model catalogs are used first on their hosts.
- **Archive search** — `/find opus 5.5` across every catalog you've ever saved; append `--check` to probe just the matches. Results render in the same message, with jump buttons per API.
- **Batches** — up to 50 pairs, one live status message, per-key reports one tap away.
- **Honest telemetry** — DeepSeek balance and OpenRouter quota shown when the provider exposes them; otherwise the report says «not exposed», never invents numbers, and never claims to identify the real model behind a proxy.

## Quick start

```bash
git clone https://github.com/juzorei/tg-api-checker.git
cd tg-api-checker
python -m venv .venv && .venv\Scripts\activate   # Windows (Unix: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env                            # put your BOT_TOKEN from @BotFather inside
python bot.py
```

Send the bot a base URL and a key. That's it — the report arrives as a reply to your message.

Optional env vars: `MAX_CONCURRENT_TESTS` (1–20, default 10), `MAX_MODELS_PER_RUN` (500), `MAX_OUTPUT_TOKENS` (128), `ALLOWED_USER_IDS` (comma-separated allowlist).

## Commands

| Command | What it does |
|---|---|
| *(paste URL + key)* | Full check: catalog, sample probes, limits — as a reply to your message |
| `/keys` | Encrypted key history: recheck, full scan, filters, retry errors, TXT export, notes, delete |
| `/batch` | Collect up to 50 pairs, then run them with one progress message |
| `/find <query> [--check]` | Search all saved catalogs; `--check` probes the matches |
| `/cancel` | Cancel input, a batch, or a running check (in-flight request may finish) |

## How it works

1. **Catalog** — OpenAI-compatible `/models` (or native Anthropic/Gemini listing on their hosts).
2. **Version gate** — your rules run *before* any paid request; skipped models saved with reasons.
3. **Protocol probe** — one cheap request picks the working format; persisted per key.
4. **Probes** — batches of up to 10 concurrent requests, adaptively throttled on 429/423; every result persisted incrementally.
5. **Report** — responding models as tappable code blocks, error breakdown grouped by cause, limits in one line.

## Security

- Keys are **encrypted at rest** (Fernet) and never placed in `callback_data`, logs, or error messages — server error text is scrubbed of your key before display.
- The transport layer blocks loopback/private/link-local IPs at connect time (checked at DNS resolution, not just at parse), follows no redirects, and ignores proxy env vars — so a hostile endpoint can't bounce your key to an internal address.
- History is strictly per-Telegram-ID; records of other users are not accessible.
- ⚠️ Reports show keys in full for tappable copying — **don't forward reports**. Deletion from history doesn't scrub old Telegram messages.
- Deleting a record removes it from the active vault only, not from backups you've made.

## Project layout

```
bot.py                       # entry point (aiogram 3 polling)
handlers/api_check.py        # input parsing + reports
handlers/history.py          # /keys, jobs, batches
handlers/search.py           # /find
services/provider_detector.py  # catalog fetch (OpenAI-compatible + native)
services/protocols.py        # chat/responses/anthropic/gemini adapters
services/protocol_detect.py  # one-probe format autodetection
services/model_tester.py     # model probes
services/model_policy.py     # version gate rules
services/jobs.py             # resumable scan jobs, adaptive throttling
services/vault.py            # encrypted SQLite storage
services/network_safety.py   # SSRF-safe transport
```

## Tests

```bash
python -m unittest discover -s tests
```

65 tests covering parsing, protocol adapters, version policy, job persistence/resume, throttling, encryption, and SSRF guards.

## License

[MIT](LICENSE) © 2026 juzorei

---

<div align="center">

**[README по-русски](README.ru.md)**

</div>
