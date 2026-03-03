from __future__ import annotations

import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from telegram.ext import Application

from src.config import Config, load_config
from src import db
from src.handlers import register_handlers
from src.handlers.commands import set_run_now_callback
from src.scheduler import init_scheduler, run_now


def _setup_logging(config: Config) -> None:
    """Configure root logger with console and rotating file handlers.

    Creates a ``logs/`` directory if it doesn't exist. Third-party loggers
    (httpx, apscheduler) are quieted to WARNING.

    Examples:
        >>> _setup_logging(Config(telegram_bot_token="t", log_level="DEBUG"))
        # Root logger set to DEBUG, logs/bot.log created

        >>> _setup_logging(Config(telegram_bot_token="t", log_level="WARNING"))
        # Root logger set to WARNING, only warnings and above appear
    """
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.log_level, logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root_logger.addHandler(console)

    file_handler = RotatingFileHandler(
        log_dir / "bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root_logger.addHandler(file_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


_scheduler = None


async def post_init(application: Application) -> None:
    """Called by python-telegram-bot after the Application is built.

    Initialises the database, starts the APScheduler (now that an event loop
    is running), and registers bot commands with BotFather.

    Examples:
        >>> await post_init(app)
        # DB tables created, scheduler started, 6 commands registered

        >>> await post_init(app)  # idempotent — safe to call again
        # Tables already exist, commands re-registered
    """
    await db.init_db()

    if _scheduler and not _scheduler.running:
        _scheduler.start()
        logging.getLogger(__name__).info("Scheduler started inside event loop")

    commands = [
        ("start", "Set up your job preferences"),
        ("preferences", "View or edit saved preferences"),
        ("now", "Run a job search now"),
        ("pause", "Pause scheduled alerts"),
        ("resume", "Resume scheduled alerts"),
        ("help", "Show available commands"),
    ]
    await application.bot.set_my_commands(commands)


def main() -> None:
    """Application entry point — load config, wire components, start polling.

    Examples:
        >>> main()  # with valid .env
        # Bot starts polling, scheduler ticks every 2 hours

        >>> main()  # with missing TELEGRAM_BOT_TOKEN
        # Prints "ERROR: TELEGRAM_BOT_TOKEN is not set in .env" and exits
    """
    global _scheduler

    config = load_config()
    _setup_logging(config)

    logger = logging.getLogger(__name__)
    logger.info("Starting Job Alert Bot")

    db.set_db_path(config.db_path)

    app = Application.builder().token(config.telegram_bot_token).post_init(post_init).build()

    register_handlers(app)
    set_run_now_callback(run_now)

    _scheduler = init_scheduler(config, app.bot)

    logger.info("Bot is running — polling for updates")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
