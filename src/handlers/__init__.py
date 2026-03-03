from __future__ import annotations

from telegram.ext import Application

from src.handlers.start import get_conversation_handler
from src.handlers.commands import register_commands


def register_handlers(app: Application) -> None:
    """Attach all bot handlers (conversation + commands) to the Application.

    Must be called once before ``app.run_polling()``.

    Examples:
        >>> register_handlers(app)
        # ConversationHandler for /start + all command handlers registered

        >>> register_handlers(app)  # calling twice adds duplicate handlers
        # (avoid — call only once during startup)
    """
    app.add_handler(get_conversation_handler())
    register_commands(app)
