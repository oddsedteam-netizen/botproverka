import asyncio
import json
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatType

from config import ADMIN_ID
from database import db

router = Router()


# ==================== СОСТОЯНИЯ ====================

class EditorState(StatesGroup):
    waiting_welcome_text = State()
    waiting_welcome_buttons = State()


class BroadcastState(StatesGroup):
    waiting_content = State()
    confirm = State()


# ==================== ПРОВЕРКА ====================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ==================== ГЛАВНОЕ МЕНЮ АДМИНКИ ====================

def get_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🔄 Тикеты на пересмотр", callback_data="admin_tickets")],
        [InlineKeyboardButton(text="📝 Заявки на проверку", callback_data="admin_requests")],
        [InlineKeyboardButton(text="📌 ПЗ бота", callback_data="admin_pz")],
        [InlineKeyboardButton(text="⚙️ Редактор бота", callback_data="admin_editor")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🛡 Антиспам", callback_data="admin_antispam")],
        [InlineKeyboardButton(text="🔴 Отключить бота", callback_data="admin_shutdown")],
    ])


def get_admin_text() -> str:
    return "🛠 <b>Админ-панель</b>\n\nВыберите раздел:"


@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(get_admin_text(), reply_markup=get_admin_keyboard())


@router.callback_query(F.data == "back_to_admin")
async def back_to_admin(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.message.edit_text(get_admin_text(), reply_markup=get_admin_keyboard())
    await callback.answer()


# ==================== ТИКЕТЫ НА ПЕРЕСМОТР ====================

@router.callback_query(F.data == "admin_tickets")
async def admin_tickets(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    topics = await db.get_all_topics(topic_type="ticket")
    super_chat_id = await db.get_super_chat_id()

    text = f"🔄 <b>Тикеты на пересмотр</b>\n{'━' * 28}\n\n"

    if not topics:
        text += "<i>Нет тикетов</i>"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")]
        ])
    else:
        buttons = []
        for t in topics:
            user = await db.get_user(t['user_id'])
            name = user['first_name'] if user else str(t['user_id'])
            status_icon = "🟡" if t['status'] == 'open' else "⚪"
            text += f"{status_icon} <b>Тикет</b> | {name} | {t['status']}\n"

            if super_chat_id != 0:
                link = f"https://t.me/c/{str(super_chat_id)[4:]}/{t['topic_id']}"
                buttons.append([InlineKeyboardButton(text=f"{status_icon} {name} — {t['status']}", url=link)])

        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ==================== ЗАЯВКИ НА ПРОВЕРКУ ====================

@router.callback_query(F.data == "admin_requests")
async def admin_requests(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    requests = await db.get_all_requests()
    super_chat_id = await db.get_super_chat_id()

    text = f"📝 <b>Заявки на проверку</b>\n{'━' * 28}\n\n"

    if not requests:
        text += "<i>Нет заявок</i>"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")]
        ])
    else:
        buttons = []
        status_icons = {"pending": "⏳", "approved": "✅", "denied": "❌"}

        for r in requests[:20]:
            icon = status_icons.get(r['status'], "❔")
            text += f"{icon} <b>#{r['request_id']}</b> — {r['bot_username']} | {r['status']}\n"

            if r['topic_id'] and super_chat_id != 0:
                link = f"https://t.me/c/{str(super_chat_id)[4:]}/{r['topic_id']}"
                buttons.append([InlineKeyboardButton(
                    text=f"{icon} #{r['request_id']} — {r['bot_username']}",
                    url=link
                )])

        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ==================== ПЗ БОТА ====================

