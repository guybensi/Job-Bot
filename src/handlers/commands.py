from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from src import db

logger = logging.getLogger(__name__)

_scheduler_run_now = None


def set_run_now_callback(fn) -> None:
    """Register the scheduler's ``run_now`` function so ``/now`` can call it.

    This avoids a circular import between handlers and the scheduler module.

    Examples:
        >>> set_run_now_callback(run_now)
        >>> _scheduler_run_now is run_now
        True

        >>> set_run_now_callback(None)
        >>> _scheduler_run_now is None
        True  # /now will reply "Scheduler is not available"
    """
    global _scheduler_run_now
    _scheduler_run_now = fn


async def now_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/now`` — trigger an immediate job search for the calling user.

    Reports how many new jobs were found, or prompts to set up first.

    Examples:
        >>> # User 42 has prefs, providers find 5 new jobs
        >>> await now_command(update, context)
        # Bot: "🔍 Searching..." then "Done! Sent you 5 new job(s)."

        >>> # User 99 has no saved prefs
        >>> await now_command(update, context)
        # Bot: "Set up your preferences first with /start."
    """
    user_id = update.effective_user.id
    prefs = await db.get_user(user_id)

    if prefs is None:
        await update.message.reply_text("Set up your preferences first with /start.")
        return

    await update.message.reply_text("\U0001F50D Searching for jobs now...")

    if _scheduler_run_now:
        count = await _scheduler_run_now(user_id, context.bot)
        if count == 0:
            await update.message.reply_text("No new matching jobs found right now. I'll keep looking!")
        else:
            await update.message.reply_text(f"Done! Sent you {count} new job(s).")
    else:
        await update.message.reply_text("Scheduler is not available. Try again later.")


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/pause`` — stop scheduled alerts for the calling user.

    Examples:
        >>> # User 42 has active alerts
        >>> await pause_command(update, context)
        # Bot: "⏸ Alerts paused. Use /resume to start receiving them again."

        >>> # User 99 hasn't set up yet
        >>> await pause_command(update, context)
        # Bot: "Set up your preferences first with /start."
    """
    user_id = update.effective_user.id
    prefs = await db.get_user(user_id)

    if prefs is None:
        await update.message.reply_text("Set up your preferences first with /start.")
        return

    await db.set_paused(user_id, True)
    await update.message.reply_text(
        "\u23f8 Alerts paused. Use /resume to start receiving them again."
    )
    logger.info("User %s paused alerts", user_id)


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/resume`` — re-enable scheduled alerts for the calling user.

    Examples:
        >>> # User 42 was paused
        >>> await resume_command(update, context)
        # Bot: "▶️ Alerts resumed! You'll receive new job matches."

        >>> # User 99 hasn't set up yet
        >>> await resume_command(update, context)
        # Bot: "Set up your preferences first with /start."
    """
    user_id = update.effective_user.id
    prefs = await db.get_user(user_id)

    if prefs is None:
        await update.message.reply_text("Set up your preferences first with /start.")
        return

    await db.set_paused(user_id, False)
    await update.message.reply_text(
        "\u25b6\ufe0f Alerts resumed! You'll receive new job matches."
    )
    logger.info("User %s resumed alerts", user_id)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/help`` — display the list of available bot commands.

    Examples:
        >>> await help_command(update, context)
        # Bot replies with formatted command list including /start, /now, etc.

        >>> # Works for any user regardless of onboarding state
        >>> await help_command(update, context)
        # Always replies with the same static help text
    """
    text = (
        "*Job Alert Bot — Commands*\n\n"
        "/start — Set up your job preferences\n"
        "/preferences — View or edit saved preferences\n"
        "/now — Run a job search right now\n"
        "/pause — Pause scheduled alerts\n"
        "/resume — Resume scheduled alerts\n"
        "/help — Show this help message"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


def register_commands(app: Application) -> None:
    """Register all non-conversation command handlers on the Application.

    Includes ``/now``, ``/pause``, ``/resume``, ``/help``, and the
    ``/preferences`` handler group.

    Examples:
        >>> register_commands(app)
        # 5 handlers added: now, pause, resume, help, preferences (+edit callback)

        >>> len(app.handlers[0])  # group 0
        ... # increases by the number of registered handlers
    """
    from src.handlers.preferences import get_preferences_handlers

    app.add_handler(CommandHandler("now", now_command))
    app.add_handler(CommandHandler("pause", pause_command))
    app.add_handler(CommandHandler("resume", resume_command))
    app.add_handler(CommandHandler("help", help_command))

    for handler in get_preferences_handlers():
        app.add_handler(handler)
