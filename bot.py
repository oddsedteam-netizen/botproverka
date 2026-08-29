import asyncio
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import TelegramObject, Message

from config import BOT_TOKEN
from database.db import init_db, register_user, increment_messages
from handlers import admin, stats, user, bridge


class UserTrackingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        u = data.get("event_from_user")
        if u and not u.is_bot:
            await register_user(
                user_id=u.id,
                username=u.username or '',
                first_name=u.first_name or '',
                last_name=u.last_name or ''
            )
            if isinstance(event, Message) and event.chat.type == "private":
                await increment_messages(u.id)

        return await handler(event, data)


async def on_startup():
    await init_db()
    print("✅ База данных инициализирована")


async def main():
    logging.basicConfig(level=logging.INFO)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    dp.message.outer_middleware(UserTrackingMiddleware())
    dp.callback_query.outer_middleware(UserTrackingMiddleware())

    # ВАЖЕН ПОРЯДОК: admin/stats/user — конкретные обработчики,
    # bridge — общий catch-all, должен быть ПОСЛЕДНИМ
    dp.include_router(admin.router)
    dp.include_router(stats.router)
    dp.include_router(user.router)
    dp.include_router(bridge.router)

    await on_startup()

    print("✅ Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("❌ Бот остановлен")