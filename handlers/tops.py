import html
import json
import os
import aiosqlite
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatType

from database import db

ADMIN_ID = int(os.getenv("ADMIN_ID", "1269379743"))
TGK_LINK = os.getenv("TGK_LINK", "https://t.me/Checking_the_angel")

router = Router()


# ==================== СОСТОЯНИЯ ====================

class VerifyState(StatesGroup):
    waiting_tag = State()
    waiting_tgk_name = State()
    waiting_tgk_link = State()


class PostCheckState(StatesGroup):
    waiting_photos = State()
    waiting_description = State()
    waiting_rating = State()
    waiting_bot_link = State()
    waiting_tgk_link = State()
    waiting_tgk_choice = State()
    waiting_passed = State()
    confirm = State()


class AnketaState(StatesGroup):
    answering = State()
    confirming = State()


class TopNumberState(StatesGroup):
    waiting_number = State()


# ==================== УТИЛИТЫ ====================

def tgk_username_from_link(link: str) -> str:
    """Достаёт имя ТГК из ссылки вида https://t.me/name"""
    link = (link or '').strip().rstrip('/')
    if 't.me/' in link:
        return link.split('t.me/')[-1] or link
    return link.lstrip('@')


def normalize_bot(bot: str) -> str:
    bot = (bot or '').strip().lstrip('@')
    return bot


# ───────────────────────── ПРЕМИУМ / АНИМИРОВАННЫЕ ЭМОДЗИ ─────────────────────────
# Telegram позволяет вставлять кастомные (премиум/анимированные) эмодзи прямо в HTML-текст
# через плейсхолдер: {#ID_НАБОРА_ЭМОДЗИ#}. Анимация видна получателям с Premium.
#
# ID набора эмодзи можно получить из любого набора, например:
#   • https://t.me/addemoji/ответы_тг  -> и взять ID из ссылки на эмодзи;
# Если ID пустой или Telegram не примет эмодзи — бот мягко откатится на обычные эмодзи
# (см. send_check_card), так что ничего не «упадёт».
PREMIUM_ENABLED = True

PREMIUM_EMOJI = {
    # {ключ: ID_эмодзи (custom_emoji_id)}
    "checker": "5257652165138947090",  # 🫂 / проверяющие
    "bot":      "5257652165138947090",  # 🤖 / бот на проверке
    "desc":     "5257652165138947090",  # 📝 / описание
    "rating":   "5257652165652564938",  # ⭐ / оценка
}


def _em(key: str, plain: str) -> str:
    """Возвращает HTML <tg-emoji> с кастомным эмодзи, если он задан, иначе обычный эмодзи.

    Telegram сам подставит кастомный (премиум/анимированный) эмодзи вместо тега.
    Если подставить не получается — бот мягко откатится на обычные (см. send_check_card).
    """
    if not PREMIUM_ENABLED:
        return plain
    eid = PREMIUM_EMOJI.get(key)
    return f'<tg-emoji emoji-id="{str(eid)}">{plain}</tg-emoji>' if eid else plain


# ───────────────────────── УТИЛИТЫ ПО ССЫЛКАМ ─────────────────────────
def to_https_link(raw) -> str:
    """Приводит ссылку к валидному HTTP(S) URL для inline-кнопок.

    В БД ссылку на бота/ТГК могли сохранить как '@username', 'username' или
    't.me/username' — Telegram не принимает такое в url= кнопки, поэтому
    нормализуем до полной https://ссылки.
    """
    if not raw:
        return ''
    link = str(raw).strip()
    if not link:
        return ''
    if link.startswith("http://") or link.startswith("https://"):
        return link
    frag = link.lstrip('@').rstrip('/')
    if frag.startswith("t.me/"):
        return "https://" + frag
    if frag.startswith("telegram.me/"):
        return "https://telegram.me/" + frag[len("telegram.me/"):]
    return f"https://t.me/{frag}"


async def ensure_user_accessible(message: Message) -> bool:
    """Проверка бана. Возвращает True, если можно продолжать."""
    user = await db.get_user(message.from_user.id)
    if user and user.get('is_banned'):
        await message.answer(f"🚫 <b>Вы заблокированы</b>\n\nПричина: {user['ban_reason'] or '—'}")
        return False
    return True


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="tops_cancel")],
    ])


def top_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Проверки check-up", callback_data="top_checkup")],
        [InlineKeyboardButton(text="📊 Другие ТГК", callback_data="top_other")],
        [InlineKeyboardButton(text="🏆 Рейтинг ТГК", callback_data="top_rating")],
    ])


def build_check_card(check: dict, premium: bool = True) -> str:
    bot = normalize_bot(check.get('bot_username') or check.get('bot_link') or '—')
    if bot and bot != '—':
        bot = f"@{bot}"
    rating = html.escape(str(check.get('rating') or '—'))
    desc = html.escape(str(check.get('description') or '—'))
    tgk = check.get('tgk_link') or ''
    check_id = check.get('check_id') or ''
    passed = check.get('passed')

    c_emoji, b_emoji, r_emoji = ('🌐', '🤖', '⭐')
    if premium:
        c_emoji, b_emoji, r_emoji = _em('checker', '🌐'), _em('bot', '🤖'), _em('rating', '⭐')

    checker = f"@{tgk_username_from_link(tgk)}" if tgk else '—'
    pass_line = '✅ <b>Бот прошёл проверку</b>' if passed in (1, '1', True) else '❌ <b>Бот не прошёл проверку</b>'

    card = (
        f"{c_emoji} <b>Проверяющие:</b> <i>{checker}</i>\n"
        f"{b_emoji} <b>Бот на проверке:</b> <b>{bot}</b>\n"
        f"<code>{'━' * 28}</code>\n\n"
        f"<blockquote>{desc}</blockquote>\n\n"
        f"{r_emoji} <b>Оценка:</b> <code>{rating}</code>\n"
        f"{pass_line}\n"
    )
    if check_id:
        card += f"🆔 <b>ID проверки:</b> <code>#{check_id}</code>"
    return card


