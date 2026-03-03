from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot

from src import db
from src.config import Config
from src.models import JobPost, UserPreferences
from src.providers import get_enabled_providers
from src.providers.base import JobProvider

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_providers: list[JobProvider] = []
_bot: Bot | None = None


def init_scheduler(config: Config, bot: Bot) -> AsyncIOScheduler:
    """Create and configure the APScheduler that runs periodic job searches.

    Stores the bot instance and enabled providers in module-level state so the
    scheduled callback can use them.

    Examples:
        >>> scheduler = init_scheduler(config, app.bot)
        >>> scheduler.start()
        # Log: "Scheduler configured: every 2h, providers: ['arbeitnow', 'remotive']"

        >>> scheduler = init_scheduler(config_no_providers, app.bot)
        >>> scheduler.start()
        # Log: "Scheduler configured: every 2h, providers: []"
    """
    global _providers, _bot
    _providers = get_enabled_providers(config)
    _bot = bot

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _scheduled_search,
        trigger=IntervalTrigger(hours=config.search_interval_hours),
        id="job_search",
        name="Periodic job search",
        replace_existing=True,
    )
    logger.info(
        "Scheduler configured: every %dh, providers: %s",
        config.search_interval_hours,
        [p.name for p in _providers],
    )
    return scheduler


async def _scheduled_search() -> None:
    """Periodic callback invoked by APScheduler every N hours.

    Iterates over all active (non-paused) users and runs a provider search
    for each one, sending new matches via Telegram.

    Examples:
        >>> # 3 active users, providers find new jobs for 2 of them
        >>> await _scheduled_search()
        # Log: "Sent 5 new jobs to user 42"
        # Log: "Sent 0 new jobs to user 99"
        # Log: "Sent 3 new jobs to user 7"

        >>> # no active users
        >>> await _scheduled_search()
        # Log: "No active users, skipping search"
    """
    logger.info("Starting scheduled job search")
    users = await db.get_active_users()
    if not users:
        logger.info("No active users, skipping search")
        return

    for user in users:
        try:
            await _search_for_user(user, _bot)
        except Exception:
            logger.exception("Error searching for user %s", user.user_id)


async def run_now(user_id: int, bot: Bot) -> int:
    """Run an immediate search for a single user (triggered by ``/now``).

    Returns the number of new jobs sent, or 0 if the user is not found.

    Examples:
        >>> await run_now(42, bot)  # 3 new jobs matched and sent
        3

        >>> await run_now(9999, bot)  # user not in DB
        0
    """
    prefs = await db.get_user(user_id)
    if prefs is None:
        return 0
    return await _search_for_user(prefs, bot)


async def _search_for_user(prefs: UserPreferences, bot: Bot) -> int:
    """Query all enabled providers for a user, deduplicate, and send new jobs.

    Returns the total number of new (unseen) jobs sent to the user's chat.

    Examples:
        >>> prefs = UserPreferences(user_id=42, chat_id=42, roles=["Backend Developer"],
        ...                         years_exp="3-5", locations=["Remote-Only"], work_mode="Remote")
        >>> await _search_for_user(prefs, bot)
        7  # 7 new jobs sent

        >>> await _search_for_user(prefs, bot)  # called again immediately
        0  # all jobs already marked seen
    """
    sent_count = 0
    for provider in _providers:
        try:
            jobs = await provider.search(prefs)
        except Exception:
            logger.exception("Provider %s failed for user %s", provider.name, prefs.user_id)
            continue

        for job in jobs:
            job_key = _job_key(job)
            if await db.is_job_seen(prefs.user_id, provider.name, job_key):
                continue

            await _send_job(bot, prefs.chat_id, job)
            await db.mark_job_seen(prefs.user_id, provider.name, job_key, job.title, job.url)
            sent_count += 1

    logger.info("Sent %d new jobs to user %s", sent_count, prefs.user_id)
    return sent_count


def _job_key(job: JobPost) -> str:
    """Derive a stable deduplication key for a job post.

    Uses the provider-assigned ``job_id`` when available; otherwise falls back
    to an MD5 hash of the URL.

    Examples:
        >>> _job_key(JobPost(source="arbeitnow", job_id="fe-dev-berlin", title="", company="",
        ...                  location="", url="https://example.com/fe-dev-berlin"))
        'fe-dev-berlin'

        >>> _job_key(JobPost(source="remotive", job_id="", title="", company="",
        ...                  location="", url="https://example.com/job/99"))
        '2942e94eaa57aefc1b1d76e4e3ae1f6f'  # md5 of the URL
    """
    if job.job_id and job.job_id != job.url:
        return job.job_id
    return hashlib.md5(job.url.encode()).hexdigest()


async def _send_job(bot: Bot, chat_id: int, job: JobPost) -> None:
    """Format a single JobPost as a Markdown message and send it to the user.

    Examples:
        >>> job = JobPost(source="arbeitnow", job_id="1", title="Backend Developer",
        ...               company="Acme", location="Berlin", url="https://acme.com/jobs/1")
        >>> await _send_job(bot, chat_id=42, job=job)
        # Sends: "💼 *Backend Developer*\n🏢 Acme\n📍 Berlin\n🔗 [View Job](...)"

        >>> job = JobPost(source="remotive", job_id="2", title="ML Engineer",
        ...               company="DeepCo", location="", url="https://deepco.ai/2", remote=True)
        >>> await _send_job(bot, chat_id=42, job=job)
        # Sends: "💼 *ML Engineer*\n🏢 DeepCo\n📍 Remote\n🔗 [View Job](...)"
    """
    location_text = job.location or ("Remote" if job.remote else "N/A")
    text = (
        f"\U0001F4BC *{_escape_md(job.title)}*\n"
        f"\U0001F3E2 {_escape_md(job.company)}\n"
        f"\U0001F4CD {_escape_md(location_text)}\n"
        f"\U0001F517 [View Job]({job.url})"
    )
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
    except Exception:
        logger.exception("Failed to send job to chat %s", chat_id)


def _escape_md(text: str) -> str:
    """Escape special Markdown characters so text renders literally in Telegram.

    Examples:
        >>> _escape_md("Full-Stack (Senior)")
        'Full\\-Stack \\(Senior\\)'

        >>> _escape_md("Acme Inc.")
        'Acme Inc\\.'
    """
    for char in ("_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"):
        text = text.replace(char, f"\\{char}")
    return text
