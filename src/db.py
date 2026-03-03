from __future__ import annotations

import json
import logging
from pathlib import Path

import aiosqlite

from src.models import UserPreferences

logger = logging.getLogger(__name__)

_db_path: str = "job_bot.sqlite"


def set_db_path(path: str) -> None:
    """Override the default SQLite file path used for all database operations.

    Examples:
        >>> set_db_path("data/my_bot.sqlite")
        >>> _get_db_path()
        'data/my_bot.sqlite'

        >>> set_db_path("/tmp/test.db")
        >>> _get_db_path()
        '/tmp/test.db'
    """
    global _db_path
    _db_path = path


def _get_db_path() -> str:
    """Return the current SQLite database file path.

    Examples:
        >>> set_db_path("job_bot.sqlite")
        >>> _get_db_path()
        'job_bot.sqlite'

        >>> set_db_path("prod/data.db")
        >>> _get_db_path()
        'prod/data.db'
    """
    return _db_path


async def init_db() -> None:
    """Create the ``users`` and ``seen_jobs`` tables if they do not exist.

    Examples:
        >>> await init_db()  # first run — tables created
        >>> # Log: "Database initialised at job_bot.sqlite"

        >>> await init_db()  # second run — no-op, tables already exist
        >>> # Log: "Database initialised at job_bot.sqlite"
    """
    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id   INTEGER PRIMARY KEY,
                chat_id   INTEGER NOT NULL,
                roles     TEXT    NOT NULL DEFAULT '[]',
                years_exp TEXT    NOT NULL DEFAULT '',
                locations TEXT    NOT NULL DEFAULT '[]',
                work_mode TEXT    NOT NULL DEFAULT '',
                is_paused INTEGER NOT NULL DEFAULT 0,
                created_at TEXT   DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT   DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS seen_jobs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                source     TEXT    NOT NULL,
                job_key    TEXT    NOT NULL,
                title      TEXT,
                url        TEXT,
                created_at TEXT    DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, source, job_key)
            )
        """)
        await db.commit()
    logger.info("Database initialised at %s", _get_db_path())


async def save_user(prefs: UserPreferences) -> None:
    """Insert or update a user's preferences in the ``users`` table.

    Uses SQLite ``ON CONFLICT`` to upsert — a new row is inserted on first
    call, and subsequent calls for the same ``user_id`` update in place.

    Examples:
        >>> prefs = UserPreferences(user_id=42, chat_id=42, roles=["DevOps Engineer"], years_exp="3-5",
        ...                         locations=["Tel Aviv"], work_mode="Hybrid")
        >>> await save_user(prefs)  # row inserted for user 42

        >>> prefs.work_mode = "Remote"
        >>> await save_user(prefs)  # row for user 42 updated with new work_mode
    """
    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, chat_id, roles, years_exp, locations, work_mode, is_paused, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                chat_id   = excluded.chat_id,
                roles     = excluded.roles,
                years_exp = excluded.years_exp,
                locations = excluded.locations,
                work_mode = excluded.work_mode,
                is_paused = excluded.is_paused,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                prefs.user_id,
                prefs.chat_id,
                json.dumps(prefs.roles),
                prefs.years_exp,
                json.dumps(prefs.locations),
                prefs.work_mode,
                int(prefs.is_paused),
            ),
        )
        await db.commit()


async def get_user(user_id: int) -> UserPreferences | None:
    """Fetch a single user's preferences by Telegram user ID.

    Returns ``None`` when the user has not completed onboarding.

    Examples:
        >>> await get_user(42)
        UserPreferences(user_id=42, chat_id=42, roles=["DevOps Engineer"], ...)

        >>> await get_user(9999)  # unknown user
        None
    """
    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_prefs(row)


async def get_active_users() -> list[UserPreferences]:
    """Return all users whose alerts are not paused (``is_paused = 0``).

    Examples:
        >>> await get_active_users()  # two active users in DB
        [UserPreferences(user_id=42, ..., is_paused=False),
         UserPreferences(user_id=99, ..., is_paused=False)]

        >>> await get_active_users()  # no users or all paused
        []
    """
    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE is_paused = 0")
        rows = await cursor.fetchall()
        return [_row_to_prefs(r) for r in rows]


async def set_paused(user_id: int, paused: bool) -> None:
    """Toggle the ``is_paused`` flag for a user.

    Examples:
        >>> await set_paused(42, True)   # user 42 will no longer receive alerts
        >>> (await get_user(42)).is_paused
        True

        >>> await set_paused(42, False)  # alerts re-enabled
        >>> (await get_user(42)).is_paused
        False
    """
    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(
            "UPDATE users SET is_paused = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (int(paused), user_id),
        )
        await db.commit()


async def is_job_seen(user_id: int, source: str, job_key: str) -> bool:
    """Check whether a specific job has already been sent to a user.

    Examples:
        >>> await is_job_seen(42, "arbeitnow", "senior-fe-dev-berlin")
        False  # first encounter

        >>> await mark_job_seen(42, "arbeitnow", "senior-fe-dev-berlin", "Senior FE Dev", "https://...")
        >>> await is_job_seen(42, "arbeitnow", "senior-fe-dev-berlin")
        True
    """
    async with aiosqlite.connect(_get_db_path()) as db:
        cursor = await db.execute(
            "SELECT 1 FROM seen_jobs WHERE user_id = ? AND source = ? AND job_key = ?",
            (user_id, source, job_key),
        )
        return await cursor.fetchone() is not None


async def mark_job_seen(
    user_id: int, source: str, job_key: str, title: str, url: str
) -> None:
    """Record that a job has been sent to a user so it won't be sent again.

    Duplicate inserts are silently ignored via ``INSERT OR IGNORE``.

    Examples:
        >>> await mark_job_seen(42, "remotive", "12345", "ML Engineer", "https://remotive.com/jobs/12345")
        >>> await is_job_seen(42, "remotive", "12345")
        True

        >>> await mark_job_seen(42, "remotive", "12345", "ML Engineer", "https://remotive.com/jobs/12345")
        >>> # no error — duplicate silently ignored
    """
    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO seen_jobs (user_id, source, job_key, title, url)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, source, job_key, title, url),
        )
        await db.commit()


def _row_to_prefs(row: aiosqlite.Row) -> UserPreferences:
    """Convert a raw SQLite Row into a UserPreferences dataclass.

    JSON-encoded columns (``roles``, ``locations``) are deserialised and
    the integer ``is_paused`` is cast to ``bool``.

    Examples:
        >>> row = {"user_id": 42, "chat_id": 42, "roles": '["QA Engineer"]',
        ...        "years_exp": "1-3", "locations": '["North"]', "work_mode": "Remote", "is_paused": 0}
        >>> _row_to_prefs(row)
        UserPreferences(user_id=42, chat_id=42, roles=["QA Engineer"], years_exp="1-3",
                        locations=["North"], work_mode="Remote", is_paused=False)

        >>> row = {"user_id": 7, "chat_id": 7, "roles": '[]', "years_exp": "",
        ...        "locations": '[]', "work_mode": "", "is_paused": 1}
        >>> _row_to_prefs(row)
        UserPreferences(user_id=7, chat_id=7, roles=[], years_exp="",
                        locations=[], work_mode="", is_paused=True)
    """
    return UserPreferences(
        user_id=row["user_id"],
        chat_id=row["chat_id"],
        roles=json.loads(row["roles"]),
        years_exp=row["years_exp"],
        locations=json.loads(row["locations"]),
        work_mode=row["work_mode"],
        is_paused=bool(row["is_paused"]),
    )