def build_check_buttons(check: dict) -> InlineKeyboardMarkup:
    rows = []
    bot_link = to_https_link(check.get('bot_link'))
    if bot_link:
        rows.append([InlineKeyboardButton(text="🤖 Перейти к боту", url=bot_link)])
    tgk = to_https_link(check.get('tgk_link'))
    if tgk:
        rows.append([InlineKeyboardButton(text="📢 Перейти к проверяющим", url=tgk)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_check_card(bot: Bot, chat_id: int, check: dict):
    """Отправляет пользователю карточку проверки (фото + текст + оценка)."""
    kb = build_check_buttons(check)
    try:
        photos = json.loads(check.get('photos') or '[]')
    except Exception:
        photos = []
    if photos:
        try:
            media = [InputMediaPhoto(media=p) for p in photos]
            await bot.send_media_group(chat_id=chat_id, media=media)
        except Exception:
            try:
                await bot.send_message(chat_id=chat_id, text="🖼 [фото недоступны]")
            except Exception:
                pass

    # Премиум-версия; если Telegram не принял кастомные эмодзи — мягкий откат.
    try:
        await bot.send_message(chat_id=chat_id, text=build_check_card(check, premium=True), reply_markup=kb)
        return
    except Exception:
        pass
    try:
        await bot.send_message(chat_id=chat_id, text=build_check_card(check, premium=False), reply_markup=kb)
        return
    except Exception:
        pass
    # Самый простой вариант — без сложного HTML, чтобы карточка всё равно дошла.
    try:
        tgk = str(check.get('tgk_link') or '')
        checker = f"@{tgk_username_from_link(tgk)}" if tgk else '—'
        bot = normalize_bot(check.get('bot_username') or check.get('bot_link') or '—')
        passed = check.get('passed')
        pass_line = '✅ Бот прошёл' if passed in (1, '1', True) else '❌ Бот не прошёл'
        cid = check.get('check_id') or ''
        plain = (
            f"🎟 <b>Проверка</b>\n"
            f"{'━' * 28}\n\n"
            f"🌐 Проверяющие: {checker}\n"
            f"🤖 Бот на проверке: @{bot}\n"
            f"{'━' * 28}\n\n"
            f"{html.escape(str(check.get('description') or '—'))}\n\n"
            f"⭐ Оценка: {html.escape(str(check.get('rating') or '—'))}\n"
            f"{pass_line}\n"
            f"🆔 ID проверки: #{cid}"
        )
        await bot.send_message(chat_id=chat_id, text=plain, reply_markup=kb)
    except Exception:
        pass
# ==================== КНОПКА «ТОПЫ» ====================

@router.message(F.text == "🏆 Топы", F.chat.type == ChatType.PRIVATE)
async def cmd_tops(message: Message, state: FSMContext):
    if not await ensure_user_accessible(message):
        return
    await state.clear()
    await message.answer("Какой топ показать?", reply_markup=top_menu_kb())


# ==================== ТОП «ДРУГИЕ ТГК» ====================

@router.callback_query(F.data == "top_other")
async def top_other(callback: CallbackQuery):
    summary = await db.get_bots_summary("other")
    text = (
        f"🏆 <b>Топ «Другие ТГК»</b>\n"
        f"{'━' * 28}\n\n"
    )
    if not summary:
        text += "<i>Пока нет проверок.</i>"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="tops_menu")]
        ])
    else:
        rows = []
        for b in summary:
            bot = f"@{normalize_bot(b['bot_username'])}"
            text += f"🤖 <b>{bot}</b> — {b['cnt']}\n"
            rows.append([InlineKeyboardButton(
                text=f"{bot} — {b['cnt']}",
                callback_data=f"bot_other_{b['bot_username']}"
            )])
        rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="tops_menu")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("bot_other_"))
async def bot_card_other(callback: CallbackQuery, state: FSMContext):
    username = callback.data.replace("bot_other_", "")
    checks = await db.get_checks_by_bot(username, "other")
    if not checks:
        await callback.answer("Нет проверок", show_alert=True)
        return

    await state.set_data({"username": username, "category": "other"})
    await state.set_state(TopNumberState.waiting_number)

    text = (
        f"📦 <b>Бот: @{normalize_bot(username)}</b>\n"
        f"Проверок: {len(checks)}\n"
        f"{'━' * 28}\n\n"
        f"<b>Проверки (выберите цифру):</b>\n"
    )
    rows = []
    for i, ch in enumerate(checks, start=1):
        tg = tgk_username_from_link(ch['tgk_link'])
        text += f"{i}. {tg or f'ТГК {i}'} — #{ch['check_id']}\n"
        rows.append([InlineKeyboardButton(
            text=f"{i} — {tg or f'ТГК {i}'} — #{ch['check_id']}",
            callback_data=f"open_check_{ch['check_id']}"
        )])

    text += f"\nПришлите <b>цифру</b> проверки, чтобы посмотреть её 👇"
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="top_other")])

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.message(TopNumberState.waiting_number, F.chat.type == ChatType.PRIVATE)
async def number_chosen(message: Message, state: FSMContext):
    if not message.text or not message.text.strip().isdigit():
        await message.answer("❌ Отправьте цифру из списка проверок.")
        return
    num = int(message.text.strip())
    data = await state.get_data()
    checks = await db.get_checks_by_bot(data['username'], data.get('category', 'other'))
    if num < 1 or num > len(checks):
        await message.answer("❌ Такой проверки нет. Отправьте цифру из списка.")
        return
    check = checks[num - 1]
    await state.clear()
    await send_check_card(message.bot, message.chat.id, check)


@router.callback_query(F.data.startswith("open_check_"))
async def open_check(callback: CallbackQuery):
    try:
        check_id = int(callback.data.replace("open_check_", ""))
    except ValueError:
        await callback.answer()
        return
    ch = await db.get_check_by_id(check_id)
    if not ch:
        await callback.answer("Не найдено", show_alert=True)
        return
    await callback.answer()
    await send_check_card(callback.bot, callback.message.chat.id, ch)


# ==================== ТОП «ПРОверКИ CHECK-UP» ====================

@router.callback_query(F.data == "top_checkup")
async def top_checkup(callback: CallbackQuery):
    summary = await db.get_bots_summary("checkup")
    text = (
        f"🔍 <b>Топ «Проверки check-up»</b>\n"
        f"{'━' * 28}\n\n"
        f"<i>Боты, проверенные нашей командой:</i>\n\n"
    )
    if not summary:
        text += "<i>Пока нет проверок.</i>"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="tops_menu")]
        ])
    else:
        rows = []
        for b in summary:
            bot = f"@{normalize_bot(b['bot_username'])}"
            text += f"🤖 <b>{bot}</b>\n"
            rows.append([InlineKeyboardButton(
                text=f"🤖 {bot}",
                callback_data=f"chk_bot_{b['bot_username']}"
            )])
        rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="tops_menu")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("chk_bot_"))
