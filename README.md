# tg-api-checker

Telegram-бот проверки API ключей OpenAI-совместимых провайдеров.
Принимает ключ, сам определяет провайдера (перебирает 14 известных
эндпоинтов), показывает список моделей и проверяет выборку из 20
через chat completions. Отчёт в стиле ApiCheck: тип ключа, кто
отвечает, коды ошибок по каждой модели, рабочий эндпоинт.

## Установка

```bash
git clone https://github.com/juzorei/tg-api-checker.git
cd tg-api-checker
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env          # и вписать BOT_TOKEN
```

Токен бота создаётся у [@BotFather](https://t.me/BotFather).

## Запуск

```bash
python bot.py
```

## Использование

Три формата ввода:

1. Просто ключ — `sk-...`: бот сам найдёт провайдера
2. Base URL + ключ одной строкой — `https://api.example.com/v1 sk-...`: проверка напрямую на этом URL
3. Сначала URL, потом ключ следующим сообщением

Кнопки под отчётом:

- **🔄 Перепроверить** — повторить чек тем же ключом
- **📋 Все модели** — полный список моделей с пагинацией
- **↩ К чеку** — вернуться к отчёту из списка

## Поддерживаемые провайдеры (автодетект)

OpenAI, DashScope (Alibaba), DeepSeek, Moonshot, SiliconFlow,
OpenRouter, Groq, Together AI, Mistral, 01.AI, ZhipuAI,
ByteDance Ark, Cohere, xAI. Любой другой — через формат 2.

## Структура

```
bot.py                       # точка входа (aiogram 3, polling)
config.py                    # токен, список провайдеров, таймауты
handlers/api_check.py        # разбор ввода, запуск чека
handlers/callbacks.py        # кнопки: перепроверка, все модели, назад
services/provider_detector.py  # автодетект провайдера по ключу
services/model_tester.py     # параллельные пробы chat completions
services/formatters.py       # HTML-отчёты
```