@router.callback_query(F.data == "admin_pz")
async def admin_pz(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    users = await db.get_all_users()

    text = f"📌 <b>ПЗ бота</b> ({len(users)} чел.)\n{'━' * 28}\n\n"

    buttons = []
    for u in users[:30]:
        stats = await db.get_user_stats(u['user_id'])
        name = u['first_name'] or u['username'] or str(u['user_id'])
        banned = " 🚫" if u['is_banned'] else ""
        line = f"👤 {name}{banned} | 📝{stats['requests']} 🎫{stats['tickets']}"
        text += f"{line}\n"
        buttons.append([InlineKeyboardButton(
            text=f"👤 {name} — 📝{stats['requests']} 🎫{stats['tickets']}",
            callback_data=f"pz_detail_{u['user_id']}"
        )])

    if len(users) > 30:
        text += f"\n<i>...и ещё {len(users) - 30}</i>"

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("pz_detail_"))
async def pz_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    user_id = int(callback.data.replace("pz_detail_", ""))
    user = await db.get_user(user_id)

    if not user:
        await callback.answer("Не найден", show_alert=True)
        return

    stats = await db.get_user_stats(user_id)
    name = f"{user['first_name']} {user['last_name']}".strip() or "—"
    username = f"@{user['username']}" if user['username'] else "—"
    banned = "🚫 Да" if user['is_banned'] else "✅ Нет"
    linked = user.get('linked_bot', '') or "—"

    text = (
        f"👤 <b>Карточка ПЗ</b>\n{'━' * 28}\n\n"
        f"🆔 <code>{user['user_id']}</code>\n"
        f"👤 {name}\n📛 {username}\n"
        f"🤖 Привязанный бот: {linked}\n\n"
        f"💬 Сообщений: {user['messages_count']}\n"
        f"📝 Заявок: {stats['requests']}\n"
        f"🎫 Тикетов: {stats['tickets']}\n"
        f"👨‍💼 Обращений: {stats['contacts']}\n\n"
        f"⚠️ Предупреждений: {user['warnings']}\n"
        f"🚫 Бан: {banned}\n"
        f"📝 Причина: {user['ban_reason'] or '—'}\n\n"
        f"📅 Регистрация: {user['join_date'][:10] if user['join_date'] else '—'}\n"
        f"🕐 Активность: {user['last_active'] or '—'}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к ПЗ", callback_data="admin_pz")]
    ])

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ==================== РЕДАКТОР БОТА ====================

@router.callback_query(F.data == "admin_editor")
async def admin_editor(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    welcome = await db.get_setting("welcome_text", "")
    buttons_json = await db.get_setting("welcome_buttons", "")
    preview = welcome[:100] + "..." if len(welcome) > 100 else welcome
    if not preview:
        preview = "<i>не задан</i>"

    btn_count = 0
    if buttons_json:
        try:
            btn_count = len(json.loads(buttons_json))
        except Exception:
            pass

    text = (
        f"⚙️ <b>Редактор бота</b>\n{'━' * 28}\n\n"
        f"📝 <b>Текущее приветствие:</b>\n{preview}\n\n"
        f"🔘 Кнопок: {btn_count}\n\n"
        f"<i>Поддерживаются премиум-эмодзи, HTML-разметка, жирный, курсив, подчеркивание, код и т.д.</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Изменить приветствие", callback_data="editor_welcome")],
        [InlineKeyboardButton(text="🔘 Настроить кнопки", callback_data="editor_buttons")],
        [InlineKeyboardButton(text="👁 Предпросмотр", callback_data="editor_preview")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")],
    ])

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "editor_welcome")
async def editor_welcome(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "📝 <b>Изменение приветствия</b>\n"
        f"{'━' * 28}\n\n"
        "Отправьте новый текст приветствия.\n\n"
        "<b>Поддерживается:</b>\n"
        "• HTML-разметка: &lt;b&gt;жирный&lt;/b&gt;, &lt;i&gt;курсив&lt;/i&gt;, &lt;u&gt;подчёркнутый&lt;/u&gt;\n"
        "• &lt;code&gt;моноширинный&lt;/code&gt;\n"
        "• Премиум-эмодзи (просто вставьте)\n"
        "• Любые шрифты Unicode\n\n"
        "<i>Отправьте текст или /cancel для отмены</i>"
    )
    await state.set_state(EditorState.waiting_welcome_text)
    await callback.answer()


@router.message(EditorState.waiting_welcome_text)
async def process_welcome_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено")
        return

    # Берём html_text чтобы сохранить форматирование
    text = message.html_text or message.text or ""

    await db.set_setting("welcome_text", text)
    await db.add_log(ADMIN_ID, "Изменил приветствие")
    await state.clear()
    await message.answer(
        f"✅ <b>Приветствие обновлено!</b>\n\n<b>Новый текст:</b>\n{text}"
    )


@router.callback_query(F.data == "editor_buttons")
async def editor_buttons(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "🔘 <b>Настройка кнопок приветствия</b>\n"
        f"{'━' * 28}\n\n"
        "Отправьте кнопки в формате (каждая с новой строки):\n\n"
        "<code>Текст кнопки | ссылка</code>\n\n"
        "<b>Пример:</b>\n"
        "<code>📢 Наш канал | https://t.me/channel\n"
        "🌐 Сайт | https://example.com\n"
        "💬 Чат | https://t.me/chat</code>\n\n"
        "Отправьте <b>clear</b> чтобы убрать все кнопки\n"
        "Или /cancel для отмены"
    )
    await state.set_state(EditorState.waiting_welcome_buttons)
    await callback.answer()