async def checkup_bot(callback: CallbackQuery):
    username = callback.data.replace("chk_bot_", "")
    checks = await db.get_checks_by_bot(username, "checkup")
    if not checks:
        await callback.answer("Нет проверок", show_alert=True)
        return
    # сразу показываем самую свежую карточку проверки
    check = checks[-1]
    await callback.answer()
    await send_check_card(callback.bot, callback.message.chat.id, check)


@router.callback_query(F.data == "tops_menu")
async def tops_menu(callback: CallbackQuery):
    await callback.message.edit_text("Какой топ показать?", reply_markup=top_menu_kb())
    await callback.answer()


# ==================== РЕЙТИНГ ТГК ====================

@router.callback_query(F.data == "top_rating")
async def tops_rating(callback: CallbackQuery, state: FSMContext):
    rows = await db.get_tgk_rating(30)
    text = (
        "🏆 <b>Рейтинг проверяющих ТГК</b>\n"
        f"<code>{'━' * 28}</code>\n\n"
    )
    if not rows:
        text += "<i>Пока нет данных для рейтинга.</i>"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="tops_menu")]
        ])
    else:
        line_buttons = []
        for i, r in enumerate(rows, start=1):
            total = int(r.get('total') or 0)
            passed = int(r.get('passed') or 0)
            failed = total - passed
            if passed > failed:
                color = "🟢"      # в основном проверки пройдены
            elif passed < failed:
                color = "🔴"      # в основном не пройдены
            else:
                color = "🟡"      # примерно поровну
            name = r.get('tgk_title') or tgk_username_from_link(r['tgk_link']) or '—'
            text += f"{i}. {color} <b>{html.escape(str(name))}</b> — {total} проверок\n"
            line_buttons.append([InlineKeyboardButton(
                text=f"{i}. {color} {str(name)[:40]}",
                callback_data=f"rtg_open_{i}"
            )])
        line_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="tops_menu")])
        kb = InlineKeyboardMarkup(inline_keyboard=line_buttons)

    await state.clear()
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("rtg_open_"))
async def rtg_open(callback: CallbackQuery, state: FSMContext):
    try:
        idx = int(callback.data.replace("rtg_open_", ""))
    except ValueError:
        await callback.answer()
        return
    rows = await db.get_tgk_rating(60)
    await state.clear()
    if idx < 1 or idx > len(rows):
        await callback.answer("Нет данных", show_alert=True)
        return
    checks = await db.get_checks_by_tgk_link(rows[idx - 1]['tgk_link'])
    if not checks:
        await callback.answer("Нет проверок", show_alert=True)
        return
    await callback.answer()
    await send_check_card(callback.bot, callback.message.chat.id, checks[0])


# ==================== ОТМЕНА ====================

@router.callback_query(F.data == "tops_cancel")
async def tops_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()
# ==================== ВЕРИФИКАЦИЯ (ПРОВЕРЯЮЩИЕ) ====================

