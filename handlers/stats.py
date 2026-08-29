from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_ID
from database import db
from datetime import datetime

router = Router()


class SearchUserState(StatesGroup):
    waiting_for_user_id = State()


# ==================== КЛАВИАТУРЫ ====================

def stats_keyboard() -> InlineKeyboardMarkup:
    """Главное меню статистики"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Общая статистика ПЗ", callback_data="stats_users_general")],
        [InlineKeyboardButton(text="🎫 Статистика тикетов", callback_data="stats_tickets")],
        [InlineKeyboardButton(text="📝 Статистика заявок", callback_data="stats_verification")],
        [InlineKeyboardButton(text="🏆 ТОП пользователей", callback_data="stats_top")],
        [InlineKeyboardButton(text="📋 Последние действия", callback_data="stats_logs")],
        [InlineKeyboardButton(text="🔎 Подробно о ПЗ", callback_data="stats_user_search")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")],
    ])


def stats_top_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 ТОП по сообщениям", callback_data="stats_top_messages")],
        [InlineKeyboardButton(text="🎫 ТОП по тикетам", callback_data="stats_top_tickets")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stats")],
    ])


def back_to_stats() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к статистике", callback_data="admin_stats")],
    ])


def back_to_stats_top() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к ТОП", callback_data="stats_top")],
    ])


def user_detail_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎫 Тикеты этого ПЗ", callback_data=f"user_tickets_{user_id}")],
        [InlineKeyboardButton(text="📋 Действия этого ПЗ", callback_data=f"user_logs_{user_id}")],
        [InlineKeyboardButton(text="◀️ Назад к статистике", callback_data="admin_stats")],
    ])


# ==================== ПРОВЕРКА АДМИНА ====================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ==================== ГЛАВНАЯ СТАТИСТИКА ====================

@router.callback_query(F.data == "admin_stats")
async def show_stats_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await state.clear()
    
    # Собираем общую сводку
    total_users = await db.get_total_users()
    active_today = await db.get_active_users_today()
    new_today = await db.get_new_users_today()
    tickets = await db.get_tickets_stats()
    logs_count = await db.get_logs_count()
    
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    text = (
        f"📊 <b>Статистика бота</b>\n"
        f"<i>Обновлено: {now}</i>\n"
        f"{'━' * 28}\n\n"
        f"👥 <b>Пользователей (ПЗ):</b> {total_users}\n"
        f"🟢 Активных сегодня: {active_today}\n"
        f"🆕 Новых сегодня: {new_today}\n\n"
        f"🎫 <b>Тикеты:</b> {tickets['total']}\n"
        f"   🟡 Открытые: {tickets['open']}\n"
        f"   🔵 В работе: {tickets['in_progress']}\n"
        f"   🟢 Решённые: {tickets['resolved']}\n\n"
        f"📋 Всего записей в логах: {logs_count}\n"
        f"{'━' * 28}\n\n"
        f"<i>Выберите раздел для подробностей 👇</i>"
    )
    
    await callback.message.edit_text(text, reply_markup=stats_keyboard())
    await callback.answer()


# ==================== ОБЩАЯ СТАТИСТИКА ПЗ ====================

@router.callback_query(F.data == "stats_users_general")
async def stats_users_general(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    total = await db.get_total_users()
    active_today = await db.get_active_users_today()
    new_today = await db.get_new_users_today()
    banned = await db.get_banned_users()
    total_messages = await db.get_total_messages()
    with_warnings = await db.get_users_with_warnings()
    total_warnings = await db.get_total_warnings()
    
    # Роли
    role_user = await db.get_users_by_role("user")
    role_mod = await db.get_users_by_role("moderator")
    role_vip = await db.get_users_by_role("vip")
    role_admin = await db.get_users_by_role("admin")
    
    # Средняя активность
    avg_messages = round(total_messages / total, 1) if total > 0 else 0
    
    text = (
        f"👥 <b>Подробная статистика ПЗ</b>\n"
        f"{'━' * 28}\n\n"
        f"📌 <b>Общее количество:</b> {total}\n"
        f"🟢 Активных сегодня: {active_today}\n"
        f"🆕 Новых сегодня: {new_today}\n"
        f"🚫 Забанено: {banned}\n\n"
        f"💬 <b>Сообщения:</b>\n"
        f"   Всего сообщений: {total_messages}\n"
        f"   Среднее на ПЗ: {avg_messages}\n\n"
        f"⚠️ <b>Предупреждения:</b>\n"
        f"   ПЗ с предупреждениями: {with_warnings}\n"
        f"   Всего предупреждений: {total_warnings}\n\n"
        f"🏷 <b>По ролям:</b>\n"
        f"   👤 Пользователь: {role_user}\n"
        f"   🛡 Модератор: {role_mod}\n"
        f"   ⭐ VIP: {role_vip}\n"
        f"   👑 Админ: {role_admin}\n"
    )
    
    await callback.message.edit_text(text, reply_markup=back_to_stats())
    await callback.answer()


# ==================== СТАТИСТИКА ТИКЕТОВ ====================

@router.callback_query(F.data == "stats_tickets")
async def stats_tickets(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    t = await db.get_tickets_stats()
    
    # Процент решённых
    resolved_pct = round((t['resolved'] + t['closed']) / t['total'] * 100, 1) if t['total'] > 0 else 0
    
    text = (
        f"🎫 <b>Подробная статистика тикетов</b>\n"
        f"{'━' * 28}\n\n"
        f"📌 <b>Всего тикетов:</b> {t['total']}\n\n"
        f"<b>По статусам:</b>\n"
        f"   🟡 Открытые: {t['open']}\n"
        f"   🔵 В работе: {t['in_progress']}\n"
        f"   🟢 Решённые: {t['resolved']}\n"
        f"   ⚪ Закрытые: {t['closed']}\n"
        f"   🔴 Отклонённые: {t['rejected']}\n\n"
        f"<b>По приоритетам:</b>\n"
        f"   ⬜ Низкий: {t['low']}\n"
        f"   🟨 Нормальный: {t['normal']}\n"
        f"   🟧 Высокий: {t['high']}\n"
        f"   🟥 Критический: {t['critical']}\n\n"
        f"<b>За сегодня:</b>\n"
        f"   📥 Создано: {t['today_created']}\n"
        f"   📤 Закрыто: {t['today_closed']}\n\n"
        f"📈 Процент решённых: {resolved_pct}%\n"
        f"⭐ Средний рейтинг: {t['avg_rating']}/5\n"
    )
    
    await callback.message.edit_text(text, reply_markup=back_to_stats())
    await callback.answer()


# ==================== СТАТИСТИКА ЗАЯВОК ====================

@router.callback_query(F.data == "stats_verification")
async def stats_verification(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    v = await db.get_verification_stats()
    
    approved_pct = round(v['approved'] / v['total'] * 100, 1) if v['total'] > 0 else 0
    
    text = (
        f"📝 <b>Статистика заявок на проверку</b>\n"
        f"{'━' * 28}\n\n"
        f"📌 <b>Всего заявок:</b> {v['total']}\n\n"
        f"   ⏳ Ожидают: {v['pending']}\n"
        f"   ✅ Одобрено: {v['approved']}\n"
        f"   ❌ Отклонено: {v['denied']}\n\n"
        f"📈 Процент одобрения: {approved_pct}%\n"
    )
    
    await callback.message.edit_text(text, reply_markup=back_to_stats())
    await callback.answer()


# ==================== ТОП ПОЛЬЗОВАТЕЛЕЙ ====================

@router.callback_query(F.data == "stats_top")
async def stats_top(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    text = (
        f"🏆 <b>ТОП пользователей</b>\n"
        f"{'━' * 28}\n\n"
        f"Выберите категорию рейтинга 👇"
    )
    
    await callback.message.edit_text(text, reply_markup=stats_top_keyboard())
    await callback.answer()


@router.callback_query(F.data == "stats_top_messages")
async def stats_top_messages(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    users = await db.get_top_users_by_messages(10)
    
    text = f"💬 <b>ТОП-10 по сообщениям</b>\n{'━' * 28}\n\n"
    
    if not users:
        text += "<i>Пока нет данных</i>"
    else:
        medals = ["🥇", "🥈", "🥉"]
        for i, u in enumerate(users):
            medal = medals[i] if i < 3 else f"  {i+1}."
            name = u['first_name'] or u['username'] or str(u['user_id'])
            text += f"{medal} <b>{name}</b> — {u['messages_count']} сообщ.\n"
            text += f"      <code>ID: {u['user_id']}</code>\n"
    
    await callback.message.edit_text(text, reply_markup=back_to_stats_top())
    await callback.answer()


@router.callback_query(F.data == "stats_top_tickets")
async def stats_top_tickets(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    users = await db.get_top_users_by_tickets(10)
    
    text = f"🎫 <b>ТОП-10 по тикетам</b>\n{'━' * 28}\n\n"
    
    if not users:
        text += "<i>Пока нет данных</i>"
    else:
        medals = ["🥇", "🥈", "🥉"]
        for i, u in enumerate(users):
            medal = medals[i] if i < 3 else f"  {i+1}."
            name = u['first_name'] or u['username'] or str(u['user_id'])
            text += f"{medal} <b>{name}</b> — {u['tickets_created']} тикетов\n"
            text += f"      <code>ID: {u['user_id']}</code>\n"
    
    await callback.message.edit_text(text, reply_markup=back_to_stats_top())
    await callback.answer()


# ==================== ПОСЛЕДНИЕ ДЕЙСТВИЯ ====================

@router.callback_query(F.data == "stats_logs")
async def stats_logs(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    logs = await db.get_recent_logs(15)
    
    text = f"📋 <b>Последние 15 действий</b>\n{'━' * 28}\n\n"
    
    if not logs:
        text += "<i>Пока нет записей</i>"
    else:
        for log in logs:
            time_str = log['timestamp'][11:16] if len(log['timestamp']) > 11 else log['timestamp']
            date_str = log['timestamp'][:10] if len(log['timestamp']) > 10 else ""
            text += (
                f"🕐 <code>{date_str} {time_str}</code>\n"
                f"   👤 ID: <code>{log['user_id']}</code>\n"
                f"   📌 {log['action']}\n"
            )
            if log['details']:
                text += f"   💬 {log['details']}\n"
            text += "\n"
    
    await callback.message.edit_text(text, reply_markup=back_to_stats())
    await callback.answer()


# ==================== ПОИСК ПЗ ПО ID ====================

@router.callback_query(F.data == "stats_user_search")
async def stats_user_search(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Показать всех ПЗ", callback_data="stats_all_users")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_stats")],
    ])
    
    await callback.message.edit_text(
        "🔎 <b>Поиск пользователя</b>\n"
        f"{'━' * 28}\n\n"
        "Введите <b>ID пользователя</b> для просмотра подробной информации:\n\n"
        "<i>Или нажмите кнопку ниже чтобы увидеть весь список</i>",
        reply_markup=kb
    )
    await state.set_state(SearchUserState.waiting_for_user_id)
    await callback.answer()


@router.callback_query(F.data == "stats_all_users")
async def stats_all_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    users = await db.get_all_users()
    
    text = f"📋 <b>Все ПЗ бота</b>\n{'━' * 28}\n\n"
    
    if not users:
        text += "<i>Пользователей нет</i>"
    else:
        for u in users[:30]:  # Ограничим 30
            name = u['first_name'] or u['username'] or "Без имени"
            banned_mark = " 🚫" if u['is_banned'] else ""
            warn_mark = f" ⚠️{u['warnings']}" if u['warnings'] > 0 else ""
            role_icon = {"user": "👤", "moderator": "🛡", "vip": "⭐", "admin": "👑"}.get(u['role'], "👤")
            
            text += (
                f"{role_icon} <b>{name}</b>{banned_mark}{warn_mark}\n"
                f"   ID: <code>{u['user_id']}</code> | 💬 {u['messages_count']}\n"
            )
        
        if len(users) > 30:
            text += f"\n<i>...и ещё {len(users) - 30} ПЗ</i>"
    
    await callback.message.edit_text(text, reply_markup=back_to_stats())
    await callback.answer()


@router.message(SearchUserState.waiting_for_user_id)
async def process_user_id_search(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    text_input = message.text.strip()
    
    if not text_input.isdigit():
        await message.answer(
            "❌ Введите числовой ID пользователя.\n"
            "Попробуйте ещё раз или нажмите /admin для отмены."
        )
        return
    
    user_id = int(text_input)
    user = await db.search_user_by_id(user_id)
    
    if not user:
        await message.answer(
            f"❌ Пользователь с ID <code>{user_id}</code> не найден.\n"
            "Попробуйте другой ID.",
            reply_markup=back_to_stats()
        )
        return
    
    await state.clear()
    
    # Формируем детальную карточку
    name = f"{user['first_name']} {user['last_name']}".strip() or "Не указано"
    username = f"@{user['username']}" if user['username'] else "Не указан"
    role_names = {"user": "👤 Пользователь", "moderator": "🛡 Модератор", "vip": "⭐ VIP", "admin": "👑 Админ"}
    role_text = role_names.get(user['role'], user['role'])
    banned_text = "🚫 Да" if user['is_banned'] else "✅ Нет"
    ban_reason = user['ban_reason'] if user['ban_reason'] else "—"
    notes = user['notes'] if user['notes'] else "—"
    
    # Расчёт дней с регистрации
    try:
        join_dt = datetime.strptime(user['join_date'], "%Y-%m-%d %H:%M:%S")
        days_since = (datetime.now() - join_dt).days
        join_display = f"{user['join_date']} ({days_since} дн.)"
    except:
        join_display = user['join_date'] or "Неизвестно"
    
    # Расчёт неактивности
    try:
        last_dt = datetime.strptime(user['last_active'], "%Y-%m-%d %H:%M:%S")
        inactive_hours = round((datetime.now() - last_dt).total_seconds() / 3600, 1)
        if inactive_hours < 1:
            inactive_text = "Менее часа назад"
        elif inactive_hours < 24:
            inactive_text = f"{inactive_hours} ч. назад"
        else:
            inactive_text = f"{int(inactive_hours // 24)} дн. назад"
        last_display = f"{user['last_active']} ({inactive_text})"
    except:
        last_display = user['last_active'] or "Неизвестно"
    
    text = (
        f"🔎 <b>Карточка ПЗ</b>\n"
        f"{'━' * 28}\n\n"
        f"🆔 <b>ID:</b> <code>{user['user_id']}</code>\n"
        f"👤 <b>Имя:</b> {name}\n"
        f"📛 <b>Username:</b> {username}\n"
        f"🏷 <b>Роль:</b> {role_text}\n\n"
        f"📅 <b>Регистрация:</b> {join_display}\n"
        f"🕐 <b>Последняя активность:</b> {last_display}\n\n"
        f"💬 <b>Сообщений:</b> {user['messages_count']}\n"
        f"🎫 <b>Тикетов создано:</b> {user['tickets_created']}\n"
        f"✅ <b>Тикетов решено:</b> {user['tickets_resolved']}\n\n"
        f"⚠️ <b>Предупреждений:</b> {user['warnings']}\n"
        f"🚫 <b>Бан:</b> {banned_text}\n"
        f"📝 <b>Причина бана:</b> {ban_reason}\n\n"
        f"📌 <b>Заметки:</b> {notes}\n"
    )
    
    await message.answer(text, reply_markup=user_detail_keyboard(user['user_id']))


# ==================== ТИКЕТЫ КОНКРЕТНОГО ПЗ ====================

@router.callback_query(F.data.startswith("user_tickets_"))
async def user_tickets_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    user_id = int(callback.data.replace("user_tickets_", ""))
    
    import aiosqlite
    from database.db import DB_PATH
    
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM tickets WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
            (user_id,)
        )
        tickets = [dict(r) for r in await cursor.fetchall()]
    
    text = f"🎫 <b>Тикеты ПЗ</b> <code>{user_id}</code>\n{'━' * 28}\n\n"
    
    if not tickets:
        text += "<i>Тикетов не найдено</i>"
    else:
        status_icons = {
            "open": "🟡", "in_progress": "🔵",
            "resolved": "🟢", "closed": "⚪", "rejected": "🔴"
        }
        priority_icons = {
            "low": "⬜", "normal": "🟨", "high": "🟧", "critical": "🟥"
        }
        
        for t in tickets:
            s_icon = status_icons.get(t['status'], "⚪")
            p_icon = priority_icons.get(t['priority'], "🟨")
            text += (
                f"{s_icon} <b>#{t['ticket_id']}</b> — {t['subject'] or 'Без темы'}\n"
                f"   {p_icon} Приоритет: {t['priority']} | {t['status']}\n"
                f"   📅 {t['created_at']}\n\n"
            )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к карточке", callback_data=f"back_to_user_{user_id}")],
    ])
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ==================== ЛОГИ КОНКРЕТНОГО ПЗ ====================

@router.callback_query(F.data.startswith("user_logs_"))
async def user_logs_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    user_id = int(callback.data.replace("user_logs_", ""))
    
    import aiosqlite
    from database.db import DB_PATH
    
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM action_logs WHERE user_id = ? ORDER BY timestamp DESC LIMIT 15",
            (user_id,)
        )
        logs = [dict(r) for r in await cursor.fetchall()]
    
    text = f"📋 <b>Действия ПЗ</b> <code>{user_id}</code>\n{'━' * 28}\n\n"
    
    if not logs:
        text += "<i>Действий не найдено</i>"
    else:
        for log in logs:
            text += (
                f"🕐 <code>{log['timestamp']}</code>\n"
                f"   📌 {log['action']}\n"
            )
            if log['details']:
                text += f"   💬 {log['details']}\n"
            text += "\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к карточке", callback_data=f"back_to_user_{user_id}")],
    ])
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ==================== ВОЗВРАТ К КАРТОЧКЕ ПЗ ====================

@router.callback_query(F.data.startswith("back_to_user_"))
async def back_to_user_card(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    user_id = int(callback.data.replace("back_to_user_", ""))
    user = await db.search_user_by_id(user_id)
    
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    
    name = f"{user['first_name']} {user['last_name']}".strip() or "Не указано"
    username = f"@{user['username']}" if user['username'] else "Не указан"
    role_names = {"user": "👤 Пользователь", "moderator": "🛡 Модератор", "vip": "⭐ VIP", "admin": "👑 Админ"}
    role_text = role_names.get(user['role'], user['role'])
    banned_text = "🚫 Да" if user['is_banned'] else "✅ Нет"
    ban_reason = user['ban_reason'] if user['ban_reason'] else "—"
    notes = user['notes'] if user['notes'] else "—"
    
    try:
        join_dt = datetime.strptime(user['join_date'], "%Y-%m-%d %H:%M:%S")
        days_since = (datetime.now() - join_dt).days
        join_display = f"{user['join_date']} ({days_since} дн.)"
    except:
        join_display = user['join_date'] or "Неизвестно"
    
    try:
        last_dt = datetime.strptime(user['last_active'], "%Y-%m-%d %H:%M:%S")
        inactive_hours = round((datetime.now() - last_dt).total_seconds() / 3600, 1)
        if inactive_hours < 1:
            inactive_text = "Менее часа назад"
        elif inactive_hours < 24:
            inactive_text = f"{inactive_hours} ч. назад"
        else:
            inactive_text = f"{int(inactive_hours // 24)} дн. назад"
        last_display = f"{user['last_active']} ({inactive_text})"
    except:
        last_display = user['last_active'] or "Неизвестно"
    
    text = (
        f"🔎 <b>Карточка ПЗ</b>\n"
        f"{'━' * 28}\n\n"
        f"🆔 <b>ID:</b> <code>{user['user_id']}</code>\n"
        f"👤 <b>Имя:</b> {name}\n"
        f"📛 <b>Username:</b> {username}\n"
        f"🏷 <b>Роль:</b> {role_text}\n\n"
        f"📅 <b>Регистрация:</b> {join_display}\n"
        f"🕐 <b>Последняя активность:</b> {last_display}\n\n"
        f"💬 <b>Сообщений:</b> {user['messages_count']}\n"
        f"🎫 <b>Тикетов создано:</b> {user['tickets_created']}\n"
        f"✅ <b>Тикетов решено:</b> {user['tickets_resolved']}\n\n"
        f"⚠️ <b>Предупреждений:</b> {user['warnings']}\n"
        f"🚫 <b>Бан:</b> {banned_text}\n"
        f"📝 <b>Причина бана:</b> {ban_reason}\n\n"
        f"📌 <b>Заметки:</b> {notes}\n"
    )
    
    await callback.message.edit_text(text, reply_markup=user_detail_keyboard(user_id))
    await callback.answer()