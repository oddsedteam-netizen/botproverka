import aiosqlite
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "bot.db")


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                last_name TEXT DEFAULT '',
                join_date TEXT DEFAULT '',
                last_active TEXT DEFAULT '',
                messages_count INTEGER DEFAULT 0,
                tickets_created INTEGER DEFAULT 0,
                tickets_resolved INTEGER DEFAULT 0,
                warnings INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                ban_reason TEXT DEFAULT '',
                role TEXT DEFAULT 'user',
                notes TEXT DEFAULT '',
                linked_bot TEXT DEFAULT '',
                is_verified INTEGER DEFAULT 0,
                checkup_mod INTEGER DEFAULT 0
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                subject TEXT DEFAULT '',
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'open',
                priority TEXT DEFAULT 'normal',
                category TEXT DEFAULT 'other',
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT '',
                closed_at TEXT DEFAULT '',
                assigned_to TEXT DEFAULT '',
                response TEXT DEFAULT '',
                rating INTEGER DEFAULT 0
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS action_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT DEFAULT '',
                details TEXT DEFAULT '',
                timestamp TEXT DEFAULT ''
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS verification_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                bot_username TEXT DEFAULT '',
                reason TEXT DEFAULT '',
                preferred_admin TEXT DEFAULT '',
                topic TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT '',
                reviewed_at TEXT DEFAULT '',
                reviewer_comment TEXT DEFAULT '',
                topic_id INTEGER DEFAULT 0
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS topics (
                topic_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                topic_type TEXT NOT NULL,
                status TEXT DEFAULT 'open',
                created_at TEXT DEFAULT '',
                closed_at TEXT DEFAULT ''
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            )
        """)

        # Таблица проверок (топы)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS checks (
                check_id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_username TEXT DEFAULT '',
                bot_link TEXT DEFAULT '',
                tgk_link TEXT DEFAULT '',
                rating TEXT DEFAULT '',
                description TEXT DEFAULT '',
                photos TEXT DEFAULT '[]',
                category TEXT DEFAULT 'other',
                tgk_title TEXT DEFAULT '',
                passed INTEGER DEFAULT 0,
                added_by INTEGER DEFAULT 0,
                created_at TEXT DEFAULT ''
            )
        """)

        # Таблица заявок на верификацию (проверяющие)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS checker_requests (
                req_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                tag TEXT DEFAULT '',
                tgk_name TEXT DEFAULT '',
                tgk_link TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT ''
            )
        """)

        # Таблица привязок ТГК (бот добавлен в чат пользователем)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tgk_bindings (
                binding_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER DEFAULT 0,
                chat_title TEXT DEFAULT '',
                username TEXT DEFAULT '',
                bound_at TEXT DEFAULT ''
            )
        """)

        # Проверки: внутренний ID начинается со 100
        cur = await conn.execute("SELECT COALESCE(MAX(check_id),0) FROM checks")
        max_check = (await cur.fetchone())[0]
        if max_check < 100:
            await conn.execute("DELETE FROM sqlite_sequence WHERE name='checks'")
            await conn.execute("INSERT INTO sqlite_sequence(name,seq) VALUES('checks',?)", (99,))
        await conn.commit()

    # Миграция — добавляем колонку linked_bot если нет
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in await cursor.fetchall()]
        if 'linked_bot' not in columns:
            await conn.execute("ALTER TABLE users ADD COLUMN linked_bot TEXT DEFAULT ''")
            await conn.commit()
        if 'is_verified' not in columns:
            await conn.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0")
            await conn.commit()
        if 'checkup_mod' not in columns:
            await conn.execute("ALTER TABLE users ADD COLUMN checkup_mod INTEGER DEFAULT 0")
            await conn.commit()

    # Миграция — добавляем колонку username в tgk_bindings если нет
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("PRAGMA table_info(tgk_bindings)")
        bind_columns = [row[1] for row in await cursor.fetchall()]
        if 'username' not in bind_columns:
            await conn.execute("ALTER TABLE tgk_bindings ADD COLUMN username TEXT DEFAULT ''")
            await conn.commit()

    # Миграция — добавляем колонку category в topics если нет
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("PRAGMA table_info(topics)")
        topic_columns = [row[1] for row in await cursor.fetchall()]
        if 'category' not in topic_columns:
            await conn.execute("ALTER TABLE topics ADD COLUMN category TEXT DEFAULT ''")
            await conn.commit()

    # Миграция — добавляем новые колонки в checks (tgk_title, passed) если нет
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("PRAGMA table_info(checks)")
        check_columns = [row[1] for row in await cursor.fetchall()]
        if 'tgk_title' not in check_columns:
            await conn.execute("ALTER TABLE checks ADD COLUMN tgk_title TEXT DEFAULT ''")
            await conn.commit()
        if 'passed' not in check_columns:
            await conn.execute("ALTER TABLE checks ADD COLUMN passed INTEGER DEFAULT 0")
            await conn.commit()


