import html
import json
import os
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, ChatMemberUpdated,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatType, ChatMemberStatus

from database import db

ADMIN_ID = int(os.getenv("ADMIN_ID", "1269379743"))
TGK_LINK = os.getenv("TGK_LINK", "https://t.me/Checking_the_angel")

router = Router()


# ==================== СОСТОЯНИЯ ====================

class VerificationForm(StatesGroup):
    waiting_bot_username = State()
    waiting_reason = State()
    waiting_admin = State()
    waiting_topic = State()
    confirm = State()


class QuickVerification(StatesGroup):
    waiting_admin = State()
    waiting_topic = State()
    confirm = State()


class LinkBotState(StatesGroup):
    waiting_bot_username = State()


# ==================== КЛАВИАТУРЫ ====================

def main_user_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Подать заявление"), KeyboardButton(text="🎫 Тикеты")],
            [KeyboardButton(text="👨‍💼 Связаться с админом"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🏆 Топы")],
        ],
        resize_keyboard=True,
        is_persistent=True
    )


def skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏩ Пропустить", callback_data="form_skip")],
        [InlineKeyboardButton(text="❌ Отменить заявку", callback_data="form_cancel")],
    ])


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить заявку", callback_data="form_cancel")],
    ])


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить и отправить", callback_data="form_confirm")],
        [InlineKeyboardButton(text="🔄 Заполнить заново", callback_data="form_restart")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="form_cancel")],
    ])


def quick_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить и отправить", callback_data="quick_confirm")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="form_cancel")],
    ])


def quick_skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏩ Пропустить", callback_data="quick_skip")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="form_cancel")],
    ])


def review_keyboard(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"req_accept_{request_id}"),
            InlineKeyboardButton(text="❌ Отказ", callback_data=f"req_deny_{request_id}"),
        ],
        [InlineKeyboardButton(text="ℹ️ Доп. инфа", callback_data=f"req_info_{request_id}")],
    ])


