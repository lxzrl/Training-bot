import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat

import config
import db
from handlers import admin, analysis, body, common, diary, onboarding, plan, progress, reminders, technique
from middlewares import AccessMiddleware
from scheduler import reminder_loop


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db.init()

    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(AccessMiddleware())
    dp.callback_query.outer_middleware(AccessMiddleware())
    dp.include_routers(common.router, admin.router, onboarding.router, plan.router, diary.router,
                       technique.router, analysis.router, body.router, progress.router, reminders.router,
                       common.fallback_router)

    commands = [
        BotCommand(command="start", description="Начать / главное меню"),
        BotCommand(command="help", description="Что умеет бот"),
        BotCommand(command="cancel", description="Отменить текущее действие"),
    ]
    await bot.set_my_commands(commands)
    if config.ADMIN_ID:
        await bot.set_my_commands(commands + [BotCommand(command="proxy", description="Прокси / VPN для нейросети")],
                                  scope=BotCommandScopeChat(chat_id=config.ADMIN_ID))
    reminders_task = asyncio.create_task(reminder_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        reminders_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