@router.callback_query(F.data == "profile_verify")
async def profile_verify(callback: CallbackQuery, state: FSMContext):
    user = await db.get_user(callback.from_user.id)
    if user and user.get('is_verified'):
        await callback.answer("✅ Вы уже верифицированы!", show_alert=True)
        return
    pending = await db.get_pending_checker_request_by_user(callback.from_user.id)
    if pending:
        await callback.answer("⚠️ У вас уже есть заявка на верификацию!", show_alert=True)
        return
    await state.set_state(VerifyState.waiting_tag)
    await callback.message.edit_text(
        "🔍 <b>Верификация</b>\n"
        f"{'━' * 28}\n\n"
        "<b>Шаг 1 из 3</b>\nВведите ваш <b>тег</b>:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@router.message(VerifyState.waiting_tag, F.chat.type == ChatType.PRIVATE)
async def verify_tag(message: Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
        return
    await state.update_data(tag=message.text.strip())
    await state.set_state(VerifyState.waiting_tgk_name)
    await message.answer(
        "<b>Шаг 2 из 3</b>\n\nВведите <b>название ТГК проверок</b>:",
        reply_markup=cancel_kb()
    )


@router.message(VerifyState.waiting_tgk_name, F.chat.type == ChatType.PRIVATE)
async def verify_tgk_name(message: Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
        return
    await state.update_data(tgk_name=message.text.strip())
    await state.set_state(VerifyState.waiting_tgk_link)
    await message.answer(
        "<b>Шаг 3 из 3</b>\n\nОтправьте <b>ссылку на ваш ТГК проверок</b> (пример: https://t.me/check)",
        reply_markup=cancel_kb()
    )


@router.message(VerifyState.waiting_tgk_link, F.chat.type == ChatType.PRIVATE)
async def verify_tgk_link(message: Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
        return
    await state.update_data(tgk_link=message.text.strip())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я добавил бота в ТГК", callback_data="verify_bound")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="tops_cancel")],
    ])
    await message.answer(
        "🔗 <b>Привязка ТГК</b>\n"
        f"{'━' * 28}\n\n"
        "1️⃣ Добавьте этого бота в ваш ТГК как администратора.\n"
        "2️⃣ Нажмите кнопку «Я добавил бота в ТГК» ниже.\n"
        "3️⃣ Бот сам проверит, что ваш ТГК совпадает со ссылкой, и засчитает привязку.\n\n"
        "<i>Это подтвердит, что ТГК принадлежит вам.</i>",
        reply_markup=kb
    )
@router.callback_query(F.data == "verify_bound")
async def verify_bound(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user = callback.from_user

    async def _resolve_chat(key):
        """Возвращает чат, если бот в нём состоит, иначе None."""
        try:
            return await bot.get_chat(key)
        except Exception:
            return None

    tgk_link_raw = (data.get('tgk_link', '') or '').strip()
    target_username = tgk_username_from_link(tgk_link_raw)

    # Чат, в который бота добавили (из сохранённой привязки)
    bound_chat = None
    binding = await db.get_user_tgk_binding(user.id)
    if binding and binding.get('chat_id'):
        bound_chat = await _resolve_chat(binding['chat_id'])
    binding_username = (binding or {}).get('username', '') or ''
    bound_username = ''
    if bound_chat:
        bound_username = (bound_chat.username or '').lstrip('@').lower()
    if not bound_username:
        bound_username = binding_username.lstrip('@').lower()

    # Чат с ссылки, который указал пользователь
    link_chat = await _resolve_chat("@" + target_username) if target_username else None
    link_username = (link_chat.username or '').lstrip('@').lower() if link_chat else ''

    valid_types = (ChatType.CHANNEL, ChatType.GROUP, ChatType.SUPERGROUP)

    # Сверяем ссылку и тот ТГК, в который добавлен бот; если всё сходится — привязка верна
    matched = False
    use_chat = None
    if link_chat is not None and link_chat.type in valid_types:
        # Бот реально находится в ТГК, указанном в ссылке
        matched = True
        use_chat = link_chat
        if bound_username and link_username and bound_username != link_username:
            matched = False
    elif bound_chat is not None and bound_chat.type in valid_types:
        # Ссылки нет/не резолвится, но бот добавлен в другой ТГК
        matched = True
        use_chat = bound_chat

    if not matched:
        await callback.answer("Сначала добавьте бота в ТГК!", show_alert=True)
        await callback.message.edit_text(
            "🔗 <b>ТГК не подтверждён</b>\n"
            f"{'━' * 28}\n\n"
            "Бот не обнаружил себя в ТГК по вашей ссылке.\n\n"
            "1️⃣ Добавьте этого бота в свой ТГК как администратора.\n"
            "2️⃣ Убедитесь, что ссылка в анкете и ТГК — один и тот же.\n"
            "3️⃣ Затем нажмите кнопку ещё раз."
        )
        return

    # Засчитываем привязку автоматически
    await db.add_tgk_binding(
        user.id,
        use_chat.id,
        use_chat.title or target_username or '',
        use_chat.username or target_username or ''
    )

    await state.clear()

    req_id = await db.create_checker_request(
        user_id=user.id,
        tag=data.get('tag', ''),
        tgk_name=data.get('tgk_name', ''),
        tgk_link=data.get('tgk_link', ''),
    )
    await db.add_log(user.id, "Подал заявку на верификацию", f"#{req_id}")

    await callback.message.edit_text(
        "✅ <b>Заявка на верификацию отправлена!</b>\n"
        f"{'━' * 28}\n\n"
        f"📌 Номер: <b>#{req_id}</b>\n\n"
        "⏳ Ожидайте решения администратора."
    )

    db_user = await db.get_user(user.id)
    join_date = (db_user.get('join_date') or '—') if db_user else '—'

    review = (
        f"🔍 <b>Новая заявка на верификацию #{req_id}</b>\n"
        f"{'━' * 28}\n\n"
        f"👤 <b>ПЗ:</b>\n"
        f"   🆔 ID: <code>{user.id}</code>\n"
        f"   👤 {user.first_name or '—'} {user.last_name or ''}\n"
        f"   📛 @{user.username or 'нет'}\n"
        f"   📅 Регистрация: {join_date}\n\n"
        f"🏷 <b>Тег:</b> {data.get('tag', '—')}\n"
        f"📡 <b>ТГК проверок:</b> {data.get('tgk_name', '—')}\n"
        f"🔗 <b>Ссылка ТГК:</b> {data.get('tgk_link', '—')}\n\n"
        f"⏳ <b>Статус:</b> Ожидает рассмотрения"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Принять", callback_data=f"checker_accept_{req_id}"),
        InlineKeyboardButton(text="❌ Отказать", callback_data=f"checker_deny_{req_id}"),
    ]])

    super_chat_id = await db.get_super_chat_id()
    try:
        if super_chat_id != 0:
            ft = await bot.create_forum_topic(chat_id=super_chat_id, name=f"Верификация #{req_id}")
            tid = ft.message_thread_id
            await db.create_topic_link(tid, user.id, "verification")
            await bot.send_message(chat_id=super_chat_id, message_thread_id=tid, text=review, reply_markup=kb)
        else:
            await bot.send_message(chat_id=ADMIN_ID, text=review, reply_markup=kb)
    except Exception as e:
        await bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ Ошибка: <code>{e}</code>\n\n{review}", reply_markup=kb)
    await callback.answer("✅ Отправлено!")


@router.callback_query(F.data.startswith("checker_accept_"))
async def checker_accept(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Только админ", show_alert=True)
        return
    req_id = int(callback.data.replace("checker_accept_", ""))
    req = await db.get_checker_request_by_id(req_id)
    if not req or req['status'] != 'pending':
        await callback.answer("Обработана", show_alert=True)
        return
    await db.update_checker_request_status(req_id, "approved")
    await db.set_user_verified(req['user_id'], True)
    await db.add_log(ADMIN_ID, "Верифицировал проверяющего", f"#{req_id}")
    try:
        await callback.message.edit_text(callback.message.html_text + "\n\n✅ <b>Принят</b>", reply_markup=None)
    except Exception:
        pass
    try:
        await bot.send_message(
            chat_id=req['user_id'],
            text="✅ <b>Вы верифицированы!</b>\n\nТеперь в вашем профиле появилась кнопка «Выложить проверку»."
        )
    except Exception:
        pass
    await callback.answer("Принят")


@router.callback_query(F.data.startswith("checker_deny_"))
async def checker_deny(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Только админ", show_alert=True)
        return
    req_id = int(callback.data.replace("checker_deny_", ""))
    req = await db.get_checker_request_by_id(req_id)
    if not req or req['status'] != 'pending':
        await callback.answer("Обработана", show_alert=True)
        return
    await db.update_checker_request_status(req_id, "denied")
    await db.add_log(ADMIN_ID, "Отклонил верификацию", f"#{req_id}")
    try:
        await callback.message.edit_text(callback.message.html_text + "\n\n❌ <b>Отклонён</b>", reply_markup=None)
    except Exception:
        pass
    try:
        await bot.send_message(
            chat_id=req['user_id'],
            text="❌ <b>К сожалению, вам отказано в верификации.</b>\n\nМожете попробовать подать заявку позже."
        )
    except Exception:
        pass
    await callback.answer("Отклонён")


# ==================== УПРАВЛЕНИЕ ТГК (сменить / добавить) ====================

def _profile_refresh_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Обновить профиль", callback_data="profile_refresh")]
    ])


@router.callback_query(F.data == "profile_refresh")
async def profile_refresh(callback: CallbackQuery, state: FSMContext):
    from handlers.user import send_profile
    await state.clear()
    user = await db.get_user(callback.from_user.id)
    try:
        if user:
            await send_profile(callback.message, user, edit=True)
        else:
            await callback.answer()
    except Exception:
        await callback.answer()
    await callback.answer()


@router.callback_query(F.data == "profile_change_tgk")
async def profile_change_tgk(callback: CallbackQuery, state: FSMContext):
    user = await db.get_user(callback.from_user.id)
    if not (user and user.get('is_verified')):
        await callback.answer("Вы не верифицированы", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Далее", callback_data="profile_change_tgk_confirm")],
        [InlineKeyboardButton(text="↩ Отмена", callback_data="profile_change_tgk_cancel")],
    ])
    await callback.message.edit_text(
        "🔁 <b>Смена ТГК</b>\n"
        f"{'━' * 28}\n\n"
        "Это действие <b>снимет верификацию</b> и <b>отвяжет бота</b> от текущего ТГК.\n\n"
        "После этого нужно будет заново привязать бота к новому ТГК и пройти верификацию.\n\n"
        "Продолжить?",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data == "profile_change_tgk_cancel")