def profile_keyboard(is_verified: bool = False, is_checkup_mod: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    # Модератор check-up действует от лица бота check-up — верификация ему не нужна
    if is_checkup_mod:
        buttons.append([InlineKeyboardButton(text="📤 Добавить проверку", callback_data="profile_post_checkup")])
    # Верификация / выложить проверку (для обычных проверяющих)
    elif is_verified:
        buttons.append([InlineKeyboardButton(text="📤 Выложить проверку", callback_data="profile_post_check")])
    else:
        buttons.append([InlineKeyboardButton(text="🔍 Верификация", callback_data="profile_verify")])

    # Управление ТГК — только для верифицированных проверяющих
    if is_verified and not is_checkup_mod:
        buttons.append([
            InlineKeyboardButton(text="🔁 Сменить ТГК", callback_data="profile_change_tgk"),
            InlineKeyboardButton(text="➕ Добавить ТГК", callback_data="profile_add_tgk"),
        ])

    # Модератор может снять с себя полномочия, обычный пользователь — подать анкету
    if is_checkup_mod:
        buttons.append([InlineKeyboardButton(text="🛡️ Снять полномочия", callback_data="profile_unmod")])
    else:
        buttons.append([InlineKeyboardButton(text="📋 Анкета", callback_data="profile_anketa")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==================== ХЕЛПЕР ПРОВЕРОК ====================

async def check_access(message: Message) -> bool:
    """Проверяет бан и включен ли бот. Возвращает True если можно продолжать."""
    user = await db.get_user(message.from_user.id)
    if user and user.get('is_banned'):
        await message.answer(
            f"🚫 <b>Вы заблокированы</b>\n\nПричина: {user['ban_reason'] or '—'}"
        )
        return False

    bot_enabled = await db.get_setting("bot_enabled", "on")
    if bot_enabled == "off":
        await message.answer("🔴 <b>Бот временно отключен.</b>\nОжидайте включения.")
        return False

    return True


# ==================== ПОДКЛЮЧЕНИЕ К ЧАТУ ====================

@router.message(Command("connect"))
async def cmd_connect(message: Message, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Эта команда только для админа.")
        return

    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.answer(
            "❌ Эту команду нужно использовать <b>в группе</b>!\n\n"
            "1. Добавьте бота в группу\n"
            "2. Выдайте ему права администратора\n"
            "3. Включите «Темы» (Topics)\n"
            "4. Напишите /connect"
        )
        return

    try:
        test_topic = await bot.create_forum_topic(
            chat_id=message.chat.id,
            name="✅ Проверка подключения"
        )
        await bot.send_message(
            chat_id=message.chat.id,
            message_thread_id=test_topic.message_thread_id,
            text="✅ <b>Бот успешно подключен!</b>\nЭтот топик можно удалить."
        )
    except Exception as e:
        await message.answer(f"❌ <b>Ошибка:</b> <code>{e}</code>")
        return

    await db.set_super_chat_id(message.chat.id)
    await db.add_log(message.from_user.id, "Подключил суперчат", f"Chat ID: {message.chat.id}")
    await message.answer(
        f"✅ Группа <b>{message.chat.title}</b> подключена.\n"
        f"🆔 <code>{message.chat.id}</code>"
    )


@router.message(Command("disconnect"))
async def cmd_disconnect(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    current = await db.get_super_chat_id()
    if current == 0:
        await message.answer("ℹ️ Суперчат не подключен.")
        return
    await db.set_super_chat_id(0)
    await message.answer(f"✅ Суперчат отключен.")


@router.message(Command("chatinfo"))
async def cmd_chatinfo(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    current = await db.get_super_chat_id()
    if current == 0:
        await message.answer("ℹ️ Суперчат <b>не подключен</b>. Используйте /connect")
    else:
        await message.answer(f"✅ Суперчат: <code>{current}</code>")


# ==================== ПРИВЕТСТВИЕ ====================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if message.chat.type != ChatType.PRIVATE:
        return
    await state.clear()

    # Проверка бана
    user = await db.get_user(message.from_user.id)
    if user and user.get('is_banned'):
        await message.answer(
            f"🚫 <b>Вы заблокированы</b>\n\nПричина: {user['ban_reason'] or '—'}"
        )
        return

    # Проверка включен ли бот (для админа не блокируем)
    bot_enabled = await db.get_setting("bot_enabled", "on")
    if bot_enabled == "off" and message.from_user.id != ADMIN_ID:
        await message.answer("🔴 <b>Бот временно отключен.</b>\nОжидайте включения.")
        return

    # Кастомное приветствие из редактора
    welcome = await db.get_setting("welcome_text", "")
    buttons_json = await db.get_setting("welcome_buttons", "")

    if not welcome:
        welcome = (
            "👋 <b>Добро пожаловать!</b>\n\n"
            "Это бот проверки. Здесь вы можете:\n"
            "• 📝 Подать заявление на проверку бота\n"
            "• 🎫 Тикеты\n"
            "• 👨‍💼 Связаться с админом\n"
            "• 👤 Посмотреть свой профиль\n\n"
            "<i>Текст приветствия — заглушка. Настраивается в редакторе.</i>"
        )

    kb = None
    if buttons_json:
        try:
            btns = json.loads(buttons_json)
            rows = [[InlineKeyboardButton(text=b['text'], url=b['url'])] for b in btns]
            kb = InlineKeyboardMarkup(inline_keyboard=rows)
        except Exception:
            pass

    await message.answer(welcome, reply_markup=kb)
    await message.answer("👇 Используйте клавиатуру ниже:", reply_markup=main_user_keyboard())


# ==================== ПРОФИЛЬ ====================

@router.message(F.text == "👤 Профиль", F.chat.type == ChatType.PRIVATE)
async def show_profile(message: Message, state: FSMContext):
    if not await check_access(message):
        return
    await state.clear()
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Вы не зарегистрированы. Нажмите /start")
        return
    await send_profile(message, user)


async def send_profile(message_or_callback, user: dict, edit: bool = False):
    """Универсальная функция отправки профиля"""
    import aiosqlite
    from database.db import DB_PATH

    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM verification_requests WHERE user_id = ?",
            (user['user_id'],)
        )
        total_requests = (await cursor.fetchone())[0]

        cursor = await conn.execute(
            "SELECT COUNT(*) FROM verification_requests WHERE user_id = ? AND status = 'pending'",
            (user['user_id'],)
        )
        pending_requests = (await cursor.fetchone())[0]

        cursor = await conn.execute(
            "SELECT COUNT(*) FROM verification_requests WHERE user_id = ? AND status = 'approved'",
            (user['user_id'],)
        )
        approved_requests = (await cursor.fetchone())[0]

        cursor = await conn.execute(
            "SELECT COUNT(*) FROM verification_requests WHERE user_id = ? AND status = 'denied'",
            (user['user_id'],)
        )
        denied_requests = (await cursor.fetchone())[0]

        cursor = await conn.execute(
            "SELECT COUNT(*) FROM topics WHERE user_id = ? AND topic_type = 'ticket'",
            (user['user_id'],)
        )
        total_tickets = (await cursor.fetchone())[0]

        cursor = await conn.execute(
            "SELECT COUNT(*) FROM topics WHERE user_id = ? AND topic_type = 'ticket' AND status = 'open'",
            (user['user_id'],)
        )
        open_tickets = (await cursor.fetchone())[0]

        cursor = await conn.execute(
            "SELECT COUNT(*) FROM topics WHERE user_id = ? AND topic_type = 'ticket' AND status = 'closed'",
            (user['user_id'],)
        )
        closed_tickets = (await cursor.fetchone())[0]

    username_display = f"@{user['username']}" if user['username'] else "не указан"
    name = f"{user['first_name']} {user['last_name']}".strip() or "Не указано"

    # Плашки ролей
    u = user

    # Отдельная выделяющаяся плашка модератора check-up
    mod_banner = ""
    if u.get('checkup_mod'):
        mod_banner = (
            "\n🛡️━━━━━━━━━━━━━━━━━━━━🛡️\n"
            "   ⭐ МОДЕРАТОР CHECK-UP ⭐\n"
            "   Проверки действуют от лица бота check-up\n"
            "   и публикуются в топ «Проверки check-up» 🔍\n"
            "🛡️━━━━━━━━━━━━━━━━━━━━🛡️\n"
        )

    badges = []
    if u.get('is_verified'):
        badges.append("🔍 Верифицирован ✓")
    badge_text = "\n".join(f"   {b}" for b in badges)
    if badge_text:
        badge_text = f"\n{badge_text}\n"

    # ТГК проверяющего: верифицированный + все привязанные (бот добавлен в каналы)
    verified_tgk = None
    bindings = []
    if u.get('is_verified'):
        verified_tgk = await db.get_user_tgk_check(user['user_id'])
        bindings = await db.get_all_user_tgk_bindings(user['user_id'])

    tgk_section = ""
    if verified_tgk and verified_tgk.get('tgk_link'):
        v_link = html.escape(str(verified_tgk['tgk_link']))
        v_name = html.escape(str(verified_tgk.get('tgk_name') or verified_tgk['tgk_link']))
        tgk_lines = [f"   🔒 <a href=\"{v_link}\">{v_name}</a> — верифицирован"]
        seen = {str(verified_tgk['tgk_link']).rstrip('/').lower()}
        for b in bindings:
            uname = (b.get('username') or '').strip().lstrip('@')
            b_link_rel = ""
            if uname:
                b_link_rel = uname.lower()
            elif b.get('chat_title'):
                b_link_rel = str(b['chat_title']).strip()
            if b_link_rel in seen:
                continue
            seen.add(b_link_rel)
            b_link = f"https://t.me/{html.escape(uname)}" if uname else ''
            b_title = html.escape(str(b.get('chat_title') or uname or '—'))
            if b_link:
                tgk_lines.append(f"   · <a href=\"{b_link}\">{b_title}</a>")
            else:
                tgk_lines.append(f"   · {b_title}")
        tgk_section = "📢 <b>ТГК проверяющего:</b>\n" + "\n".join(tgk_lines) + "\n\n"

    text = (
        f"👤 <b>Ваш профиль</b>\n"
        f"{'━' * 28}\n\n"
        f"🆔 <b>ID:</b> <code>{user['user_id']}</code>\n"
        f"👤 <b>Имя:</b> {name}\n"
        f"📛 <b>Username:</b> {username_display}\n"
        f"{mod_banner}"
        f"{badge_text}"
        f"{tgk_section}"
        f"📝 <b>Заявления на проверку:</b>\n"
        f"   Всего: {total_requests}\n"
        f"   ⏳ Ожидают: {pending_requests}\n"
        f"   ✅ Одобрено: {approved_requests}\n"
        f"   ❌ Отклонено: {denied_requests}\n\n"
        f"🎫 <b>Тикеты:</b>\n"
        f"   Всего: {total_tickets}\n"
        f"   🟡 Открытые: {open_tickets}\n"
        f"   ⚪ Закрытые: {closed_tickets}\n\n"
        f"💬 <b>Сообщений:</b> {user['messages_count']}\n"
        f"📅 <b>Дата регистрации:</b> {user['join_date'][:10] if user['join_date'] else '—'}\n"
    )

    kb = profile_keyboard(is_verified=bool(user.get('is_verified')), is_checkup_mod=bool(user.get('checkup_mod')))

    if edit and hasattr(message_or_callback, 'edit_text'):
        await message_or_callback.edit_text(text, reply_markup=kb)
    elif hasattr(message_or_callback, 'answer'):
        await message_or_callback.answer(text, reply_markup=kb)


# ==================== ПРИВЯЗКА БОТА ====================

@router.callback_query(F.data == "profile_link_bot")
async def profile_link_bot(callback: CallbackQuery, state: FSMContext):
    await state.set_state(LinkBotState.waiting_bot_username)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="profile_cancel")],
    ])

    await callback.message.edit_text(
        "🔗 <b>Привязка бота</b>\n"
        f"{'━' * 28}\n\n"
        "Отправьте <b>юзернейм бота</b>, который хотите привязать к профилю.\n\n"
        "<i>Пример: @MyBot или mybot</i>",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data == "profile_cancel")
async def profile_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await db.get_user(callback.from_user.id)
    if user:
        await send_profile(callback.message, user, edit=True)
    await callback.answer()


@router.message(LinkBotState.waiting_bot_username, F.chat.type == ChatType.PRIVATE)
async def process_link_bot(message: Message, state: FSMContext):
    bot_username = message.text.strip()

    if len(bot_username) < 3:
        await message.answer("❌ Юзернейм слишком короткий. Попробуйте ещё раз.")
        return
    if len(bot_username) > 64:
        await message.answer("❌ Юзернейм слишком длинный.")
        return

    clean = bot_username.lstrip("@")
    final = f"@{clean}"

    await db.set_linked_bot(message.from_user.id, final)
    await db.add_log(message.from_user.id, "Привязал бота", final)
    await state.clear()

    await message.answer(f"✅ Бот <b>{final}</b> привязан к вашему профилю!")

    user = await db.get_user(message.from_user.id)
    if user:
        await send_profile(message, user, edit=False)


# ==================== БЫСТРЫЙ ЗАПРОС ПРОВЕРКИ ====================

@router.callback_query(F.data == "profile_quick_verify")
async def profile_quick_verify(callback: CallbackQuery, state: FSMContext):
    user = await db.get_user(callback.from_user.id)
    if not user or not user.get('linked_bot'):
        await callback.answer("❌ Сначала привяжите бота!", show_alert=True)
        return

    existing = await db.get_pending_request_by_user(callback.from_user.id)
    if existing:
        await callback.answer("⚠️ У вас уже есть активная заявка!", show_alert=True)
        return

    await state.update_data(
        bot_username=user['linked_bot'],
        reason="Запрос проверки из профиля"
    )

    await callback.message.edit_text(
        f"🚀 <b>Быстрый запрос проверки</b>\n"
        f"{'━' * 28}\n\n"
        f"🤖 Бот: <b>{user['linked_bot']}</b> (из профиля)\n\n"
        f"📌 <b>Шаг 1 из 2</b>\n"
        f"Укажите <b>тег желаемого админа</b> для проверки.\n\n"
        f"<i>Пример: @admin_tag\n"
        f"Если нет предпочтений — «Пропустить»</i>"
    )
    await callback.message.answer(
        "Введите тег админа или нажмите «Пропустить» 👇",
        reply_markup=quick_skip_keyboard()
    )
    await state.set_state(QuickVerification.waiting_admin)
    await callback.answer()


@router.callback_query(F.data == "quick_skip", QuickVerification.waiting_admin)
async def quick_skip_admin(callback: CallbackQuery, state: FSMContext):
    await state.update_data(preferred_admin="Не указан")
    await callback.message.edit_text(
        "✅ Пропущено!\n\n"
        "📌 <b>Шаг 2 из 2</b>\n"
        "Укажите <b>тему для проверки</b>.\n\n"
        "<i>Например: безопасность, функционал, скам\n"
        "Если нет — «Пропустить»</i>"
    )
    await callback.message.answer("Введите тему или «Пропустить» 👇", reply_markup=quick_skip_keyboard())
    await state.set_state(QuickVerification.waiting_topic)
    await callback.answer()


@router.message(QuickVerification.waiting_admin, F.chat.type == ChatType.PRIVATE)
async def quick_process_admin(message: Message, state: FSMContext):
    admin_pref = message.text.strip()
    if not admin_pref.startswith("@"):
        admin_pref = f"@{admin_pref.lstrip('@')}"
    await state.update_data(preferred_admin=admin_pref)
    await message.answer(
        "✅ Записано!\n\n"
        "📌 <b>Шаг 2 из 2</b>\n"
        "Укажите <b>тему для проверки</b>.",
        reply_markup=quick_skip_keyboard()
    )
    await state.set_state(QuickVerification.waiting_topic)


@router.callback_query(F.data == "quick_skip", QuickVerification.waiting_topic)
async def quick_skip_topic(callback: CallbackQuery, state: FSMContext):
    await state.update_data(topic="Не указана")
    await show_quick_confirmation(callback.message, state, edit=True)
    await callback.answer()


@router.message(QuickVerification.waiting_topic, F.chat.type == ChatType.PRIVATE)
async def quick_process_topic(message: Message, state: FSMContext):
    await state.update_data(topic=message.text.strip())
    await show_quick_confirmation(message, state, edit=False)


async def show_quick_confirmation(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    text = (
        "📋 <b>Проверьте заявку</b>\n"
        f"{'━' * 28}\n\n"
        f"🤖 <b>Бот:</b> {data['bot_username']}\n"
        f"👤 <b>Желаемый админ:</b> {data.get('preferred_admin', 'Не указан')}\n"
        f"📌 <b>Тема:</b> {data.get('topic', 'Не указана')}\n\n"
        "Всё верно? 👇"
    )
    await state.set_state(QuickVerification.confirm)
    if edit:
        await message.edit_text(text, reply_markup=quick_confirm_keyboard())
    else:
        await message.answer(text, reply_markup=quick_confirm_keyboard())


@router.callback_query(F.data == "quick_confirm")
async def quick_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user = callback.from_user
    await state.clear()

    request_id = await db.create_verification_request(
        user_id=user.id,
        bot_username=data['bot_username'],
        reason=data.get('reason', 'Быстрый запрос из профиля'),
        preferred_admin=data.get('preferred_admin', 'Не указан'),
        topic=data.get('topic', 'Не указана')
    )
    await db.add_log(user.id, "Быстрая заявка из профиля", f"#{request_id} — {data['bot_username']}")

    await callback.message.edit_text(
        "✅ <b>Заявка отправлена!</b>\n\n"
        f"📋 Номер: <b>#{request_id}</b>\n"
        f"🤖 Бот: {data['bot_username']}\n\n"
        "⏳ Ожидайте рассмотрения."
    )

    user_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Без имени"
    username_display = f"@{user.username}" if user.username else "нет"

    review_text = (
        f"📋 <b>Новая заявка #{request_id}</b>\n"
        f"{'━' * 28}\n\n"
        f"<b>👤 ПЗ:</b>\n"
        f"   🆔 ID: <code>{user.id}</code>\n"
        f"   👤 {user_name}\n"
        f"   📛 {username_display}\n\n"
        f"<b>📝 Заявка:</b>\n"
        f"   🤖 Бот: {data['bot_username']}\n"
        f"   📌 Причина: {data.get('reason', '—')}\n"
        f"   👤 Админ: {data.get('preferred_admin', 'Не указан')}\n"
        f"   📂 Тема: {data.get('topic', 'Не указана')}\n\n"
        f"⏳ <b>Статус:</b> Ожидает рассмотрения"
    )

    super_chat_id = await db.get_super_chat_id()

    if super_chat_id != 0:
        try:
            topic_name = f"Заявка #{request_id} — {data['bot_username']}"
            forum_topic = await bot.create_forum_topic(chat_id=super_chat_id, name=topic_name)
            tid = forum_topic.message_thread_id
            await db.create_topic_link(tid, user.id, "verification")
            await db.update_request_topic_id(request_id, tid)
            await bot.send_message(
                chat_id=super_chat_id, message_thread_id=tid,
                text=review_text, reply_markup=review_keyboard(request_id)
            )
        except Exception as e:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ Ошибка: <code>{e}</code>\n\n{review_text}",
                reply_markup=review_keyboard(request_id)
            )
    else:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ <i>Суперчат не подключен</i>\n\n{review_text}",
            reply_markup=review_keyboard(request_id)
        )

    await callback.answer("✅ Отправлено!")


