from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
)

from src import db
from src.models import (
    AVAILABLE_ROLES,
    EXPERIENCE_OPTIONS,
    LOCATION_OPTIONS,
    WORK_MODE_OPTIONS,
    UserPreferences,
)

logger = logging.getLogger(__name__)

SELECTING_ROLES, SELECTING_EXPERIENCE, SELECTING_LOCATIONS, SELECTING_MODE, CONFIRMATION = range(5)

_CHECK = "\u2705"


# ── /start entry ──────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the ``/start`` command — reset state and show role-selection keyboard.

    Initialises empty selections in ``context.user_data`` and returns the
    ``SELECTING_ROLES`` conversation state.

    Examples:
        >>> # User sends /start
        >>> state = await start_command(update, context)
        >>> state == SELECTING_ROLES
        True  # bot replies with welcome text + role keyboard

        >>> # User sends /start a second time (re-onboarding)
        >>> state = await start_command(update, context)
        >>> context.user_data["selected_roles"]
        set()  # selections are reset
    """
    context.user_data["selected_roles"] = set()
    context.user_data["selected_locations"] = set()
    context.user_data["years_exp"] = ""
    context.user_data["work_mode"] = ""

    await update.message.reply_text(
        "Welcome to *Job Alert Bot*\\! \U0001F4BC\n\n"
        "I'll help you find matching job posts from public job boards\\.\n"
        "Let's set up your preferences\\.\n\n"
        "First, select the *job roles* you're interested in, then tap *Done*\\.",
        parse_mode="MarkdownV2",
        reply_markup=_roles_keyboard(set()),
    )
    return SELECTING_ROLES


# ── Role selection (multi-select) ────────────────────────────

def _roles_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    """Build an InlineKeyboard for role multi-selection with checkmarks.

    Roles already in ``selected`` are prefixed with a green checkmark.
    A "Done" button is appended as the last row.

    Examples:
        >>> kb = _roles_keyboard(set())
        >>> kb.inline_keyboard[0][0].text
        'Software Engineer'  # no checkmark

        >>> kb = _roles_keyboard({"Software Engineer"})
        >>> kb.inline_keyboard[0][0].text
        '✅ Software Engineer'  # checkmark shown
    """
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, role in enumerate(AVAILABLE_ROLES):
        label = f"{_CHECK} {role}" if role in selected else role
        row.append(InlineKeyboardButton(label, callback_data=f"role:{role}"))
        if len(row) == 2 or i == len(AVAILABLE_ROLES) - 1:
            buttons.append(row)
            row = []
    buttons.append([InlineKeyboardButton("\u2714\ufe0f Done", callback_data="roles_done")])
    return InlineKeyboardMarkup(buttons)


async def toggle_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle a role on/off when the user taps a role button.

    Adds the role to the selection set if absent, removes it if present,
    then refreshes the keyboard. Stays in ``SELECTING_ROLES`` state.

    Examples:
        >>> # callback_data="role:DevOps Engineer", not yet selected
        >>> state = await toggle_role(update, context)
        >>> "DevOps Engineer" in context.user_data["selected_roles"]
        True

        >>> # callback_data="role:DevOps Engineer", already selected
        >>> state = await toggle_role(update, context)
        >>> "DevOps Engineer" in context.user_data["selected_roles"]
        False  # toggled off
    """
    query = update.callback_query
    await query.answer()

    role = query.data.removeprefix("role:")
    selected: set[str] = context.user_data.setdefault("selected_roles", set())

    if role in selected:
        selected.discard(role)
    else:
        selected.add(role)

    await query.edit_message_reply_markup(reply_markup=_roles_keyboard(selected))
    return SELECTING_ROLES


async def roles_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Finalise role selection and advance to the experience step.

    If no roles are selected, shows an alert and stays in the current state.

    Examples:
        >>> # selected_roles = {"Backend Developer", "DevOps Engineer"}
        >>> state = await roles_done(update, context)
        >>> state == SELECTING_EXPERIENCE
        True  # shows experience buttons

        >>> # selected_roles = set()  (empty)
        >>> state = await roles_done(update, context)
        >>> state == SELECTING_ROLES
        True  # alert: "Please select at least one role."
    """
    query = update.callback_query
    await query.answer()

    selected: set[str] = context.user_data.get("selected_roles", set())
    if not selected:
        await query.answer("Please select at least one role.", show_alert=True)
        return SELECTING_ROLES

    buttons = [
        [InlineKeyboardButton(opt, callback_data=f"exp:{opt}")]
        for opt in EXPERIENCE_OPTIONS
    ]
    await query.edit_message_text(
        "Great! Now select your *years of experience*:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return SELECTING_EXPERIENCE


# ── Experience selection (single-select) ─────────────────────

async def select_experience(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the chosen experience range and advance to location selection.

    Examples:
        >>> # callback_data="exp:3-5"
        >>> state = await select_experience(update, context)
        >>> context.user_data["years_exp"]
        '3-5'
        >>> state == SELECTING_LOCATIONS
        True

        >>> # callback_data="exp:8+"
        >>> state = await select_experience(update, context)
        >>> context.user_data["years_exp"]
        '8+'
    """
    query = update.callback_query
    await query.answer()

    exp = query.data.removeprefix("exp:")
    context.user_data["years_exp"] = exp

    await query.edit_message_text(
        "Now select your *preferred locations* (tap to toggle, then *Done*):",
        parse_mode="Markdown",
        reply_markup=_locations_keyboard(set()),
    )
    return SELECTING_LOCATIONS


