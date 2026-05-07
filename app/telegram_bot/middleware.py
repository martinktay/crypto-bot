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
        user = update.effective_user
        if not user or not is_admin(user.id):
            if update.effective_message:
                await update.effective_message.reply_text("⛔ Unauthorized")
            return
        return await func(update, context)

    return wrapper
