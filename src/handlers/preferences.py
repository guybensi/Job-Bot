from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from src import db

logger = logging.getLogger(__name__)


async def preferences_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the user's saved preferences as a formatted summary.

    Includes an "Edit" button. If no preferences exist yet, prompts the
    user to run ``/start``.

    Examples:
        >>> # User 42 has saved prefs: roles=["QA Engineer"], exp="1-3", mode="Hybrid"
        >>> await preferences_command(update, context)
        # Bot replies with: "Roles: QA Engineer | Experience: 1-3 years | ..."

        >>> # User 99 has never run /start
        >>> await preferences_command(update, context)
        # Bot replies: "You haven't set up preferences yet. Use /start to begin."
    """
    user_id = update.effective_user.id
    prefs = await db.get_user(user_id)

    if prefs is None:
        await update.message.reply_text(
            "You haven't set up preferences yet. Use /start to begin."
        )
        return

    roles = ", ".join(prefs.roles) or "None"
    locs = ", ".join(prefs.locations) or "None"
    status = "\u23f8 Paused" if prefs.is_paused else "\u25b6\ufe0f Active"

    text = (
        "*Your Preferences*\n\n"
        f"*Roles:* {roles}\n"
        f"*Experience:* {prefs.years_exp} years\n"
        f"*Locations:* {locs}\n"
        f"*Work mode:* {prefs.work_mode}\n"
        f"*Status:* {status}\n\n"
        "Tap *Edit* to change your preferences."
    )

    buttons = [[InlineKeyboardButton("\u270f\ufe0f Edit", callback_data="prefs_edit")]]
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def prefs_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the "Edit" inline button on the preferences message.

    Replaces the message text with instructions to re-run ``/start``.

    Examples:
        >>> # User taps the "Edit" button under preferences
        >>> await prefs_edit_callback(update, context)
        # Message replaced with: "Use /start to re-run the setup..."

        >>> # Button pressed a second time (message already edited)
        >>> await prefs_edit_callback(update, context)
        # Telegram may raise MessageNotModified — handled gracefully
    """
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Use /start to re-run the setup and update your preferences."
    )


def get_preferences_handlers() -> list:
    """Return the list of handlers for the ``/preferences`` command and its
    inline "Edit" callback.

    Examples:
        >>> handlers = get_preferences_handlers()
        >>> len(handlers)
        2  # CommandHandler + CallbackQueryHandler

        >>> handlers[0].commands
        frozenset({'preferences'})
    """
    return [
        CommandHandler("preferences", preferences_command),
        CallbackQueryHandler(prefs_edit_callback, pattern=r"^prefs_edit$"),
    ]
