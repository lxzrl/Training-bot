from html import escape
from urllib.parse import urlsplit

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import ai
import config
import db

router = Router()

SCHEMES = {"http", "https", "socks5", "socks5h"}

HELP = """<b>🛡 Прокси / VPN для нейросети</b>

Нейросеть: {provider}
Прокси: {proxy}

Задать: <code>/proxy socks5://логин:пароль@адрес:порт</code>
Подходят http://, https:// и socks5://
Выключить: <code>/proxy off</code>

VPN на VLESS настраивается на сервере одной командой: <code>sudo bash install.sh --vpn</code>. После этого прокси здесь будет <code>socks5://127.0.0.1:10818</code>"""


def is_admin(uid: int) -> bool:
    return bool(config.ADMIN_ID) and uid == config.ADMIN_ID


def masked(url: str | None) -> str:
    if not url:
        return "не используется"
    parts = urlsplit(url)
    if parts.password:
        url = url.replace(f":{parts.password}@", ":***@", 1)
    return f"<code>{escape(url)}</code>"


def valid_proxy(url: str) -> bool:
    try:
        parts = urlsplit(url)
        return parts.scheme in SCHEMES and bool(parts.hostname) and parts.port is not None
    except ValueError:
        return False


def status_text() -> str:
    return HELP.format(provider=escape(ai.provider_name()), proxy=masked(ai.current_proxy()))


def check_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔌 Проверить связь", callback_data="admin:check")
    return builder.as_markup()


async def report_check(message: Message):
    wait = await message.answer("Отправляю пробный запрос каждой модели… ⏳")
    try:
        results = await ai.check_models()
    except ai.AIError as e:
        await wait.edit_text(f"❌ {e}")
        return
    lines = ["<b>Проверка нейросети</b>", ""]
    for model, works, detail in results:
        mark = "✅" if works else "❌"
        lines.append(f"{mark} <code>{escape(model)}</code>\n    {escape(detail)}")
    if any(works for _, works, _ in results):
        lines += ["", "Нейросеть работает: бот берёт первую модель из списка, которая отвечает."]
    else:
        lines += ["", "Ни одна модель не ответила. Если ошибка связи — проверь VPN/прокси; "
                      "если 404 — модель убрали, поменяй OPENAI_MODEL в <code>/opt/fitbot/.env</code>."]
    await wait.edit_text("\n".join(lines))


@router.message(Command("proxy"))
async def proxy(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда только для владельца бота 🙂" if config.ADMIN_ID else
                             "Чтобы управлять прокси, впиши свой Telegram ID в ADMIN_ID в файле .env "
                             f"(твой ID: <code>{message.from_user.id}</code>)")
        return
    arg = (command.args or "").strip()
    if not arg:
        await message.answer(status_text(), reply_markup=check_kb())
        return

    if arg.lower() in {"off", "выкл", "нет"}:
        db.set_setting("proxy", "")
        await ai.reset_client()
        await message.answer("Прокси выключен, запросы к нейросети идут напрямую.")
        await report_check(message)
        return

    if not valid_proxy(arg):
        await message.answer("Не похоже на адрес прокси 🤔 Пример: <code>socks5://user:pass@1.2.3.4:1080</code>")
        return
    # The address may contain a password: don't leave it in the chat history.
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    db.set_setting("proxy", arg)
    await ai.reset_client()
    await message.answer(f"Прокси сохранён: {masked(arg)}\nПроверяю связь…")
    await report_check(message)


@router.callback_query(F.data == "admin:check")
async def check(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer()
        return
    await cb.answer("Проверяю…")
    await report_check(cb.message)
