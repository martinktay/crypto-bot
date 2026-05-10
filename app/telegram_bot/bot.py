"""Telegram bot lifecycle management."""

from __future__ import annotations

import logging

from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeDefault, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app.core.config import settings
from app.utils.agent_debug_log import agent_debug_log

from app.telegram_bot.handlers import (
    balance_command,
    backtest_command,
    chatinfo_command,
    help_command,
    insights_command,
    mode_command,
    optimize_command,
    pause_command,
    positions_command,
    rejected_command,
    resume_command,
    signals_command,
    status_command,
    start_command,
    telegramtest_command,
    why_command,
)

logger = logging.getLogger(__name__)

_application: Application | None = None


async def _telegram_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    # #region agent log
    agent_debug_log(
        "bot.py:_telegram_error_handler",
        "handler error",
        "H3",
        error_type=type(err).__name__ if err else None,
        error_msg=(str(err)[:400] if err else None),
        has_update=update is not None,
    )
    # #endregion
    if err:
        logger.error(
            "Telegram handler error: %s",
            err,
            exc_info=(type(err), err, err.__traceback__)
            if isinstance(err, BaseException)
            else None,
        )
    if isinstance(update, Update) and update.effective_message:
        try:
            from telegram.error import BadRequest

            hint = "Try again in a moment. If it keeps failing, restart the bot."
            if isinstance(err, BadRequest):
                hint = (
                    "Telegram rejected the reply (often a formatting issue). "
                    "This build uses HTML for /status and /signals — retry the command."
                )
            await update.effective_message.reply_text(f"⚠️ Command failed. {hint}")
        except Exception:
            pass


def _public_commands() -> list[BotCommand]:
    return [
        BotCommand("start", "Welcome"),
        BotCommand("help", "Show help"),
    ]


def _full_commands() -> list[BotCommand]:
    return [
        BotCommand("start", "Welcome"),
        BotCommand("help", "Show help"),
        BotCommand("status", "Bot status"),
        BotCommand("signals", "Recent signals"),
        BotCommand("positions", "Positions (if applicable)"),
        BotCommand("balance", "Balance (if applicable)"),
        BotCommand("mode", "Current mode"),
        BotCommand("pause", "Pause scanning"),
        BotCommand("resume", "Resume scanning"),
        BotCommand("why", "Explain last signal"),
        BotCommand("insights", "Signal analytics"),
        BotCommand("backtest", "Run backtest"),
        BotCommand("rejected", "View filtered signals"),
        BotCommand("optimize", "Run optimization (advisory)"),
        BotCommand("chatinfo", "Show chat id for .env"),
        BotCommand("telegramtest", "Ping broadcast chats"),
    ]


async def _register_command_menus(application: Application) -> None:
    """
    Configure Telegram's native "/" command menu.

    - Default scope (incl. groups): minimal public commands only.
    - Admin chat: full command set.

    The full set is intentionally NOT exposed in the group menu — admin
    commands are still authorized server-side, but listing them publicly
    is unnecessary information disclosure.
    """
    try:
        await application.bot.set_my_commands(
            _public_commands(), scope=BotCommandScopeDefault()
        )
        if settings.telegram_admin_chat_id:
            await application.bot.set_my_commands(
                _full_commands(),
                scope=BotCommandScopeChat(chat_id=settings.telegram_admin_chat_id),
            )
        if settings.telegram_group_chat_id:
            # Public-only commands in the group menu, by design.
            await application.bot.set_my_commands(
                _public_commands(),
                scope=BotCommandScopeChat(chat_id=settings.telegram_group_chat_id),
            )
    except Exception as exc:
        logger.warning("Failed to register Telegram command menus: %s", exc.__class__.__name__)


async def start_bot(token: str) -> None:
    """Initialize and start the Telegram bot with polling."""
    global _application
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set, skipping bot startup")
        # #region agent log
        agent_debug_log("bot.py:start_bot", "skip no token", "H1", skipped=True)
        # #endregion
        return

    _application = Application.builder().token(token).build()
    _application.add_error_handler(_telegram_error_handler)

    # Register command handlers
    _application.add_handler(CommandHandler("start", start_command))
    _application.add_handler(CommandHandler("help", help_command))
    _application.add_handler(CommandHandler("chatinfo", chatinfo_command))
    _application.add_handler(CommandHandler("status", status_command))
    _application.add_handler(CommandHandler("signals", signals_command))
    _application.add_handler(CommandHandler("positions", positions_command))
    _application.add_handler(CommandHandler("balance", balance_command))
    _application.add_handler(CommandHandler("mode", mode_command))
    _application.add_handler(CommandHandler("pause", pause_command))
    _application.add_handler(CommandHandler("resume", resume_command))
    _application.add_handler(CommandHandler("why", why_command))
    _application.add_handler(CommandHandler("insights", insights_command))
    _application.add_handler(CommandHandler("backtest", backtest_command))
    _application.add_handler(CommandHandler("rejected", rejected_command))
    _application.add_handler(CommandHandler("optimize", optimize_command))
    _application.add_handler(CommandHandler("telegramtest", telegramtest_command))

    await _application.initialize()
    await _application.start()
    await _register_command_menus(_application)
    # If this bot had a webhook set (e.g. another host or BotFather test), polling receives nothing.
    wi = await _application.bot.get_webhook_info()
    # #region agent log
    agent_debug_log(
        "bot.py:start_bot",
        "webhook info before delete_webhook",
        "H5",
        has_webhook_url=bool(wi.url),
        pending_updates=wi.pending_update_count,
    )
    # #endregion
    await _application.bot.delete_webhook(drop_pending_updates=True)
    await _application.updater.start_polling(drop_pending_updates=True)
    logger.info("Telegram bot started")
    # #region agent log
    agent_debug_log("bot.py:start_bot", "polling started", "H2", ok=True)
    # #endregion


async def stop_bot() -> None:
    """Stop the Telegram bot.

    Each teardown step is best-effort: if startup aborted before polling
    began (e.g. uvicorn failed to bind its socket), the updater / Application
    will not be in a "running" state and python-telegram-bot raises
    ``RuntimeError("This Updater is not running!")``. Swallowing those keeps
    the *real* startup error visible in the lifespan traceback instead of
    being masked by a noisy shutdown failure.
    """
    global _application
    if _application is None:
        return
    for step_name, coro_factory in (
        ("updater.stop", lambda: _application.updater.stop()),
        ("application.stop", lambda: _application.stop()),
        ("application.shutdown", lambda: _application.shutdown()),
    ):
        try:
            await coro_factory()
        except RuntimeError as exc:
            logger.debug("Telegram bot %s skipped: %s", step_name, exc)
    _application = None
    logger.info("Telegram bot stopped")


def get_bot_application() -> Application | None:
    """Return the running Application instance or None."""
    return _application
