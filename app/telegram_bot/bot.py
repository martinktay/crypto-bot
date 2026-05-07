"""Telegram bot lifecycle management."""

from __future__ import annotations

import logging

from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from app.core.config import settings

from app.telegram_bot.handlers import (
    approval_callback,
    balance_command,
    backtest_command,
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
    why_command,
)

logger = logging.getLogger(__name__)

_application: Application | None = None


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
        return

    _application = Application.builder().token(token).build()

    # Register command handlers
    _application.add_handler(CommandHandler("start", start_command))
    _application.add_handler(CommandHandler("help", help_command))
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

    # Register callback handler for approval buttons
    _application.add_handler(CallbackQueryHandler(approval_callback))

    await _application.initialize()
    await _application.start()
    await _register_command_menus(_application)
    await _application.updater.start_polling(drop_pending_updates=True)
    logger.info("Telegram bot started")


async def stop_bot() -> None:
    """Stop the Telegram bot."""
    global _application
    if _application is None:
        return
    await _application.updater.stop()
    await _application.stop()
    await _application.shutdown()
    _application = None
    logger.info("Telegram bot stopped")


def get_bot_application() -> Application | None:
    """Return the running Application instance or None."""
    return _application