# ==================== ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ СОЗДАНИЯ ТОПИКА ====================

async def create_bridge_topic(bot: Bot, user, topic_name: str, topic_type: str, header_text: str) -> int | None:
    super_chat_id = await db.get_super_chat_id()
    user_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Без имени"
    username_display = f"@{user.username}" if user.username else "нет"

    full_header = (
        f"{header_text}\n{'━' * 28}\n\n"
        f"<b>👤 ПЗ:</b>\n"
        f"   🆔 <code>{user.id}</code>\n"
        f"   👤 {user_name}\n"
        f"   📛 {username_display}\n\n"
        f"<i>💬 Пишите — сообщения доставятся пользователю.</i>"
    )

    if super_chat_id == 0:
        try:
            await bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ Суперчат не подключен\n\n{full_header}")
        except Exception:
            pass
        return None

    try:
        forum_topic = await bot.create_forum_topic(chat_id=super_chat_id, name=topic_name)
        tid = forum_topic.message_thread_id
        await db.create_topic_link(tid, user.id, topic_type)
        await bot.send_message(chat_id=super_chat_id, message_thread_id=tid, text=full_header)
        return tid
    except Exception as e:
        try:
            await bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ Ошибка: <code>{e}</code>\n\n{full_header}")
        except Exception:
            pass
        return None


