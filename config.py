import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.environ["BOT_TOKEN"]
# Telegram ID of the owner: only they can change the proxy from the bot.
ADMIN_ID = int(os.getenv("ADMIN_ID") or 0)

# "claude" or "openai" (any OpenAI-compatible API: OpenRouter, Groq, etc.)
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").strip().lower()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# Several models separated by commas: if one is unavailable, the next is tried.
OPENAI_MODELS = [m.strip() for m in os.getenv("OPENAI_MODEL", "openai/gpt-oss-120b:free").split(",") if m.strip()]
# Comma-separated Telegram user IDs; empty means anyone can use the bot.
ALLOWED_USERS = {int(x) for x in os.getenv("ALLOWED_USERS", "").replace(" ", "").split(",") if x}
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Europe/Moscow"))
AI_DAILY_LIMIT = int(os.getenv("AI_DAILY_LIMIT", "15"))
# Initial proxy for AI requests; the owner can change it in the bot with /proxy.
PROXY_URL = os.getenv("PROXY_URL") or None
DB_PATH = BASE_DIR / "fitbot.db"