# ── Location selection (multi-select) ────────────────────────

def _locations_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    """Build an InlineKeyboard for location multi-selection with checkmarks.

    Same pattern as ``_roles_keyboard`` — selected items get a checkmark
    prefix, with a "Done" button at the bottom.

    Examples:
        >>> kb = _locations_keyboard(set())
        >>> kb.inline_keyboard[0][0].text
        'South'

        >>> kb = _locations_keyboard({"Tel Aviv", "Remote-Only"})
        >>> any("✅ Tel Aviv" in btn.text for row in kb.inline_keyboard for btn in row)
        True
    """
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, loc in enumerate(LOCATION_OPTIONS):
        label = f"{_CHECK} {loc}" if loc in selected else loc
        row.append(InlineKeyboardButton(label, callback_data=f"loc:{loc}"))
        if len(row) == 2 or i == len(LOCATION_OPTIONS) - 1:
            buttons.append(row)
            row = []
    buttons.append([InlineKeyboardButton("\u2714\ufe0f Done", callback_data="locs_done")])
    return InlineKeyboardMarkup(buttons)


async def toggle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle a location on/off when the user taps a location button.

    Mirrors ``toggle_role`` logic for the location multi-select step.

    Examples:
        >>> # callback_data="loc:Tel Aviv", not yet selected
        >>> state = await toggle_location(update, context)
        >>> "Tel Aviv" in context.user_data["selected_locations"]
        True

        >>> # callback_data="loc:Tel Aviv", already selected
        >>> state = await toggle_location(update, context)
        >>> "Tel Aviv" in context.user_data["selected_locations"]
        False
    """
    query = update.callback_query
    await query.answer()

    loc = query.data.removeprefix("loc:")
    selected: set[str] = context.user_data.setdefault("selected_locations", set())

    if loc in selected:
        selected.discard(loc)
    else:
        selected.add(loc)

    await query.edit_message_reply_markup(reply_markup=_locations_keyboard(selected))
    return SELECTING_LOCATIONS


async def locations_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Finalise location selection and advance to work-mode step.

    Requires at least one location to be selected.

    Examples:
        >>> # selected_locations = {"Center", "Remote-Only"}
        >>> state = await locations_done(update, context)
        >>> state == SELECTING_MODE
        True  # shows On-site / Hybrid / Remote buttons

        >>> # selected_locations = set()
        >>> state = await locations_done(update, context)
        >>> state == SELECTING_LOCATIONS
        True  # alert shown, stays on location step
    """
    query = update.callback_query
    await query.answer()

    selected: set[str] = context.user_data.get("selected_locations", set())
    if not selected:
        await query.answer("Please select at least one location.", show_alert=True)
        return SELECTING_LOCATIONS

    buttons = [
        [InlineKeyboardButton(mode, callback_data=f"mode:{mode}")]
        for mode in WORK_MODE_OPTIONS
    ]
    await query.edit_message_text(
        "Almost done! Select your preferred *work mode*:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return SELECTING_MODE


# ── Work-mode selection (single-select) ──────────────────────

async def select_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the chosen work mode and show the confirmation summary.

    Examples:
        >>> # callback_data="mode:Remote"
        >>> state = await select_mode(update, context)
        >>> context.user_data["work_mode"]
        'Remote'
        >>> state == CONFIRMATION
        True

        >>> # callback_data="mode:Hybrid"
        >>> state = await select_mode(update, context)
        >>> context.user_data["work_mode"]
        'Hybrid'
    """
    query = update.callback_query
    await query.answer()

    mode = query.data.removeprefix("mode:")
    context.user_data["work_mode"] = mode

    return await _show_confirmation(query, context)


# ── Confirmation ─────────────────────────────────────────────

async def _show_confirmation(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render a summary of all selected preferences with Save / Edit buttons.

    Examples:
        >>> # user_data = {selected_roles: {"QA Engineer"}, years_exp: "1-3",
        ... #              selected_locations: {"North"}, work_mode: "On-site"}
        >>> state = await _show_confirmation(query, context)
        >>> state == CONFIRMATION
        True
        # Message: "Roles: QA Engineer | Experience: 1-3 years | ..."

        >>> # user_data with multiple roles and locations
        >>> state = await _show_confirmation(query, context)
        # Message lists all roles comma-separated, all locations comma-separated
    """
    ud = context.user_data
    roles = ", ".join(sorted(ud.get("selected_roles", [])))
    exp = ud.get("years_exp", "?")
    locs = ", ".join(sorted(ud.get("selected_locations", [])))
    mode = ud.get("work_mode", "?")

    text = (
        "*Your Preferences*\n\n"
        f"*Roles:* {roles}\n"
        f"*Experience:* {exp} years\n"
        f"*Locations:* {locs}\n"
        f"*Work mode:* {mode}\n\n"
        "Tap *Save* to confirm or *Edit* to start over."
    )
    buttons = [
        [
            InlineKeyboardButton("\U0001F4BE Save", callback_data="confirm_save"),
            InlineKeyboardButton("\u270f\ufe0f Edit", callback_data="confirm_edit"),
        ]
    ]
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return CONFIRMATION


async def confirm_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Persist user preferences to SQLite and end the conversation.

    Examples:
        >>> # User taps "Save" with roles={"Backend Developer"}, exp="3-5", etc.
        >>> state = await confirm_save(update, context)
        >>> state == ConversationHandler.END
        True  # preferences written to DB, confirmation message sent

        >>> prefs = await db.get_user(update.effective_user.id)
        >>> prefs.roles
        ['Backend Developer']
    """
    query = update.callback_query
    await query.answer()

    ud = context.user_data
    prefs = UserPreferences(
        user_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        roles=sorted(ud.get("selected_roles", [])),
        years_exp=ud.get("years_exp", ""),
        locations=sorted(ud.get("selected_locations", [])),
        work_mode=ud.get("work_mode", ""),
    )
    await db.save_user(prefs)

    await query.edit_message_text(
        "\u2705 Preferences saved! You'll start receiving job alerts.\n\n"
        "Use /now to search immediately or /help to see all commands."
    )
    logger.info("User %s saved preferences: %s", prefs.user_id, prefs)
    return ConversationHandler.END


async def confirm_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Reset selections and restart the onboarding flow from role selection.

    Called when the user taps "Edit" on the confirmation screen.

    Examples:
        >>> # User taps "Edit"
        >>> state = await confirm_edit(update, context)
        >>> state == SELECTING_ROLES
        True

        >>> context.user_data["selected_roles"]
        set()  # cleared for fresh selection
    """
    query = update.callback_query
    await query.answer()

    context.user_data["selected_roles"] = set()
    context.user_data["selected_locations"] = set()

    await query.edit_message_text(
        "Let's start over. Select the *job roles* you're interested in:",
        parse_mode="Markdown",
        reply_markup=_roles_keyboard(set()),
    )
    return SELECTING_ROLES


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle ``/cancel`` — abort the onboarding conversation.

    Examples:
        >>> # User sends /cancel mid-onboarding
        >>> state = await cancel(update, context)
        >>> state == ConversationHandler.END
        True  # bot: "Setup cancelled. Use /start to begin again."

        >>> # User sends /cancel even if nothing was in progress
        >>> state = await cancel(update, context)
        >>> state == ConversationHandler.END
        True
    """
    await update.message.reply_text("Setup cancelled. Use /start to begin again.")
    return ConversationHandler.END


# ── Build handler ────────────────────────────────────────────

def get_conversation_handler() -> ConversationHandler:
    """Build and return the onboarding ConversationHandler.

    The handler walks the user through five states: role selection,
    experience, location selection, work mode, and confirmation.

    Examples:
        >>> handler = get_conversation_handler()
        >>> len(handler.states)
        5  # SELECTING_ROLES .. CONFIRMATION

        >>> handler.entry_points[0].commands
        frozenset({'start'})  # triggered by /start
    """
    return ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            SELECTING_ROLES: [
                CallbackQueryHandler(toggle_role, pattern=r"^role:"),
                CallbackQueryHandler(roles_done, pattern=r"^roles_done$"),
            ],
            SELECTING_EXPERIENCE: [
                CallbackQueryHandler(select_experience, pattern=r"^exp:"),
            ],
            SELECTING_LOCATIONS: [
                CallbackQueryHandler(toggle_location, pattern=r"^loc:"),
                CallbackQueryHandler(locations_done, pattern=r"^locs_done$"),
            ],
            SELECTING_MODE: [
                CallbackQueryHandler(select_mode, pattern=r"^mode:"),
            ],
            CONFIRMATION: [
                CallbackQueryHandler(confirm_save, pattern=r"^confirm_save$"),
                CallbackQueryHandler(confirm_edit, pattern=r"^confirm_edit$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