# ==================== ТИКЕТЫ ====================

def tickets_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎫 Мои тикеты", callback_data="tickets_mine")],
        [InlineKeyboardButton(text="➕ Открыть тикет", callback_data="tickets_open")],
    ])


@router.message(F.text == "🎫 Тикеты", F.chat.type == ChatType.PRIVATE)
async def tickets_menu(message: Message, state: FSMContext):
    if not await check_access(message):
        return
    await state.clear()
    await message.answer(
        "🎫 <b>Тикеты</b>\n"
        f"{'━' * 28}\n\n"
        "Что именно вы хотите открыть?",
        reply_markup=tickets_menu_kb()
    )


@router.callback_query(F.data == "tickets_open")
async def tickets_open(callback: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    existing = await db.get_user_open_topic(callback.from_user.id, "ticket")
    if existing:
        await callback.answer("У вас уже есть открытый тикет!", show_alert=True)
        return

    topic_id = await create_bridge_topic(
        bot=bot, user=callback.from_user,
        topic_name=f"Тикет — {callback.from_user.first_name or callback.from_user.id}",
        topic_type="ticket",
        header_text="🎫 <b>Новый тикет на пересмотр</b>"
    )
    if topic_id:
        await db.add_log(callback.from_user.id, "Создал тикет", f"Topic: {topic_id}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="tickets_cancel")],
    ])
    await callback.message.answer(
        "✅ <b>Тикет открыт!</b>\n"
        f"{'━' * 28}\n\n"
        "Опишите, что хотите открыть. 💬 Можно присылать текст, фото, файлы.\n\n"
        "<i>Тикет будет закрыт администратором после рассмотрения.</i>",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data == "tickets_cancel")