async def profile_change_tgk_cancel(callback: CallbackQuery, state: FSMContext):
    from handlers.user import send_profile
    await state.clear()
    user = await db.get_user(callback.from_user.id)
    if user:
        await send_profile(callback.message, user, edit=True)
    await callback.answer()


@router.callback_query(F.data == "profile_change_tgk_confirm")
async def profile_change_tgk_confirm(callback: CallbackQuery, state: FSMContext):
    from handlers.user import send_profile
    user = await db.get_user(callback.from_user.id)
    if not (user and user.get('is_verified')):
        await callback.answer("Вы не верифицированы", show_alert=True)
        return
    await state.clear()
    await db.unverify_user(callback.from_user.id)
    await db.add_log(callback.from_user.id, "Сменил ТГК — снята верификация")
    try:
        await callback.message.edit_text(
            "❌ <b>Верификация снята</b>\n"
            f"{'━' * 28}\n\n"
            "Бот отвязан от старого ТГК.\n\n"
            "Чтобы привязать новый ТГК:\n"
            "1️⃣ Добавьте этого бота в <b>новый ТГК</b> как администратора;\n"
            "2️⃣ Дождитесь сообщения «ТГК привязан»;\n"
            "3️⃣ Пройдите верификацию заново из профиля.",
            reply_markup=_profile_refresh_kb()
        )
    except Exception:
        pass
    user2 = await db.get_user(callback.from_user.id)
    if user2:
        try:
            await send_profile(callback.message, user2, edit=False)
        except Exception:
            pass
    await callback.answer("Верификация снята")


@router.callback_query(F.data == "profile_add_tgk")
async def profile_add_tgk(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not (user and user.get('is_verified')):
        await callback.answer("Вы не верифицированы", show_alert=True)
        return
    bindings = await db.get_all_user_tgk_bindings(callback.from_user.id)
    count = len(bindings)
    await callback.message.edit_text(
        "➕ <b>Добавить ТГК</b>\n"
        f"{'━' * 28}\n\n"
        f"Сейчас привязано ТГК: <b>{count or 0}</b>\n\n"
        "Чтобы добавить ещё один ТГК:\n"
        "1️⃣ Добавьте этого бота в <b>новый ТГК</b> как администратора;\n"
        "2️⃣ Дождитесь сообщения «ТГК привязан»;\n"
        "3️⃣ Новый ТГК появится в профиле и в списке при выкладывании проверки.",
        reply_markup=_profile_refresh_kb()
    )
    await callback.answer()


# ==================== ВЫЛОЖИТЬ ПРОВЕРКУ ====================

# Этапы заполнения карточки проверки (показываются пользователю в начале)
POST_STEPS = [
    ("🖼", "Фото"),
    ("📝", "Описание"),
    ("⭐", "Оценка"),
    ("🤖", "Ссылка на бота"),
    ("📢", "ТГК (по желанию)"),
]


def post_check_kb(cnt: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Готово ({cnt})", callback_data="post_details_done")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="tops_cancel")],
    ])


def _gather_tgk_candidates(verified_tgk, bindings) -> list[dict]:
    """Собирает ТГК, которые можно указать как проверяющего: верифицированный профиль
    + все привязанные (бот добавлен в каналы), с дедупликацией."""
    cands = []
    seen = set()

    if verified_tgk and (verified_tgk.get('tgk_link') or '').strip():
        link = verified_tgk['tgk_link'].strip()
        key = tgk_username_from_link(link).lower()
        if key:
            seen.add(key)
        cands.append({
            "link": link,
            "title": (verified_tgk.get('tgk_name') or '').strip() or tgk_username_from_link(link),
            "verified": True,
        })

    for b in bindings or []:
        uname = (b.get('username') or '').strip().lstrip('@')
        title = (b.get('chat_title') or '').strip() or uname or '—'
        key = (uname or title).lower()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        link = f"https://t.me/{uname}" if uname else ''
        cands.append({"link": link or title, "title": title, "verified": False})

    return cands


async def show_post_intro(message_or_cb, state: FSMContext, category: str,
                          tgk_link: str, tgk_title: str):
    """Показывает стартовое сообщение с этапами заполнения проверки."""
    await state.set_state(PostCheckState.waiting_photos)
    await state.update_data(
        category=category,
        photos=[],
        tgk_link=tgk_link or '',
        tgk_title=tgk_title or '',
        tgk_from_profile=bool(tgk_link),
    )
    steps_text = "\n".join(f"   {e} <b>{t}</b>" for e, t in POST_STEPS)
    sec_title = "Проверки check-up 🔍" if category == "checkup" else "Другие ТГК 🏆"
    intro = (
        f"📦 <b>Добавление проверки</b>\n"
        f"{'━' * 28}\n\n"
        f"Секция: <b>{sec_title}</b>\n\n"
        f"<b>Этапы заполнения:</b>\n"
        f"{steps_text}\n\n"
        f"Нажмите <b>«Далее»</b>, чтобы начать, или <b>«Отменить»</b>."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Далее", callback_data="post_step_start")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="tops_cancel")],
    ])
    tgt = getattr(message_or_cb, 'message', None) or message_or_cb
    await tgt.answer(intro, reply_markup=kb)


