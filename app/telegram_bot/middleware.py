from functools import wraps
from typing import Any, Callable

from telegram import Update
from telegram.ext import ContextTypes

from app.core.config import settings


def is_admin(user_id: int) -> bool:
    """Check if a Telegram user is the configured admin."""
    return str(user_id) == settings.telegram_admin_user_id


def require_admin(func: Callable) -> Callable:
    """Decorator that restricts a handler to the admin user."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
        if not (settings.telegram_admin_user_id or "").strip():
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⚠️ TELEGRAM_ADMIN_USER_ID is missing in .env. "
                    "Set it to your numeric Telegram user id (same account you use with the bot), "
                    "then restart. Until then, /status and other admin commands will not run."
                )
            return
        user = update.effective_user
        if not user or not is_admin(user.id):
            if update.effective_message:
                await update.effective_message.reply_text("⛔ Unauthorized")
            return
        return await func(update, context)

    return wrapper
