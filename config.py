import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# Проверяются по порядку, первый эндпоинт с /models == 200 побеждает
KNOWN_PROVIDERS: list[tuple[str, str]] = [
    ("https://api.openai.com/v1", "OpenAI"),
    ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DashScope (Alibaba)"),
    ("https://api.deepseek.com/v1", "DeepSeek"),
    ("https://api.moonshot.cn/v1", "Moonshot AI"),
    ("https://api.siliconflow.cn/v1", "SiliconFlow"),
    ("https://openrouter.ai/api/v1", "OpenRouter"),
    ("https://api.groq.com/openai/v1", "Groq"),
    ("https://api.together.xyz/v1", "Together AI"),
    ("https://api.mistral.ai/v1", "Mistral AI"),
    ("https://api.lingyiwanwu.com/v1", "01.AI (Yi)"),
    ("https://open.bigmodel.cn/api/paas/v4", "ZhipuAI"),
    ("https://ark.cn-beijing.volces.com/api/v3", "ByteDance (Ark)"),
    ("https://api.cohere.ai/compatibility/v1", "Cohere"),
    ("https://api.x.ai/v1", "xAI"),
]

TEST_SAMPLE_SIZE: int = 20   # сколько моделей проверять чатом
TEST_TIMEOUT: float = 15.0   # сек на один chat completion
DETECT_TIMEOUT: float = 8.0  # сек на пробу одного эндпоинта
MAX_CONCURRENT_TESTS: int = 10

MODELS_PAGE_SIZE: int = 60   # моделей на страницу в "Все модели"
FAILING_LINES_LIMIT: int = 12  # строк с провалившимися моделями в отчёте