async def start_post_check(message_or_cb, state: FSMContext, category: str):
    user_id = getattr(getattr(message_or_cb, 'from_user', None), 'id', None)
    user = await db.get_user(user_id) if user_id else None
    is_checkup_mod = bool(user and user.get('checkup_mod'))
    is_admin = user_id == ADMIN_ID

    bindings = await db.get_all_user_tgk_bindings(user_id) if user_id else []
    verified_tgk = await db.get_user_tgk_check(user_id) if user_id else None
    cands = _gather_tgk_candidates(verified_tgk, bindings)

    # Нечего указать как проверяющего — просим привязать ТГК (кроме модератора/админа).
    if not cands and not is_checkup_mod and not is_admin:
        notice = (
            "🔗 <b>Сначала привяжите ТГК!</b>\n"
            f"{'━' * 28}\n\n"
            "Чтобы выкладывать проверки, сначала <b>добавьте этого бота в свой ТГК</b> как администратора.\n\n"
            "Как только увидите сообщение о привязке — попробуйте ещё раз."
        )
        if hasattr(message_or_cb, 'message') and message_or_cb.message:
            await message_or_cb.message.answer(notice)
            await message_or_cb.answer()
        else:
            await message_or_cb.answer(notice)
        return

    if len(cands) > 1:
        # Несколько ТГК — спрашиваем, какой указать как проверяющего.
        await state.set_state(PostCheckState.waiting_tgk_choice)
        await state.update_data(category=category, photos=[], _tgk_candidates=cands)
        lines = "\n".join(
            f"   {i + 1}. {html.escape(str(c['title']))}{' 🔒' if c['verified'] else ''}"
            for i, c in enumerate(cands)
        )
        rows = [
            [InlineKeyboardButton(
                text=f"{'🔒 ' if c['verified'] else ''}{str(c['title'])[:40]}",
                callback_data=f"post_tgk_choose_{i}"
            )]
            for i, c in enumerate(cands)
        ]
        rows.append([InlineKeyboardButton(text="❌ Отменить", callback_data="tops_cancel")])
        tgt = getattr(message_or_cb, 'message', None) or message_or_cb
        await tgt.answer(
            "📢 <b>Какой ТГК указать как проверяющего?</b>\n\n" + lines,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
        return

    cand = cands[0] if cands else None
    await show_post_intro(
        message_or_cb, state, category,
        cand['link'] if cand else '',
        cand['title'] if cand else '',
    )


@router.callback_query(F.data.startswith("post_tgk_choose_"), PostCheckState.waiting_tgk_choice)
async def post_tgk_choose(callback: CallbackQuery, state: FSMContext):
    try:
        idx = int(callback.data.replace("post_tgk_choose_", ""))
    except ValueError:
        await callback.answer()
        return
    data = await state.get_data()
    cands = data.get('_tgk_candidates') or []
    if idx < 0 or idx >= len(cands):
        await callback.answer("Нет такого ТГК", show_alert=True)
        return
    cand = cands[idx]
    await show_post_intro(
        callback, state, data.get('category', 'other'),
        cand.get('link', ''),
        cand.get('title', ''),
    )
    await callback.answer()


@router.callback_query(F.data == "post_step_start", PostCheckState.waiting_photos)
async def post_step_start(callback: CallbackQuery, state: FSMContext):
    """Кнопка «Далее» — начинаем заполнение с этапа «Фото»."""
    form_text = (
        "🖼 <b>Этап 1 из 5 — Фото</b>\n"
        f"{'━' * 28}\n\n"
        "Отправьте <b>фото проверок</b> (можно сразу несколько).\n"
        "Когда закончите — нажмите кнопку «Готово»."
    )
    await callback.message.edit_text(form_text, reply_markup=post_check_kb(0))
    await callback.answer()


@router.callback_query(F.data == "profile_post_check")
async def profile_post_check(callback: CallbackQuery, state: FSMContext):
    await start_post_check(callback, state, "other")
    await callback.answer()


@router.callback_query(F.data == "profile_post_checkup")
async def profile_post_checkup(callback: CallbackQuery, state: FSMContext):
    await start_post_check(callback, state, "checkup")
    await callback.answer()


@router.message(PostCheckState.waiting_photos, F.chat.type == ChatType.PRIVATE)
async def post_collect_photo(message: Message, state: FSMContext):
    if message.photo:
        data = await state.get_data()
        photos = list(data.get('photos') or [])
        photos.append(message.photo[-1].file_id)
        await state.update_data(photos=photos)
        await message.answer(f"📸 Принято! Фото: {len(photos)}. Отправьте ещё или нажмите «Готово».")


@router.callback_query(F.data == "post_details_done", PostCheckState.waiting_photos)
async def post_photos_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    photos = list(data.get('photos') or [])
    if not photos:
        await callback.answer("Сначала отправьте хотя бы одно фото!", show_alert=True)
        return
    await state.set_state(PostCheckState.waiting_description)
    await callback.message.edit_text(
        f"✅ Фото получено: {len(photos)}\n\n"
        "<b>Следующий шаг</b> — отправьте <b>сообщение с описанием</b>:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@router.message(PostCheckState.waiting_description, F.chat.type == ChatType.PRIVATE)
async def post_description(message: Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
        return
    await state.update_data(description=message.text.strip())
    await state.set_state(PostCheckState.waiting_rating)
    await message.answer(
        "<b>Следующий шаг</b> — укажите <b>оценку бота</b>, например <b>10/100</b>:",
        reply_markup=cancel_kb()
    )


@router.message(PostCheckState.waiting_rating, F.chat.type == ChatType.PRIVATE)
async def post_rating(message: Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
        return
    await state.update_data(rating=message.text.strip())
    await state.set_state(PostCheckState.waiting_bot_link)
    await message.answer(
        "<b>Следующий шаг</b> — отправьте <b>ссылку на бота</b> (например @botproverka):",
        reply_markup=cancel_kb()
    )
def _passed_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data="post_passed_yes"),
         InlineKeyboardButton(text="❌ Нет", callback_data="post_passed_no")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="tops_cancel")],
    ])


async def ask_passed(state: FSMContext, msg) -> None:
    """Предпоследний вопрос: прошёл ли бот проверку (Да/Нет)."""
    await state.set_state(PostCheckState.waiting_passed)
    await msg.answer(
        "✅ <b>Предпоследний шаг</b> — бот <b>прошёл проверку</b>?",
        reply_markup=_passed_kb()
    )


