import json
import logging
import re

import anthropic
import openai
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

import config
import db

log = logging.getLogger(__name__)

# If Claude declines a request, the API retries it on a fallback model within the same call.
FALLBACK = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}


class AIError(Exception):
    """Failure with a message that is safe to show to the user."""


class Exercise(BaseModel):
    name: str
    sets: int
    reps: str
    rest_sec: int
    weight_tip: str
    note: str


class Day(BaseModel):
    title: str
    warmup: str
    exercises: list[Exercise]
    cooldown: str


class Plan(BaseModel):
    summary: str
    days: list[Day]
    progression: str
    nutrition_tips: list[str]
    safety_note: str


PLAN_SYSTEM = """Ты — опытный персональный тренер. Составь недельную программу тренировок под анкету клиента.

Правила:
- Тренировочных дней ровно столько, сколько указано в анкете. Каждая тренировка вместе с разминкой укладывается в указанное время.
- Используй только доступный клиенту инвентарь.
- Учитывай уровень: новичкам — базовые движения и простые тренажёры, без сложной техники.
- Если указаны травмы или ограничения, не нагружай проблемную зону, подбери щадящие замены, а в safety_note одной-двумя фразами посоветуй согласовать нагрузку с врачом. Если ограничений нет, safety_note — пустая строка.
- title дня — вида «День 1 — Верх тела».
- name — общепринятое русское название упражнения без пояснений (например «Жим штанги лёжа»): по нему клиент ведёт дневник.
- reps — диапазон повторов вида «8-12», для статики — «30-45 сек», для упражнений на одну сторону — «10-12 на каждую сторону».
- weight_tip — как подобрать вес по ощущениям (максимумы клиента неизвестны), для упражнений без веса — как усложнить или упростить. Одна фраза.
- note — один короткий совет по технике или пустая строка.
- warmup и cooldown — по одной-две фразы.
- progression — как повышать нагрузку от недели к неделе, 2-4 предложения.
- nutrition_tips — 4-6 практичных советов по питанию под цель и рассчитанную норму, без меню на день.
- summary — 2-3 предложения: логика программы и почему она подходит клиенту.
- Пиши кратко, по-русски, без markdown."""

# OpenAI-compatible models don't all support structured outputs, so the schema goes into the prompt.
PLAN_JSON_INSTRUCTION = ("\n\nОтветь только JSON-объектом по этой JSON-схеме, без пояснений и без ```:\n"
                         + json.dumps(Plan.model_json_schema(), ensure_ascii=False))

ANALYZE_SYSTEM = """Ты — опытный персональный тренер. Клиент прислал свою программу тренировок. Оцени её с учётом его анкеты: что хорошо и что стоит поменять (баланс мышечных групп, объём, частота, восстановление, соответствие цели и уровню, безопасность при ограничениях). Предлагай конкретные замены.

Отвечай по-русски простым текстом без markdown: можно эмодзи и списки через «•». Не длиннее 2500 символов. Если присланное не похоже на программу тренировок, скажи об этом и попроси прислать план."""

TECHNIQUE_SYSTEM = """Ты — тренер. Кратко объясни технику упражнения: какие мышцы работают, исходное положение, выполнение, дыхание, 3 частые ошибки.

Отвечай по-русски простым текстом без markdown: можно эмодзи и списки через «•». Не длиннее 1200 символов. Если это не упражнение, скажи об этом одной фразой."""


# ---------- client and proxy ----------

_clients: dict[str, AsyncAnthropic | AsyncOpenAI] = {}


def current_proxy() -> str | None:
    """Proxy set by the owner in the bot; falls back to PROXY_URL from .env."""
    saved = db.get_setting("proxy")
    return config.PROXY_URL if saved is None else saved or None


def provider_name() -> str:
    if config.AI_PROVIDER == "claude":
        return f"Claude ({config.CLAUDE_MODEL})"
    return f"{config.OPENAI_BASE_URL} ({', '.join(config.OPENAI_MODELS)})"


def _client() -> AsyncAnthropic | AsyncOpenAI:
    if "main" not in _clients:
        proxy = current_proxy()
        try:
            if config.AI_PROVIDER == "claude":
                options = {"max_retries": 3}
                if proxy:
                    options["http_client"] = anthropic.DefaultAsyncHttpxClient(proxy=proxy)
                _clients["main"] = AsyncAnthropic(**options)
            else:
                options = {"api_key": config.OPENAI_API_KEY, "base_url": config.OPENAI_BASE_URL, "max_retries": 2}
                if proxy:
                    options["http_client"] = openai.DefaultAsyncHttpxClient(proxy=proxy)
                _clients["main"] = AsyncOpenAI(**options)
        except Exception:
            log.exception("Can't create AI client with proxy %r", proxy)
            raise AIError("Не получилось настроить подключение к нейросети. Напиши владельцу бота.")
    return _clients["main"]


async def reset_client():
    """Close the cached client so the next request uses the new proxy."""
    for client in _clients.values():
        await client.close()
    _clients.clear()