async def tickets_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    open_topic = await db.get_user_open_topic(callback.from_user.id, "ticket")
    if open_topic:
        await db.close_topic(open_topic['topic_id'])
        await callback.message.answer("❌ Тикет отменён.")
    else:
        await callback.message.answer("❌ Отменено.")
    await callback.answer()


@router.callback_query(F.data == "tickets_mine")
async def tickets_mine(callback: CallbackQuery):
    tickets = await db.get_user_tickets(callback.from_user.id)
    text = (
        f"🎫 <b>Мои тикеты</b>\n"
        f"{'━' * 28}\n\n"
    )
    rows = []
    if not tickets:
        text += "<i>У вас пока нет тикетов.</i>"
    else:
        for t in tickets:
            if t['status'] == 'closed':
                text += f"🔴 <b>Тикет #{t['topic_id']}</b> — Закрыт 🔴\n"
            else:
                text += f"🟡 <b>Тикет #{t['topic_id']}</b> — Открыт\n"
            if t['status'] == 'open':
                rows.append([InlineKeyboardButton(text=f"#{t['topic_id']} 👁", callback_data=f"ticket_view_{t['topic_id']}")])

    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="tickets_menu_back")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data == "tickets_menu_back")
async def tickets_menu_back(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎫 <b>Тикеты</b>\n"
        f"{'━' * 28}\n\n"
        "Что именно вы хотите открыть?",
        reply_markup=tickets_menu_kb()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ticket_view_"))
async def ticket_view(callback: CallbackQuery):
    try:
        topic_id = int(callback.data.replace("ticket_view_", ""))
    except ValueError:
        await callback.answer()
        return
    info = await db.get_topic_info(topic_id)
    if not info or info['user_id'] != callback.from_user.id:
        await callback.answer("Не найдено", show_alert=True)
        return

    text = (
        f"🎫 <b>Тикет</b>\n"
        f"{'━' * 28}\n\n"
        f"🆔 Тикет: <code>#{topic_id}</code>\n"
        f"📌 Статус: {'🟡 Открыт' if info['status'] == 'open' else '🔴 Закрыт'}\n"
        f"📅 Создан: {info['created_at'] or '—'}\n"
        f"🏁 Закрыт: {info['closed_at'] or '—'}\n\n"
        f"<i>💬 Пишите сюда — сообщения доставятся администратору.</i>"
    )
    rows = []
    if info['status'] == 'open':
        rows.append([InlineKeyboardButton(text="➕ Дополнить", callback_data=f"ticket_add_{topic_id}")])
        rows.append([InlineKeyboardButton(text="🔴 Закрыть тикет", callback_data=f"ticket_close_{topic_id}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="tickets_mine")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data.startswith("ticket_close_"))
async def ticket_close(callback: CallbackQuery):
    try:
        topic_id = int(callback.data.replace("ticket_close_", ""))
    except ValueError:
        await callback.answer()
        return
    info = await db.get_topic_info(topic_id)
    if not info or info['user_id'] != callback.from_user.id:
        await callback.answer("Не найдено", show_alert=True)
        return
    if info['status'] == 'closed':
        await callback.answer("Тикет уже закрыт", show_alert=True)
        return
    await db.close_topic(topic_id)
    await callback.answer("✅ Тикет закрыт")
    await ticket_view(callback)


@router.callback_query(F.data.startswith("ticket_add_"))
async def ticket_add(callback: CallbackQuery):
    try:
        topic_id = int(callback.data.replace("ticket_add_", ""))
    except ValueError:
        await callback.answer()
        return
    info = await db.get_topic_info(topic_id)
    if not info or info['user_id'] != callback.from_user.id:
        await callback.answer("Не найдено", show_alert=True)
        return
    if info['status'] == 'closed':
        await callback.answer("Тикет закрыт", show_alert=True)
        return
    rows = []
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"ticket_view_{topic_id}")])
    await callback.message.edit_text(
        f"📝 <b>Дополнить тикет #{topic_id}</b>\n"
        f"{'━' * 28}\n\n"
        "Напишите дополнительную информацию — она попадёт к администратору в тикет.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


# ==================== СВЯЗЬ С АДМИНОМ ====================

@router.message(F.text == "👨‍💼 Связаться с админом", F.chat.type == ChatType.PRIVATE)
async def contact_admin(message: Message, bot: Bot, state: FSMContext):
    if not await check_access(message):
        return
    await state.clear()

    existing = await db.get_user_open_topic(message.from_user.id, "contact")
    if existing:
        await message.answer("⚠️ У вас уже открыта переписка с админом! Продолжайте писать.")
        return

    topic_id = await create_bridge_topic(
        bot=bot, user=message.from_user,
        topic_name=f"Связь — {message.from_user.first_name or message.from_user.id}",
        topic_type="contact",
        header_text="👨‍💼 <b>Обращение к админу</b>"
    )
    if topic_id:
        await db.add_log(message.from_user.id, "Связался с админом", f"Topic: {topic_id}")

    await message.answer(
        "✅ <b>Обращение отправлено!</b>\n"
        f"{'━' * 28}\n\n"
        "Админ скоро напишет.\n"
        "💬 Можете уже описать свой вопрос."
    )


# ==================== ПОДАТЬ ЗАЯВЛЕНИЕ (полная форма) ====================

@router.message(F.text == "📝 Подать заявление", F.chat.type == ChatType.PRIVATE)
async def start_verification(message: Message, state: FSMContext):
    if not await check_access(message):
        return

    existing = await db.get_pending_request_by_user(message.from_user.id)
    if existing:
        await message.answer(
            f"⚠️ У вас уже есть заявка <b>#{existing['request_id']}</b> — ожидайте."
        )
        return

    await state.clear()
    await message.answer(
        "📝 <b>Подача заявления</b>\n"
        f"{'━' * 28}\n\n"
        "📌 <b>Шаг 1/4</b> — Юзернейм бота\n\n"
        "<i>Пример: @MyBot</i>",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(VerificationForm.waiting_bot_username)


@router.message(VerificationForm.waiting_bot_username, F.chat.type == ChatType.PRIVATE)
async def process_bot_username(message: Message, state: FSMContext):
    t = message.text.strip()
    if len(t) < 3:
        await message.answer("❌ Слишком коротко.", reply_markup=cancel_keyboard())
        return
    if len(t) > 64:
        await message.answer("❌ Слишком длинно.", reply_markup=cancel_keyboard())
        return

    await state.update_data(bot_username=f"@{t.lstrip('@')}")
    await message.answer(
        "✅ Записано!\n\n📌 <b>Шаг 2/4</b> — Причина проверки",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(VerificationForm.waiting_reason)


@router.message(VerificationForm.waiting_reason, F.chat.type == ChatType.PRIVATE)
async def process_reason(message: Message, state: FSMContext):
    r = message.text.strip()
    if len(r) < 10:
        await message.answer("❌ Минимум 10 символов.", reply_markup=cancel_keyboard())
        return
    if len(r) > 1000:
        await message.answer("❌ Максимум 1000 символов.", reply_markup=cancel_keyboard())
        return

    await state.update_data(reason=r)
    await message.answer(
        "✅ Записано!\n\n📌 <b>Шаг 3/4</b> — Тег желаемого админа\n\n<i>@tag или «Пропустить»</i>",
        reply_markup=skip_keyboard()
    )
    await state.set_state(VerificationForm.waiting_admin)


@router.callback_query(F.data == "form_skip", VerificationForm.waiting_admin)
async def skip_admin(callback: CallbackQuery, state: FSMContext):
    await state.update_data(preferred_admin="Не указан")
    await callback.message.edit_text("✅ Пропущено!\n\n📌 <b>Шаг 4/4</b> — Тема проверки")
    await callback.message.answer("Введите тему или «Пропустить» 👇", reply_markup=skip_keyboard())
    await state.set_state(VerificationForm.waiting_topic)
    await callback.answer()


@router.message(VerificationForm.waiting_admin, F.chat.type == ChatType.PRIVATE)
async def process_admin(message: Message, state: FSMContext):
    a = message.text.strip()
    if not a.startswith("@"):
        a = f"@{a.lstrip('@')}"
    await state.update_data(preferred_admin=a)
    await message.answer(
        "✅ Записано!\n\n📌 <b>Шаг 4/4</b> — Тема проверки",
        reply_markup=skip_keyboard()
    )
    await state.set_state(VerificationForm.waiting_topic)


@router.callback_query(F.data == "form_skip", VerificationForm.waiting_topic)
async def skip_topic(callback: CallbackQuery, state: FSMContext):
    await state.update_data(topic="Не указана")
    await show_confirmation(callback.message, state, edit=True)
    await callback.answer()


@router.message(VerificationForm.waiting_topic, F.chat.type == ChatType.PRIVATE)
async def process_topic(message: Message, state: FSMContext):
    await state.update_data(topic=message.text.strip())
    await show_confirmation(message, state, edit=False)


async def show_confirmation(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    text = (
        "📋 <b>Проверьте заявку</b>\n"
        f"{'━' * 28}\n\n"
        f"🤖 {data['bot_username']}\n"
        f"📝 {data['reason']}\n"
        f"👤 {data.get('preferred_admin', 'Не указан')}\n"
        f"📌 {data.get('topic', 'Не указана')}\n\n"
        "Всё верно? 👇"
    )
    await state.set_state(VerificationForm.confirm)
    if edit:
        await message.edit_text(text, reply_markup=confirm_keyboard())
    else:
        await message.answer(text, reply_markup=confirm_keyboard())


@router.callback_query(F.data == "form_cancel")
async def form_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ <b>Отменено</b>")
    await callback.answer()


@router.callback_query(F.data == "form_restart")
async def form_restart(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🔄 Заново\n\n📌 <b>Шаг 1/4</b> — Юзернейм бота")
    await callback.message.answer("Введите юзернейм 👇", reply_markup=cancel_keyboard())
    await state.set_state(VerificationForm.waiting_bot_username)
    await callback.answer()


@router.callback_query(F.data == "form_confirm")
async def form_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user = callback.from_user
    await state.clear()

    request_id = await db.create_verification_request(
        user_id=user.id,
        bot_username=data['bot_username'],
        reason=data['reason'],
        preferred_admin=data.get('preferred_admin', 'Не указан'),
        topic=data.get('topic', 'Не указана')
    )
    await db.add_log(user.id, "Подал заявку", f"#{request_id}")

    await callback.message.edit_text(
        f"✅ <b>Заявка #{request_id} отправлена!</b>\n"
        f"🤖 {data['bot_username']}\n\n⏳ Ожидайте."
    )

    user_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Без имени"
    username_display = f"@{user.username}" if user.username else "нет"

    review_text = (
        f"📋 <b>Заявка #{request_id}</b>\n{'━' * 28}\n\n"
        f"👤 <code>{user.id}</code> | {user_name} | {username_display}\n\n"
        f"🤖 {data['bot_username']}\n📌 {data['reason']}\n"
        f"👤 Админ: {data.get('preferred_admin', '—')}\n"
        f"📂 Тема: {data.get('topic', '—')}\n\n"
        f"⏳ <b>Статус:</b> Ожидает рассмотрения"
    )

    super_chat_id = await db.get_super_chat_id()
    if super_chat_id != 0:
        try:
            ft = await bot.create_forum_topic(
                chat_id=super_chat_id,
                name=f"Заявка #{request_id} — {data['bot_username']}"
            )
            tid = ft.message_thread_id
            await db.create_topic_link(tid, user.id, "verification")
            await db.update_request_topic_id(request_id, tid)
            await bot.send_message(
                chat_id=super_chat_id, message_thread_id=tid,
                text=review_text, reply_markup=review_keyboard(request_id)
            )
        except Exception as e:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ <code>{e}</code>\n\n{review_text}",
                reply_markup=review_keyboard(request_id)
            )
    else:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Суперчат не подключен\n\n{review_text}",
            reply_markup=review_keyboard(request_id)
        )

    await callback.answer("✅")


# ==================== ДЕЙСТВИЯ АДМИНА ====================

@router.callback_query(F.data.startswith("req_accept_"))
async def request_accept(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Только админ", show_alert=True)
        return
    rid = int(callback.data.replace("req_accept_", ""))
    req = await db.get_request_by_id(rid)
    if not req or req['status'] != 'pending':
        await callback.answer("Заявка не найдена или обработана", show_alert=True)
        return

    await db.update_request_status(rid, "approved")
    await db.add_log(ADMIN_ID, "Принял заявку", f"#{rid}")

    new_text = (callback.message.html_text or "").replace(
        "⏳ <b>Статус:</b> Ожидает рассмотрения",
        "✅ <b>Статус:</b> ПРИНЯТА"
    )
    try:
        await callback.message.edit_text(new_text, reply_markup=None)
    except Exception:
        pass

    try:
        await bot.send_message(
            chat_id=req['user_id'],
            text=(
                f"✅ <b>Заявка #{rid} принята!</b>\n{'━' * 28}\n\n"
                f"🤖 {req['bot_username']}\n\n"
                f"Ваш бот принят на проверку! ⏳ Ожидайте.\n\n📢 Следите за новостями!"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Наш ТГК", url=TGK_LINK)]
            ])
        )
    except Exception:
        pass
    await callback.answer("✅ Принята")


@router.callback_query(F.data.startswith("req_deny_"))
async def request_deny(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Только админ", show_alert=True)
        return
    rid = int(callback.data.replace("req_deny_", ""))
    req = await db.get_request_by_id(rid)
    if not req or req['status'] != 'pending':
        await callback.answer("Обработана", show_alert=True)
        return

    await db.update_request_status(rid, "denied")
    await db.add_log(ADMIN_ID, "Отклонил заявку", f"#{rid}")

    new_text = (callback.message.html_text or "").replace(
        "⏳ <b>Статус:</b> Ожидает рассмотрения",
        "❌ <b>Статус:</b> ОТКЛОНЕНА"
    )
    try:
        await callback.message.edit_text(new_text, reply_markup=None)
    except Exception:
        pass

    try:
        await bot.send_message(
            chat_id=req['user_id'],
            text=f"❌ <b>Заявка #{rid} отклонена</b>\n\n🤖 {req['bot_username']}\n\nМожете подать новую позже."
        )
    except Exception:
        pass
    await callback.answer("❌ Отклонена")


@router.callback_query(F.data.startswith("req_info_"))
async def request_info(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔", show_alert=True)
        return
    rid = int(callback.data.replace("req_info_", ""))
    req = await db.get_request_by_id(rid)
    if not req:
        await callback.answer("Не найдена", show_alert=True)
        return
    try:
        await bot.send_message(
            chat_id=req['user_id'],
            text=f"ℹ️ <b>По заявке #{rid}</b>\n\nАдмин запросил доп. информацию.\nСкоро с вами свяжутся. ⏳"
        )
    except Exception:
        pass
    await callback.answer("ℹ️ Уведомлён", show_alert=True)
# ==================== ПРИВЯЗКА ТГК (бот добавлен в чат) ====================

@router.my_chat_member()
async def on_my_chat_member(update: ChatMemberUpdated, bot: Bot):
    member = update.new_chat_member
    if member and member.user and member.user.id == bot.id:
        # Статус участника изменился
        if update.chat and update.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            # Бот добавлен в чат/ТГК
            active_statuses = (
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                getattr(ChatMemberStatus, "CREATOR", None),
                getattr(ChatMemberStatus, "OWNER", None),
            )
            active_statuses = tuple(s for s in active_statuses if s is not None)
            if member.status in active_statuses:
                # Пробуем сохранить привязку за пользователем, который добавил бота
                if update.from_user and not update.from_user.is_bot:
                    await db.add_tgk_binding(
                        update.from_user.id,
                        update.chat.id,
                        update.chat.title or update.chat.username or '',
                        update.chat.username or ''
                    )
                    try:
                        await bot.send_message(
                            chat_id=update.from_user.id,
                            text=(
                                "🔗 <b>ТГК привязан!</b>\n"
                                f"{'━' * 28}\n\n"
                                f"✅ Бот добавлен в чат <b>{update.chat.title or 'ТГК'}</b>.\n\n"
                                "Это подтверждает владение каналом. Можете продолжить."
                            )
                        )
                    except Exception:
                        pass
            elif member.status == ChatMemberStatus.LEFT:
                if update.from_user and not update.from_user.is_bot:
                    await db.remove_tgk_binding(update.from_user.id, update.chat.id)