@router.message(PostCheckState.waiting_bot_link, F.chat.type == ChatType.PRIVATE)
async def post_bot_link(message: Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
        return
    bot_link_raw = message.text.strip()
    bot_username = bot_link_raw.lstrip('@').split('/')[-1]
    await state.update_data(bot_username=bot_username, bot_link=bot_link_raw)
    data = await state.get_data()
    if data.get('tgk_link'):
        # ТГК уже подставлен из верифицированного профиля — пропускаем ручной ввод.
        await ask_passed(state, message)
        return
    await state.set_state(PostCheckState.waiting_tgk_link)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏩ Пропустить", callback_data="post_tgk_skip")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="tops_cancel")],
    ])
    await message.answer(
        "<b>Следующий шаг</b> — отправьте <b>ссылку на ваш ТГК</b> (необязательно):",
        reply_markup=kb
    )


@router.message(PostCheckState.waiting_tgk_link, F.chat.type == ChatType.PRIVATE)
async def post_tgk_link(message: Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
        return
    await state.update_data(tgk_link=message.text.strip())
    await ask_passed(state, message)


@router.callback_query(F.data == "post_tgk_skip", PostCheckState.waiting_tgk_link)
async def post_tgk_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(tgk_link="")
    await ask_passed(state, callback.message)
    await callback.answer()


@router.callback_query(F.data == "post_passed_yes", PostCheckState.waiting_passed)
async def post_passed_yes(callback: CallbackQuery, state: FSMContext):
    await state.update_data(passed=1)
    await show_post_confirm(callback.message, state, edit=True)
    await callback.answer()


@router.callback_query(F.data == "post_passed_no", PostCheckState.waiting_passed)
async def post_passed_no(callback: CallbackQuery, state: FSMContext):
    await state.update_data(passed=0)
    await show_post_confirm(callback.message, state, edit=True)
    await callback.answer()


async def show_post_confirm(message: Message, state: FSMContext, edit: bool):
    data = await state.get_data()
    photos = list(data.get('photos') or [])
    bot = f"@{data.get('bot_username', '—')}"
    tgk = data.get('tgk_link') or ''
    checker = f"@{tgk_username_from_link(tgk)}" if tgk else '—'
    passed = data.get('passed')
    pass_line = '✅ Да' if passed in (1, '1', True) else ('❌ Нет' if passed is not None else '—')
    text = (
        "📋 <b>Проверьте данные</b>\n"
        f"{'━' * 28}\n\n"
        f"🌐 Проверяющие: {checker}\n"
        f"🤖 Бот на проверке: {bot}\n"
        f"📝 Описание: {data.get('description', '—')}\n"
        f"⭐ Оценка: {data.get('rating', '—')}\n"
        f"🔗 Ссылка бота: {data.get('bot_link', '—')}\n"
        f"📢 ТГК: {tgk or '—'}\n"
        f"✅ Бот прошёл проверку: {pass_line}\n"
        f"🖼 Фото: {len(photos)}\n\n"
        f"Всё верно?"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить проверку", callback_data="post_confirm")],
        [InlineKeyboardButton(text="📝 Заполнить заново", callback_data="post_restart")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="tops_cancel")],
    ])
    await state.set_state(PostCheckState.confirm)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "post_restart")
async def post_restart(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    await start_post_check(callback, state, data.get('category', 'other'))
    await callback.answer()


@router.callback_query(F.data == "post_confirm")
async def post_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    category = data.get('category', 'other')
    user = await db.get_user(callback.from_user.id)
    if category == "checkup":
        if callback.from_user.id != ADMIN_ID and not (user and user.get('checkup_mod')):
            await callback.answer("⛔ Нет доступа", show_alert=True)
            return
    elif category == "other":
        if callback.from_user.id != ADMIN_ID and not (user and user.get('is_verified')):
            await callback.answer("⛔ Только для верифицированных", show_alert=True)
            return

    await db.create_check(
        bot_username=data.get('bot_username', ''),
        bot_link=data.get('bot_link', ''),
        tgk_link=data.get('tgk_link', ''),
        tgk_title=data.get('tgk_title', ''),
        rating=data.get('rating', ''),
        description=data.get('description', ''),
        photos=json.dumps(data.get('photos') or []),
        category=category,
        added_by=callback.from_user.id,
        passed=1 if data.get('passed') in (1, '1', True) else 0,
    )
    await state.clear()
    await callback.message.edit_text(
        "✅ <b>Спасибо за отправленную проверку!</b>\n\nОна уже появилась в топе «Другие ТГК» 🏆"
        if category == "other"
        else "✅ <b>Спасибо за отправленную проверку!</b>\n\nОна уже появилась в топе «Проверки check-up» 🔍"
    )
    await callback.answer("Отправлено!")
# ==================== АНКЕТА НА МОДЕРАТОРА ====================

ANKETA_QUESTIONS = [
    "1️⃣ Ваш <b>возраст</b>?",
    "2️⃣ Сколько времени вы готовы <b>уделять проекту</b>?",
    "3️⃣ Есть ли у вас <b>опыт в проверках</b>?",
    "4️⃣ Ваш <b>часовой пояс</b>?",
    "5️⃣ <b>Отдаёте душу</b>?)",
    "6️⃣ Легко ли вас <b>разозлить</b>?",
    "7️⃣ Ваша <b>реакция</b>, если админы начнут неадекватно себя вести или оскорблять вас?",
]


@router.callback_query(F.data == "profile_anketa")
async def profile_anketa(callback: CallbackQuery, state: FSMContext):
    user = await db.get_user(callback.from_user.id)
    if user and user.get('checkup_mod'):
        await callback.answer("Вы уже модератор check-up", show_alert=True)
        return
    await state.set_state(AnketaState.answering)
    await state.update_data(step=0, answers=[])
    await callback.message.edit_text(ANKETA_QUESTIONS[0], reply_markup=cancel_kb())
    await callback.answer()


@router.message(AnketaState.answering, F.chat.type == ChatType.PRIVATE)
async def anketa_answer(message: Message, state: FSMContext, bot: Bot):
    if not message.text or message.text.startswith("/"):
        return
    data = await state.get_data()
    step = data.get('step', 0)
    answers = list(data.get('answers') or [])
    answers.append(message.text.strip())
    step += 1

    if step < len(ANKETA_QUESTIONS):
        await state.update_data(step=step, answers=answers)
        await message.answer(ANKETA_QUESTIONS[step])
        return

    # Все ответы собраны
    await state.clear()
    await message.answer(
        "8) Вы <b>милашка</b>, ждём вашу анкету 💌\n\n"
        "<i>Отправляем анкету администратору...</i>"
    )
    await submit_anketa(message, bot, answers)


async def submit_anketa(message: Message, bot: Bot, answers: list):
    user_msg = message.from_user
    db_user = await db.get_user(user_msg.id)
    join_date = (db_user.get('join_date') or '—') if db_user else '—'
    warnings = (db_user.get('warnings') or 0) if db_user else 0

    async with aiosqlite.connect(db.DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM topics WHERE user_id=? AND topic_type='ticket'",
            (user_msg.id,)
        )
        tickets = (await cursor.fetchone())[0]

    header = (
        f"📝 <b>Анкета на модератора</b>\n"
        f"{'━' * 28}\n\n"
        f"👤 <b>ПЗ:</b>\n"
        f"   🆔 ID: <code>{user_msg.id}</code>\n"
        f"   👤 {user_msg.first_name or '—'} {user_msg.last_name or ''}\n"
        f"   📛 @{user_msg.username or 'нет'}\n"
        f"   📅 Регистрация в боте: {join_date}\n"
        f"   ⚠️ Жалоб: {warnings}\n"
        f"   🎫 Тикетов: {tickets}\n\n"
    )
    body = ""
    for i, a in enumerate(answers, start=1):
        body += f"<b>{i})</b> {a}\n"

    full = header + body
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Принять", callback_data=f"ank_accept_{user_msg.id}"),
        InlineKeyboardButton(text="❌ Отказать", callback_data=f"ank_deny_{user_msg.id}"),
    ]])

    super_chat_id = await db.get_super_chat_id()
    try:
        if super_chat_id != 0:
            ft = await bot.create_forum_topic(chat_id=super_chat_id, name=f"Анкета — {user_msg.first_name or user_msg.id}")
            tid = ft.message_thread_id
            await db.create_topic_link(tid, user_msg.id, "anketa")
            await bot.send_message(chat_id=super_chat_id, message_thread_id=tid, text=full, reply_markup=kb)
        else:
            await bot.send_message(chat_id=ADMIN_ID, text=full, reply_markup=kb)
    except Exception as e:
        await bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ Ошибка: <code>{e}</code>\n\n{full}", reply_markup=kb)


