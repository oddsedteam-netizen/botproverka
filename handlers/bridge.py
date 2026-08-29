import time
import aiosqlite
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatType

from config import ADMIN_ID
from database import db

router = Router()

# Антиспам: {user_id: last_message_timestamp}
_antispam_cache: dict[int, float] = {}

# Маппинг сообщений: чтобы правильно связывать реплаи
# Ключ: (chat_id, message_id) в топике/ЛС → значение: message_id в другом чате
# Формат: {"topic_to_dm": {(chat_id, msg_id): dm_msg_id}, "dm_to_topic": {(user_id, msg_id): topic_msg_id}}
_message_map_topic_to_dm: dict[tuple, int] = {}
_message_map_dm_to_topic: dict[tuple, int] = {}


async def is_our_chat(message: Message) -> bool:
    super_chat_id = await db.get_super_chat_id()
    return super_chat_id != 0 and message.chat.id == super_chat_id


# ==================== /ban ====================

@router.message(Command("ban"), F.chat.type.in_({ChatType.SUPERGROUP, ChatType.GROUP}))
async def cmd_ban(message: Message, bot: Bot):
    if not await is_our_chat(message):
        return
    if message.from_user.id != ADMIN_ID:
        return
    if not message.message_thread_id:
        await message.reply("⚠️ Используйте /ban внутри топика ПЗ")
        return

    topic_info = await db.get_topic_info(message.message_thread_id)
    if not topic_info:
        await message.reply("⚠️ Топик не привязан к ПЗ")
        return

    reason = message.text.replace("/ban", "").strip() or "Не указана"
    user_id = topic_info['user_id']

    await db.ban_user(user_id, reason)
    await db.add_log(ADMIN_ID, "Забанил ПЗ", f"ID: {user_id} | Причина: {reason}")

    await message.reply(
        f"🚫 <b>ПЗ забанен</b>\n\n"
        f"🆔 <code>{user_id}</code>\n"
        f"📝 Причина: {reason}"
    )

    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"🚫 <b>Вы были заблокированы</b>\n{'━' * 28}\n\n"
                f"📝 Причина: {reason}\n\n"
                f"Вы больше не можете пользоваться ботом."
            )
        )
    except Exception:
        pass


# ==================== /unban ====================

@router.message(Command("unban"), F.chat.type.in_({ChatType.SUPERGROUP, ChatType.GROUP}))
async def cmd_unban(message: Message, bot: Bot):
    if not await is_our_chat(message):
        return
    if message.from_user.id != ADMIN_ID:
        return
    if not message.message_thread_id:
        await message.reply("⚠️ Используйте /unban внутри топика ПЗ")
        return

    topic_info = await db.get_topic_info(message.message_thread_id)
    if not topic_info:
        await message.reply("⚠️ Топик не привязан к ПЗ")
        return

    user_id = topic_info['user_id']
    await db.unban_user(user_id)
    await db.add_log(ADMIN_ID, "Разбанил ПЗ", f"ID: {user_id}")

    await message.reply(f"✅ <b>ПЗ разбанен</b>\n🆔 <code>{user_id}</code>")

    try:
        await bot.send_message(
            chat_id=user_id,
            text="✅ <b>Вы разблокированы!</b>\n\nТеперь вы можете снова пользоваться ботом."
        )
    except Exception:
        pass


# ==================== /close ====================

@router.message(Command("close"), F.chat.type.in_({ChatType.SUPERGROUP, ChatType.GROUP}))
async def close_ticket(message: Message, bot: Bot):
    if not await is_our_chat(message):
        return
    if message.from_user.id != ADMIN_ID:
        return
    if not message.message_thread_id:
        await message.reply("⚠️ Используйте /close внутри топика.")
        return

    topic_info = await db.get_topic_info(message.message_thread_id)
    if not topic_info:
        await message.reply("⚠️ Топик не привязан.")
        return

    if topic_info['topic_type'] != 'ticket':
        await message.reply(
            f"❌ /close работает только в тикетах.\nТип: <code>{topic_info['topic_type']}</code>"
        )
        return

    if topic_info['status'] == 'closed':
        await message.reply("ℹ️ Тикет уже закрыт.")
        return

    await db.close_topic(message.message_thread_id)
    await db.add_log(ADMIN_ID, "Закрыл тикет", f"Topic: {message.message_thread_id}")

    await message.reply("✅ <b>Тикет закрыт.</b>")

    try:
        await bot.close_forum_topic(chat_id=message.chat.id, message_thread_id=message.message_thread_id)
    except Exception:
        pass

    try:
        await bot.send_message(
            chat_id=topic_info['user_id'],
            text="🔒 <b>Ваш тикет закрыт администратором.</b>\n\nСпасибо за обращение!"
        )
    except Exception:
        pass


# ==================== АДМИН → ПЗ (с поддержкой reply) ====================