def _translate(e: Exception) -> AIError:
    if isinstance(e, (anthropic.AuthenticationError, openai.AuthenticationError)):
        log.error("AI API: invalid API key")
        return AIError("Нейросеть не настроена: неверный ключ API. Напиши владельцу бота.")
    if isinstance(e, (anthropic.PermissionDeniedError, openai.PermissionDeniedError)):
        log.error("AI API: permission denied: %s", e)
        return AIError("Нейросеть недоступна с этого сервера. Напиши владельцу бота.")
    if isinstance(e, (anthropic.RateLimitError, openai.RateLimitError)):
        return AIError("Слишком много запросов к нейросети, попробуй через минуту.")
    if isinstance(e, (anthropic.APIStatusError, openai.APIStatusError)):
        log.error("AI API error %s: %s", e.status_code, e.message)
        return AIError("Нейросеть сейчас недоступна, попробуй чуть позже.")
    log.error("AI API: connection error: %r", e)
    return AIError("Не получилось связаться с нейросетью, попробуй чуть позже.")


def _error_detail(e: Exception) -> str:
    if isinstance(e, (anthropic.APIStatusError, openai.APIStatusError)):
        body = e.body.get("error", e.body) if isinstance(e.body, dict) else e.body
        message = body.get("message", body) if isinstance(body, dict) else body
        return f"{e.status_code}: {message}"[:200]
    return type(e).__name__


async def check_models() -> list[tuple[str, bool, str]]:
    """Send a tiny real request to every configured model: (model, works, detail)."""
    content = "Ответь одним словом: работаю"
    if config.AI_PROVIDER == "claude":
        try:
            response = await _client().messages.create(model=config.CLAUDE_MODEL, max_tokens=1000,
                                                       output_config={"effort": "low"},
                                                       messages=[{"role": "user", "content": content}])
        except anthropic.APIError as e:
            return [(config.CLAUDE_MODEL, False, _error_detail(e))]
        return [(config.CLAUDE_MODEL, response.stop_reason != "refusal", response.stop_reason)]

    results = []
    for model in config.OPENAI_MODELS:
        try:
            response = await _client().chat.completions.create(
                model=model, max_tokens=1000, messages=[{"role": "user", "content": content}])
        except openai.APIError as e:
            results.append((model, False, _error_detail(e)))
            continue
        answered = bool(response.choices and response.choices[0].message.content)
        # openrouter/free reports which model actually answered.
        results.append((model, answered, response.model if answered else "пустой ответ"))
    return results


# ---------- Claude ----------

async def _claude(method, **kwargs):
    try:
        response = await method(model=config.CLAUDE_MODEL, max_tokens=16000, **FALLBACK, **kwargs)
    except anthropic.APIError as e:
        raise _translate(e) from e
    if response.stop_reason == "refusal":
        raise AIError("Нейросеть не стала отвечать на этот запрос.")
    if response.stop_reason == "max_tokens":
        raise AIError("Ответ получился слишком длинным, попробуй ещё раз.")
    return response


# ---------- OpenAI-compatible ----------

async def _chat(system: str, content: str, max_tokens: int = 8000) -> str:
    last_error: Exception | None = None
    for model in config.OPENAI_MODELS:
        try:
            response = await _client().chat.completions.create(
                model=model, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": content}])
        except (openai.RateLimitError, openai.NotFoundError, openai.InternalServerError) as e:
            # Free models are often overloaded or get removed: move on to the next one.
            log.warning("Model %s unavailable (check OPENAI_MODEL): %s", model, e)
            last_error = e
            continue
        except openai.APIError as e:
            raise _translate(e) from e
        choice = response.choices[0] if response.choices else None
        if choice is None or not choice.message.content:
            log.warning("Model %s returned an empty answer", model)
            continue
        if choice.finish_reason == "length":
            raise AIError("Ответ получился слишком длинным, попробуй ещё раз.")
        # Some reasoning models put their thoughts into the answer.
        return re.sub(r"<think>.*?</think>", "", choice.message.content, flags=re.S).strip()
    if last_error is not None:
        raise _translate(last_error)
    raise AIError("Нейросеть вернула пустой ответ, попробуй ещё раз.")


def _extract_json(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


# ---------- public API ----------

async def generate_plan(profile: str) -> Plan:
    if config.AI_PROVIDER == "claude":
        response = await _claude(_client().beta.messages.parse, system=PLAN_SYSTEM,
                                 messages=[{"role": "user", "content": profile}],
                                 output_format=Plan, output_config={"effort": "medium"})
        if response.parsed_output is None:
            raise AIError("Не получилось составить план, попробуй ещё раз.")
        return response.parsed_output

    for attempt in (1, 2):
        raw = await _chat(PLAN_SYSTEM + PLAN_JSON_INSTRUCTION, profile, 12000)
        try:
            return Plan.model_validate_json(_extract_json(raw))
        except ValidationError as e:
            log.warning("Invalid plan JSON (attempt %s): %s", attempt, e)
    raise AIError("Не получилось составить план, попробуй ещё раз.")


async def _text(system: str, content: str, effort: str) -> str:
    if config.AI_PROVIDER != "claude":
        return await _chat(system, content)
    response = await _claude(_client().beta.messages.create, system=system,
                             messages=[{"role": "user", "content": content}],
                             output_config={"effort": effort})
    return "".join(block.text for block in response.content if block.type == "text").strip()


async def analyze_plan(profile: str, user_plan: str) -> str:
    return await _text(ANALYZE_SYSTEM, f"{profile}\n\nПрограмма клиента:\n{user_plan}", "medium")


async def explain_technique(exercise: str) -> str:
    return await _text(TECHNIQUE_SYSTEM, f"Упражнение: {exercise}", "low")