@router.callback_query(F.data.startswith("ank_accept_"))
async def anketa_accept(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Только админ", show_alert=True)
        return
    user_id = int(callback.data.replace("ank_accept_", ""))
    await db.set_checkup_mod(user_id, True)
    await db.add_log(ADMIN_ID, "Назначил модератора check-up (анкета)", f"ID: {user_id}")
    try:
        await callback.message.edit_text(callback.message.html_text + "\n\n✅ <b>Принят</b>", reply_markup=None)
    except Exception:
        pass
    try:
        profile_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Добавить проверку", callback_data="profile_post_checkup")]
        ])
        await bot.send_message(
            chat_id=user_id,
            text=(
                "🛡 <b>Вы — модератор check-up!</b>\n"
                f"{'━' * 28}\n\n"
                "Поздравляем! Ваша анкета принята.\n"
                "Теперь вы можете добавлять проверки check-up из своего профиля."
            ),
            reply_markup=profile_kb
        )
    except Exception:
        pass
    await callback.answer("Принят")


@router.callback_query(F.data.startswith("ank_deny_"))
async def anketa_deny(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Только админ", show_alert=True)
        return
    user_id = int(callback.data.replace("ank_deny_", ""))
    try:
        await callback.message.edit_text(callback.message.html_text + "\n\n❌ <b>Отказано</b>", reply_markup=None)
    except Exception:
        pass
    try:
        await bot.send_message(
            chat_id=user_id,
            text="❌ <b>К сожалению, вам отказано.</b>\n\nВы можете попробовать подать анкету ещё раз или позже."
        )
    except Exception:
        pass
    await callback.answer("Отказано")


# ==================== СНЯТИЕ ПОЛНОМОЧИЙ МОДЕРАТОРА ====================

@router.callback_query(F.data == "profile_unmod")
async def profile_unmod(callback: CallbackQuery):
    """Кнопка «Снять полномочия» — запрос подтверждения."""
    user = await db.get_user(callback.from_user.id)
    if not (user and user.get('checkup_mod')):
        await callback.answer("Вы не являетесь модератором check-up", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="profile_unmod_confirm")],
        [InlineKeyboardButton(text="↩ Отмена", callback_data="profile_unmod_cancel")],
    ])
    await callback.message.edit_text(
        "🛡️ <b>Снятие полномочий модератора</b>\n"
        f"{'━' * 28}\n\n"
        "Это действие <b>снимет с вас статус модератора</b> check-up "
        "и <b>уберёт возможность публиковать проверки</b>.\n\n"
        "Вы уверены?",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data == "profile_unmod_cancel")
async def profile_unmod_cancel(callback: CallbackQuery):
    """Кнопка «Отмена» — возвращаемся к профилю."""
    from handlers.user import send_profile
    user = await db.get_user(callback.from_user.id)
    if user:
        await send_profile(callback.message, user, edit=True)
    await callback.answer()


@router.callback_query(F.data == "profile_unmod_confirm")
async def profile_unmod_confirm(callback: CallbackQuery, bot: Bot):
    """Кнопка «Подтвердить» — снимаем полномочия модератора."""
    user = await db.get_user(callback.from_user.id)
    if not (user and user.get('checkup_mod')):
        await callback.answer("Вы не являетесь модератором check-up", show_alert=True)
        return
    await db.set_checkup_mod(callback.from_user.id, False)
    await db.add_log(callback.from_user.id, "Снял с себя полномочия модератора check-up")
    try:
        await callback.message.edit_text(
            "✅ <b>Полномочия сняты</b>\n\n"
            "Вы больше не можете публиковать проверки в топе «Проверки check-up»."
        )
    except Exception:
        pass
    try:
        await bot.send_message(
            chat_id=callback.from_user.id,
            text="ℹ️ Если захотите снова стать модератором — подайте анкету через свой профиль."
        )
    except Exception:
        pass
    await callback.answer("Полномочия сняты")