@router.message(EditorState.waiting_welcome_buttons)
async def process_welcome_buttons(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено")
        return

    if message.text.strip().lower() == "clear":
        await db.set_setting("welcome_buttons", "")
        await state.clear()
        await message.answer("✅ Кнопки удалены")
        return

    lines = message.text.strip().split("\n")
    buttons = []
    errors = []

    for i, line in enumerate(lines, 1):
        parts = line.split("|")
        if len(parts) != 2:
            errors.append(f"Строка {i}: неверный формат")
            continue
        btn_text = parts[0].strip()
        btn_url = parts[1].strip()
        if not btn_text or not btn_url:
            errors.append(f"Строка {i}: пустое значение")
            continue
        if not btn_url.startswith("http"):
            errors.append(f"Строка {i}: ссылка должна начинаться с http")
            continue
        buttons.append({"text": btn_text, "url": btn_url})

    if errors:
        await message.answer("❌ <b>Ошибки:</b>\n" + "\n".join(errors))
        return

    await db.set_setting("welcome_buttons", json.dumps(buttons, ensure_ascii=False))
    await db.add_log(ADMIN_ID, "Обновил кнопки приветствия", f"{len(buttons)} кнопок")
    await state.clear()
    await message.answer(f"✅ Сохранено <b>{len(buttons)}</b> кнопок!")


@router.callback_query(F.data == "editor_preview")
async def editor_preview(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return

    welcome = await db.get_setting("welcome_text", "")
    buttons_json = await db.get_setting("welcome_buttons", "")

    if not welcome:
        welcome = "👋 <b>Добро пожаловать!</b>\n\n<i>Текст приветствия — заглушка.</i>"

    kb = None
    if buttons_json:
        try:
            btns = json.loads(buttons_json)
            rows = [[InlineKeyboardButton(text=b['text'], url=b['url'])] for b in btns]
            kb = InlineKeyboardMarkup(inline_keyboard=rows)
        except Exception:
            pass

    await bot.send_message(chat_id=ADMIN_ID, text=f"👁 <b>ПРЕДПРОСМОТР:</b>\n{'━' * 28}\n\n{welcome}", reply_markup=kb)
    await callback.answer("Предпросмотр отправлен")


# ==================== РАССЫЛКА ====================

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    total = await db.get_total_users()

    await callback.message.edit_text(
        f"📢 <b>Рассылка</b>\n{'━' * 28}\n\n"
        f"👥 Получателей: <b>{total}</b>\n\n"
        "Отправьте сообщение для рассылки.\n\n"
        "<b>Поддерживается:</b>\n"
        "• Текст с HTML-разметкой\n"
        "• Премиум-эмодзи\n"
        "• Фото с подписью\n"
        "• Любые шрифты\n\n"
        "<i>/cancel для отмены</i>"
    )
    await state.set_state(BroadcastState.waiting_content)
    await callback.answer()


@router.message(BroadcastState.waiting_content)
async def process_broadcast_content(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено")
        return

    # Сохраняем данные рассылки
    data = {}
    if message.photo:
        data['photo'] = message.photo[-1].file_id
        data['caption'] = message.html_text or message.caption or ""
        data['type'] = 'photo'
    else:
        data['text'] = message.html_text or message.text or ""
        data['type'] = 'text'

    await state.update_data(broadcast=data)
    total = await db.get_total_users()

    preview = data.get('caption', '') or data.get('text', '')
    short = preview[:200] + "..." if len(preview) > 200 else preview

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить всем", callback_data="broadcast_send")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")],
    ])

    await message.answer(
        f"📢 <b>Подтверждение рассылки</b>\n{'━' * 28}\n\n"
        f"📨 Тип: <b>{'Фото' if data['type'] == 'photo' else 'Текст'}</b>\n"
        f"👥 Получателей: <b>{total}</b>\n\n"
        f"<b>Превью:</b>\n{short}",
        reply_markup=kb
    )
    await state.set_state(BroadcastState.confirm)


@router.callback_query(F.data == "broadcast_cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена")
    await callback.answer()


@router.callback_query(F.data == "broadcast_send")
async def broadcast_send(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        return

    data = await state.get_data()
    broadcast = data.get('broadcast')
    await state.clear()

    if not broadcast:
        await callback.answer("Нет данных", show_alert=True)
        return

    users = await db.get_all_users()
    await callback.message.edit_text(f"📢 <b>Рассылка запущена...</b>\n\n👥 Отправляем {len(users)} пользователям...")
    await callback.answer()

    success = 0
    failed = 0

    for u in users:
        try:
            if broadcast['type'] == 'photo':
                await bot.send_photo(
                    chat_id=u['user_id'],
                    photo=broadcast['photo'],
                    caption=broadcast.get('caption', ''),
                    parse_mode="HTML"
                )
            else:
                await bot.send_message(
                    chat_id=u['user_id'],
                    text=broadcast['text'],
                    parse_mode="HTML"
                )
            success += 1
        except Exception:
            failed += 1

        await asyncio.sleep(0.05)

    await db.add_log(ADMIN_ID, "Рассылка", f"✅ {success} | ❌ {failed}")
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"📢 <b>Рассылка завершена!</b>\n{'━' * 28}\n\n"
            f"✅ Доставлено: {success}\n"
            f"❌ Не доставлено: {failed}\n"
            f"📊 Всего: {success + failed}"
        )
    )