@router.message(
    F.chat.type.in_({ChatType.SUPERGROUP, ChatType.GROUP}),
    F.message_thread_id,
    ~F.text.startswith("/"),
)
async def admin_to_user(message: Message, bot: Bot):
    if not await is_our_chat(message):
        return
    if message.from_user.id != ADMIN_ID:
        return
    if message.forum_topic_created or message.forum_topic_closed or message.forum_topic_reopened:
        return

    topic_info = await db.get_topic_info(message.message_thread_id)
    if not topic_info:
        return
    if topic_info['status'] == 'closed':
        await message.reply("⚠️ Топик закрыт.")
        return

    user_id = topic_info['user_id']

    # Определяем reply_to_message_id для ЛС пользователя
    reply_to_dm_id = None
    if message.reply_to_message:
        reply_msg = message.reply_to_message
        # Игнорируем reply на сервисное сообщение о создании топика
        if reply_msg.message_id != message.message_thread_id:
            # Ищем в маппинге: сообщение админа → сообщение в ЛС
            key = (message.chat.id, reply_msg.message_id)
            reply_to_dm_id = _message_map_topic_to_dm.get(key)

            # Если это ответ на сообщение ПЗ (пришедшее из ЛС в топик)
            if not reply_to_dm_id:
                # Ищем в маппинге dm_to_topic: какое сообщение ПЗ соответствует этому в топике
                for (uid, dm_msg_id), topic_msg_id in _message_map_dm_to_topic.items():
                    if uid == user_id and topic_msg_id == reply_msg.message_id:
                        reply_to_dm_id = dm_msg_id
                        break

    try:
        sent = await bot.copy_message(
            chat_id=user_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            reply_to_message_id=reply_to_dm_id,
            allow_sending_without_reply=True
        )
        # Сохраняем маппинг: сообщение в топике → сообщение в ЛС
        _message_map_topic_to_dm[(message.chat.id, message.message_id)] = sent.message_id
    except Exception as e:
        await message.reply(f"❌ Не доставлено: <code>{e}</code>")


# ==================== ПЗ → АДМИН (с поддержкой reply) ====================

@router.message(F.chat.type == ChatType.PRIVATE, ~F.text.startswith("/"))
async def user_to_admin(message: Message, bot: Bot):
    # Игнорируем кнопки клавиатуры
    if message.text in ("📝 Подать заявление", "🎫 Создать тикет", "👨‍💼 Связаться с админом", "👤 Профиль"):
        return

    user_id = message.from_user.id

    # Проверка бана
    user = await db.get_user(user_id)
    if user and user['is_banned']:
        await message.answer(f"🚫 <b>Вы заблокированы</b>\n\nПричина: {user['ban_reason'] or '—'}")
        return

    # Проверка включен ли бот
    bot_enabled = await db.get_setting("bot_enabled", "on")
    if bot_enabled == "off":
        await message.answer("🔴 <b>Бот временно отключен.</b>\nОжидайте включения.")
        return

    # Антиспам
    antispam = await db.get_setting("antispam", "off")
    if antispam == "on":
        now = time.time()
        last = _antispam_cache.get(user_id, 0)
        if now - last < 60:
            remaining = int(60 - (now - last))
            await message.answer(
                f"🛡 <b>Антиспам</b>\n\nПодождите <b>{remaining} сек.</b> перед следующим сообщением."
            )
            return
        _antispam_cache[user_id] = now

    super_chat_id = await db.get_super_chat_id()
    if super_chat_id == 0:
        return

    # Ищем открытый топик
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM topics WHERE user_id=? AND status='open' ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        )
        row = await cursor.fetchone()
        topic = dict(row) if row else None

    if not topic:
        return

    # Определяем reply_to_message_id в топике
    reply_to_topic_id = None
    if message.reply_to_message:
        reply_msg = message.reply_to_message
        # Ищем: сообщение в ЛС → сообщение в топике
        # Вариант 1: пользователь отвечает на своё же сообщение (было отправлено в топик)
        key = (user_id, reply_msg.message_id)
        reply_to_topic_id = _message_map_dm_to_topic.get(key)

        # Вариант 2: пользователь отвечает на сообщение админа (пришедшее из топика)
        if not reply_to_topic_id:
            for (chat_id, topic_msg_id), dm_msg_id in _message_map_topic_to_dm.items():
                if chat_id == super_chat_id and dm_msg_id == reply_msg.message_id:
                    reply_to_topic_id = topic_msg_id
                    break

    try:
        sent = await bot.copy_message(
            chat_id=super_chat_id,
            message_thread_id=topic['topic_id'],
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            reply_to_message_id=reply_to_topic_id,
            allow_sending_without_reply=True
        )
        # Сохраняем маппинг: сообщение в ЛС → сообщение в топике
        _message_map_dm_to_topic[(user_id, message.message_id)] = sent.message_id
    except Exception:
        await db.close_topic(topic['topic_id'])