# ==================== ПОЛЬЗОВАТЕЛИ ====================

async def register_user(user_id: int, username: str, first_name: str, last_name: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as conn:
        existing = await conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        row = await existing.fetchone()
        if row is None:
            await conn.execute(
                "INSERT INTO users (user_id, username, first_name, last_name, join_date, last_active) VALUES (?,?,?,?,?,?)",
                (user_id, username or '', first_name or '', last_name or '', now, now)
            )
        else:
            await conn.execute(
                "UPDATE users SET username=?, first_name=?, last_name=?, last_active=? WHERE user_id=?",
                (username or '', first_name or '', last_name or '', now, user_id)
            )
        await conn.commit()


async def increment_messages(user_id: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET messages_count=messages_count+1, last_active=? WHERE user_id=?", (now, user_id))
        await conn.commit()


async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM users ORDER BY join_date DESC")
        return [dict(r) for r in await cursor.fetchall()]


async def search_user_by_id(user_id: int) -> dict | None:
    return await get_user(user_id)


async def set_linked_bot(user_id: int, bot_username: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET linked_bot=? WHERE user_id=?", (bot_username, user_id))
        await conn.commit()


async def get_linked_bot(user_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("SELECT linked_bot FROM users WHERE user_id=?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row and row[0] else ''


async def ban_user(user_id: int, reason: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET is_banned=1, ban_reason=? WHERE user_id=?", (reason, user_id))
        await conn.commit()


async def unban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET is_banned=0, ban_reason='' WHERE user_id=?", (user_id,))
        await conn.commit()


# ==================== СТАТИСТИКА ====================

async def get_total_users() -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        return (await (await conn.execute("SELECT COUNT(*) FROM users")).fetchone())[0]


async def get_active_users_today() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as conn:
        return (await (await conn.execute("SELECT COUNT(*) FROM users WHERE last_active LIKE ?", (f"{today}%",))).fetchone())[0]


async def get_new_users_today() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as conn:
        return (await (await conn.execute("SELECT COUNT(*) FROM users WHERE join_date LIKE ?", (f"{today}%",))).fetchone())[0]


async def get_banned_users() -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        return (await (await conn.execute("SELECT COUNT(*) FROM users WHERE is_banned=1")).fetchone())[0]


async def get_total_messages() -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        return (await (await conn.execute("SELECT COALESCE(SUM(messages_count),0) FROM users")).fetchone())[0]


async def get_users_with_warnings() -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        return (await (await conn.execute("SELECT COUNT(*) FROM users WHERE warnings>0")).fetchone())[0]


async def get_total_warnings() -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        return (await (await conn.execute("SELECT COALESCE(SUM(warnings),0) FROM users")).fetchone())[0]


async def get_tickets_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as conn:
        total = (await (await conn.execute("SELECT COUNT(*) FROM tickets")).fetchone())[0]
        open_t = (await (await conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'")).fetchone())[0]
        in_progress = (await (await conn.execute("SELECT COUNT(*) FROM tickets WHERE status='in_progress'")).fetchone())[0]
        resolved = (await (await conn.execute("SELECT COUNT(*) FROM tickets WHERE status='resolved'")).fetchone())[0]
        closed = (await (await conn.execute("SELECT COUNT(*) FROM tickets WHERE status='closed'")).fetchone())[0]
        rejected = (await (await conn.execute("SELECT COUNT(*) FROM tickets WHERE status='rejected'")).fetchone())[0]
        low = (await (await conn.execute("SELECT COUNT(*) FROM tickets WHERE priority='low'")).fetchone())[0]
        normal = (await (await conn.execute("SELECT COUNT(*) FROM tickets WHERE priority='normal'")).fetchone())[0]
        high = (await (await conn.execute("SELECT COUNT(*) FROM tickets WHERE priority='high'")).fetchone())[0]
        critical = (await (await conn.execute("SELECT COUNT(*) FROM tickets WHERE priority='critical'")).fetchone())[0]
        today = datetime.now().strftime("%Y-%m-%d")
        today_created = (await (await conn.execute("SELECT COUNT(*) FROM tickets WHERE created_at LIKE ?", (f"{today}%",))).fetchone())[0]
        today_closed = (await (await conn.execute("SELECT COUNT(*) FROM tickets WHERE closed_at LIKE ?", (f"{today}%",))).fetchone())[0]
        avg_rating = (await (await conn.execute("SELECT AVG(rating) FROM tickets WHERE rating>0")).fetchone())[0]
        return {
            "total": total, "open": open_t, "in_progress": in_progress,
            "resolved": resolved, "closed": closed, "rejected": rejected,
            "low": low, "normal": normal, "high": high, "critical": critical,
            "today_created": today_created, "today_closed": today_closed,
            "avg_rating": round(avg_rating, 1) if avg_rating else 0,
        }


async def get_verification_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as conn:
        total = (await (await conn.execute("SELECT COUNT(*) FROM verification_requests")).fetchone())[0]
        pending = (await (await conn.execute("SELECT COUNT(*) FROM verification_requests WHERE status='pending'")).fetchone())[0]
        approved = (await (await conn.execute("SELECT COUNT(*) FROM verification_requests WHERE status='approved'")).fetchone())[0]
        denied = (await (await conn.execute("SELECT COUNT(*) FROM verification_requests WHERE status='denied'")).fetchone())[0]
        return {"total": total, "pending": pending, "approved": approved, "denied": denied}


# ==================== ЗАЯВКИ ====================

async def create_verification_request(user_id, bot_username, reason, preferred_admin, topic, topic_id=0) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "INSERT INTO verification_requests (user_id,bot_username,reason,preferred_admin,topic,status,created_at,topic_id) VALUES (?,?,?,?,?,'pending',?,?)",
            (user_id, bot_username, reason, preferred_admin, topic, now, topic_id)
        )
        await conn.commit()
        return cursor.lastrowid


async def update_request_topic_id(request_id, topic_id):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE verification_requests SET topic_id=? WHERE request_id=?", (topic_id, request_id))
        await conn.commit()


async def update_request_status(request_id, status):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE verification_requests SET status=?, reviewed_at=? WHERE request_id=?", (status, now, request_id))
        await conn.commit()


async def get_request_by_id(request_id) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM verification_requests WHERE request_id=?", (request_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_pending_request_by_user(user_id) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM verification_requests WHERE user_id=? AND status='pending'", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_requests(status=None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if status:
            cursor = await conn.execute("SELECT * FROM verification_requests WHERE status=? ORDER BY created_at DESC", (status,))
        else:
            cursor = await conn.execute("SELECT * FROM verification_requests ORDER BY created_at DESC")
        return [dict(r) for r in await cursor.fetchall()]


# ==================== ТОПИКИ ====================

async def create_topic_link(topic_id, user_id, topic_type, category=""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("INSERT OR REPLACE INTO topics (topic_id,user_id,topic_type,status,created_at,category) VALUES (?,?,?,'open',?,?)",
                           (topic_id, user_id, topic_type, now, category))
        await conn.commit()


async def get_topic_info(topic_id) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM topics WHERE topic_id=?", (topic_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_user_open_topic(user_id, topic_type) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM topics WHERE user_id=? AND topic_type=? AND status='open'", (user_id, topic_type))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def close_topic(topic_id):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE topics SET status='closed', closed_at=? WHERE topic_id=?", (now, topic_id))
        await conn.commit()


async def get_all_topics(topic_type=None, status=None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        q = "SELECT * FROM topics WHERE 1=1"
        params = []
        if topic_type:
            q += " AND topic_type=?"
            params.append(topic_type)
        if status:
            q += " AND status=?"
            params.append(status)
        q += " ORDER BY created_at DESC"
        cursor = await conn.execute(q, params)
        return [dict(r) for r in await cursor.fetchall()]


# ==================== НАСТРОЙКИ ====================

async def set_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("INSERT INTO settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        await conn.commit()


async def get_setting(key, default="") -> str:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cursor.fetchone()
        return row[0] if row else default


async def get_super_chat_id() -> int:
    v = await get_setting("super_chat_id", "0")
    try:
        return int(v)
    except ValueError:
        return 0


async def set_super_chat_id(chat_id):
    await set_setting("super_chat_id", str(chat_id))


# ==================== ЛОГИ ====================

async def add_log(user_id, action, details=""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("INSERT INTO action_logs (user_id,action,details,timestamp) VALUES (?,?,?,?)", (user_id, action, details, now))
        await conn.commit()


async def get_logs_count() -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        return (await (await conn.execute("SELECT COUNT(*) FROM action_logs")).fetchone())[0]


async def get_recent_logs(limit=10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM action_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cursor.fetchall()]


async def get_top_users_by_messages(limit=5) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM users ORDER BY messages_count DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cursor.fetchall()]


async def get_top_users_by_tickets(limit=5) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM users ORDER BY tickets_created DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cursor.fetchall()]


async def get_users_by_role(role) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        return (await (await conn.execute("SELECT COUNT(*) FROM users WHERE role=?", (role,))).fetchone())[0]


async def get_user_stats(user_id) -> dict:
    """Подробная стата по юзеру для админки"""
    async with aiosqlite.connect(DB_PATH) as conn:
        reqs = (await (await conn.execute("SELECT COUNT(*) FROM verification_requests WHERE user_id=?", (user_id,))).fetchone())[0]
        ticks = (await (await conn.execute("SELECT COUNT(*) FROM topics WHERE user_id=? AND topic_type='ticket'", (user_id,))).fetchone())[0]
        contacts = (await (await conn.execute("SELECT COUNT(*) FROM topics WHERE user_id=? AND topic_type='contact'", (user_id,))).fetchone())[0]
        return {"requests": reqs, "tickets": ticks, "contacts": contacts}


# ==================== ВЕРИФИКАЦИЯ (ПРОВЕРЯЮЩИЕ) ====================

async def set_user_verified(user_id: int, val: bool):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET is_verified=? WHERE user_id=?", (1 if val else 0, user_id))
        await conn.commit()


async def set_checkup_mod(user_id: int, val: bool):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET checkup_mod=? WHERE user_id=?", (1 if val else 0, user_id))
        await conn.commit()


async def create_checker_request(user_id, tag, tgk_name, tgk_link) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "INSERT INTO checker_requests (user_id,tag,tgk_name,tgk_link,status,created_at) VALUES (?,?,?,?,'pending',?)",
            (user_id, tag, tgk_name, tgk_link, now)
        )
        await conn.commit()
        return cursor.lastrowid


async def get_pending_checker_request_by_user(user_id) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM checker_requests WHERE user_id=? AND status='pending'", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_checker_request_by_id(req_id) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM checker_requests WHERE req_id=?", (req_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_checker_request_status(req_id, status):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE checker_requests SET status=? WHERE req_id=?", (status, req_id))
        await conn.commit()


# ==================== ПРОВЕРКИ (ТОПЫ) ====================

async def create_check(bot_username, bot_link, tgk_link, tgk_title, rating, description, photos, category, added_by, passed=0) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "INSERT INTO checks (bot_username,bot_link,tgk_link,tgk_title,rating,description,photos,category,passed,added_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (bot_username, bot_link, tgk_link, tgk_title or '', rating, description, photos, category, 1 if passed else 0, added_by, now)
        )
        await conn.commit()
        return cursor.lastrowid


async def get_checks(category=None, limit=100) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        q = "SELECT * FROM checks WHERE 1=1"
        params = []
        if category:
            q += " AND category=?"
            params.append(category)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cursor = await conn.execute(q, params)
        return [dict(r) for r in await cursor.fetchall()]


async def get_bots_summary(category) -> list[dict]:
    """Список ботов в категории с количеством проверок, отсортированный по убыванию."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT bot_username, MAX(check_id) as last_check_id, COUNT(check_id) as cnt "
            "FROM checks WHERE category=? GROUP BY bot_username ORDER BY cnt DESC",
            (category,)
        )
        return [dict(r) for r in await cursor.fetchall()]


async def get_checks_by_bot(bot_username, category) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM checks WHERE bot_username=? AND category=? ORDER BY created_at ASC",
            (bot_username, category)
        )
        return [dict(r) for r in await cursor.fetchall()]


async def get_check_by_id(check_id) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM checks WHERE check_id=?", (check_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
async def delete_check_by_id(check_id) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("DELETE FROM checks WHERE check_id=?", (check_id,))
        await conn.commit()
        return cursor.rowcount > 0


async def get_user_tgk_check(user_id) -> dict | None:
    """Возвращает ТГК проверяющего, привязанный при верификации (approved)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT tgk_name, tgk_link FROM checker_requests "
            "WHERE user_id=? AND status='approved' ORDER BY req_id DESC LIMIT 1",
            (user_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_tgk_rating(limit: int = 30) -> list[dict]:
    """Рейтинг проверяющих ТГК по количеству проверок (топ до заданного лимита).

    Для каждого ТГК считает всего проверок и сколько из них бот прошёл (passed=1).
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT tgk_link, MAX(tgk_title) AS tgk_title, "
            "COUNT(*) AS total, "
            "COALESCE(SUM(CASE WHEN passed=1 THEN 1 ELSE 0 END), 0) AS passed "
            "FROM checks WHERE tgk_link <> '' "
            "GROUP BY tgk_link ORDER BY total DESC, tgk_link ASC LIMIT ?",
            (int(limit),)
        )
        return [dict(r) for r in await cursor.fetchall()]


async def get_checks_by_tgk_link(tgk_link: str, limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM checks WHERE tgk_link=? ORDER BY created_at DESC LIMIT ?",
            (tgk_link, int(limit))
        )
        return [dict(r) for r in await cursor.fetchall()]


# ==================== ПРИВЯЗКА ТГК (бот добавлен в чат) ====================

async def add_tgk_binding(user_id: int, chat_id: int, chat_title: str, chat_username: str = ''):
    """Добавляет/обновляет привязку ТГК для пользователя.

    Позволяет хранить несколько ТГК за одним пользователем. Если такой чат уже
    привязан — обновляет его, иначе вставляет новую запись (старые не удаляются).
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT binding_id FROM tgk_bindings WHERE user_id=? AND chat_id=?",
            (user_id, chat_id)
        )
        existing = await cursor.fetchone()
        if existing:
            await conn.execute(
                "UPDATE tgk_bindings SET chat_title=?, username=?, bound_at=? WHERE binding_id=?",
                (chat_title or '', chat_username or '', now, existing[0])
            )
        else:
            await conn.execute(
                "INSERT INTO tgk_bindings (user_id,chat_id,chat_title,username,bound_at) VALUES (?,?,?,?,?)",
                (user_id, chat_id, chat_title or '', chat_username or '', now)
            )
        await conn.commit()


async def get_all_user_tgk_bindings(user_id: int) -> list[dict]:
    """Все привязанные ТГК пользователя (бот добавлен в несколько каналов)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM tgk_bindings WHERE user_id=? ORDER BY bound_at DESC",
            (user_id,)
        )
        return [dict(r) for r in await cursor.fetchall()]


async def get_user_tgk_binding(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM tgk_bindings WHERE user_id=? ORDER BY binding_id DESC LIMIT 1", (user_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def remove_tgk_binding(user_id: int, chat_id: int | None = None):
    """Удаляет привязку ТГК. Если передан chat_id — только эту, иначе все для юзера."""
    async with aiosqlite.connect(DB_PATH) as conn:
        if chat_id is not None:
            await conn.execute(
                "DELETE FROM tgk_bindings WHERE user_id=? AND chat_id=?",
                (user_id, chat_id)
            )
        else:
            await conn.execute("DELETE FROM tgk_bindings WHERE user_id=?", (user_id,))
        await conn.commit()


async def unverify_user(user_id: int):
    """Полностью снимает верификацию: убирает флаг, отзывает утверждённую заявку
    и отвязывает бота от всех ТГК пользователя."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET is_verified=0 WHERE user_id=?", (user_id,))
        await conn.execute(
            "UPDATE checker_requests SET status='revoked' WHERE user_id=? AND status='approved'",
            (user_id,)
        )
        await conn.execute("DELETE FROM tgk_bindings WHERE user_id=?", (user_id,))
        await conn.commit()


# ==================== МОДЕРАТОРЫ CHECK-UP ====================

async def get_checkup_moderators() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM users WHERE checkup_mod=1 ORDER BY join_date DESC"
        )
        return [dict(r) for r in await cursor.fetchall()]


async def get_checks_by_moderator(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM checks WHERE added_by=? ORDER BY created_at DESC", (user_id,)
        )
        return [dict(r) for r in await cursor.fetchall()]


# ==================== ТИКЕТЫ ПОЛЬЗОВАТЕЛЯ ====================

async def get_user_tickets(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM topics WHERE user_id=? AND topic_type='ticket' ORDER BY created_at DESC",
            (user_id,)
        )
        return [dict(r) for r in await cursor.fetchall()]