# ==================== АНТИСПАМ ====================

@router.callback_query(F.data == "admin_antispam")
async def admin_antispam(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return

    current = await db.get_setting("antispam", "off")
    status = "🟢 Включен" if current == "on" else "🔴 Выключен"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔴 Выключить" if current == "on" else "🟢 Включить",
            callback_data="antispam_toggle"
        )],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")],
    ])

    await callback.message.edit_text(
        f"🛡 <b>Антиспам</b>\n{'━' * 28}\n\n"
        f"Статус: <b>{status}</b>\n\n"
        f"При включении пользователи могут отправлять\n"
        f"сообщения не чаще <b>1 раз в минуту</b>.\n"
        f"Они получат уведомление.",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data == "antispam_toggle")
async def antispam_toggle(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return

    current = await db.get_setting("antispam", "off")
    new_val = "off" if current == "on" else "on"
    await db.set_setting("antispam", new_val)
    await db.add_log(ADMIN_ID, f"Антиспам {'включен' if new_val == 'on' else 'выключен'}")

    # Оповещаем всех
    if new_val == "on":
        notify_text = "🛡 <b>Включен режим антиспам</b>\n\nСообщения можно отправлять не чаще 1 раза в минуту."
    else:
        notify_text = "✅ <b>Антиспам выключен</b>\n\nОграничения сняты."

    users = await db.get_all_users()
    for u in users:
        try:
            await bot.send_message(chat_id=u['user_id'], text=notify_text)
        except Exception:
            pass
        await asyncio.sleep(0.05)

    # Обновляем меню
    status = "🟢 Включен" if new_val == "on" else "🔴 Выключен"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔴 Выключить" if new_val == "on" else "🟢 Включить",
            callback_data="antispam_toggle"
        )],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")],
    ])

    await callback.message.edit_text(
        f"🛡 <b>Антиспам</b>\n{'━' * 28}\n\nСтатус: <b>{status}</b>\n\nПри включении — 1 сообщение в минуту.",
        reply_markup=kb
    )
    await callback.answer(f"Антиспам {'включен' if new_val == 'on' else 'выключен'}")


# ==================== ОТКЛЮЧЕНИЕ БОТА ====================

@router.callback_query(F.data == "admin_shutdown")
async def admin_shutdown(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    current = await db.get_setting("bot_enabled", "on")
    status = "🟢 Работает" if current == "on" else "🔴 Отключен"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔴 Отключить" if current == "on" else "🟢 Включить",
            callback_data="shutdown_toggle"
        )],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")],
    ])

    await callback.message.edit_text(
        f"🔴 <b>Управление ботом</b>\n{'━' * 28}\n\n"
        f"Статус: <b>{status}</b>\n\n"
        f"При отключении пользователи получат уведомление\n"
        f"и бот перестанет обрабатывать их сообщения.\n"
        f"Админ-панель продолжит работать.",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data == "shutdown_toggle")
async def shutdown_toggle(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return

    current = await db.get_setting("bot_enabled", "on")
    new_val = "off" if current == "on" else "on"
    await db.set_setting("bot_enabled", new_val)
    await db.add_log(ADMIN_ID, f"Бот {'выключен' if new_val == 'off' else 'включен'}")

    if new_val == "off":
        notify_text = "🔴 <b>Бот временно отключен</b>\n\nАдминистратор приостановил работу бота. Ожидайте включения."
    else:
        notify_text = "🟢 <b>Бот снова работает!</b>\n\nМожете продолжать пользоваться ботом."

    users = await db.get_all_users()
    for u in users:
        try:
            await bot.send_message(chat_id=u['user_id'], text=notify_text)
        except Exception:
            pass
        await asyncio.sleep(0.05)

    status = "🟢 Работает" if new_val == "on" else "🔴 Отключен"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔴 Отключить" if new_val == "on" else "🟢 Включить",
            callback_data="shutdown_toggle"
        )],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")],
    ])

    await callback.message.edit_text(
        f"🔴 <b>Управление ботом</b>\n{'━' * 28}\n\nСтатус: <b>{status}</b>",
        reply_markup=kb
    )
    await callback.answer(f"Бот {'отключен' if new_val == 'off' else 'включен'}")