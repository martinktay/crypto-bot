"""Telegram command and callback handlers."""

from __future__ import annotations

import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from app.db.session import SessionLocal
from app.db.repository import StateRepository
from app.services.signal_service import get_pipeline
from app.telegram_bot.middleware import is_admin, require_admin

logger = logging.getLogger(__name__)


# --- Public commands ---


def _admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["/status", "/signals", "/why"],
            ["/mode", "/insights", "/rejected"],
            ["/backtest", "/optimize"],
            ["/pause", "/resume"],
        ],
        resize_keyboard=True,
    )


def _help_text(is_admin_user: bool) -> str:
    base = (
        "📋 *Commands*\n\n"
        "/start — Welcome\n"
        "/help — This help\n"
    )
    if not is_admin_user:
        return base + "\n_Admin commands are only available to the configured admin user._"

    return (
        base
        + "\n"
        "/status — Bot status\n"
        "/signals — Recent signals\n"
        "/why — Last signal explanation\n"
        "/mode — Current mode\n"
        "/insights — Signal analytics\n"
        "/rejected — Recently filtered signals\n"
        "/backtest — Run backtest (args: symbol days)\n"
        "/optimize — Run GA optimization (advisory)\n"
        "/pause — Pause scanning\n"
        "/resume — Resume scanning\n"
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    admin = bool(user and is_admin(user.id))
    await update.message.reply_text(
        "🤖 *Crypto Signal Bot*\n\n"
        "I generate trading signals for BTC/USDT and provide AI-powered market insights.\n\n"
        "Use /help to see available commands.",
        parse_mode="Markdown",
        reply_markup=_admin_menu_keyboard() if admin else None,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    admin = bool(user and is_admin(user.id))
    await update.message.reply_text(
        _help_text(admin),
        parse_mode="Markdown",
        reply_markup=_admin_menu_keyboard() if admin else None,
    )


# --- Admin commands ---


@require_admin
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        repo = StateRepository(db)
        state = repo.get_runtime_state_snapshot()
        lessons = repo.count_knowledge_documents()
        
        await update.message.reply_text(
            "📊 *Bot Status*\n\n"
            f"Approval: `{state.approval_mode.value}`\n"
            f"Paused: {'⏸️ Yes' if state.paused else '▶️ No'}\n"
            f"Strategy: `{state.strategy}`\n"
            f"Lessons Learned: `{lessons}` 🧠\n"
            f"Symbols: {', '.join(state.symbols)}\n"
            f"Timeframes: {', '.join(state.timeframes)}\n"
            f"Pending approvals: {len(state.approvals)}\n",
            parse_mode="Markdown",
        )


@require_admin
async def signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        state = StateRepository(db).get_runtime_state_snapshot()
        
        if not state.signals:
            await update.message.reply_text("📭 No signals generated yet.")
            return
        
        lines = ["📡 *Recent Signals*\n"]
        for sig in state.signals[:5]:
            lines.append(
                f"• {sig.symbol} {sig.timeframe} → *{sig.signal.value}* "
                f"({sig.confidence:.1f}%) @ {sig.entry_price:.2f}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")





@require_admin
async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        state = StateRepository(db).get_runtime_state_snapshot()
        await update.message.reply_text(
            f"⚙️ *Mode*\n"
            f"Execution: `{state.execution_mode}`\n"
            f"Approval: `{state.approval_mode.value}`",
            parse_mode="Markdown",
        )


@require_admin
async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Signal-only build: no live position sync (skill parity — explicit reply)."""
    with SessionLocal() as db:
        state = StateRepository(db).get_runtime_state_snapshot()
    if state.execution_mode == "paper":
        await update.message.reply_text(
            "📭 *Positions*\n\n"
            "`paper` mode is not tracking simulated positions in this build — "
            "the bot emits signals only.",
            parse_mode="Markdown",
        )
        return
    await update.message.reply_text(
        "📭 *Positions*\n\n"
        "`signal_only` mode: no exchange positions are queried or stored.",
        parse_mode="Markdown",
    )


@require_admin
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Signal-only build: no balance sync."""
    with SessionLocal() as db:
        state = StateRepository(db).get_runtime_state_snapshot()
    if state.execution_mode == "paper":
        await update.message.reply_text(
            "💰 *Balance*\n\n"
            "`paper` mode does not maintain a synced paper wallet here — signals are advisory.",
            parse_mode="Markdown",
        )
        return
    await update.message.reply_text(
        "💰 *Balance*\n\n"
        "`signal_only` mode: no exchange balances are queried.",
        parse_mode="Markdown",
    )


@require_admin
async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        StateRepository(db).update_mode(paused=True)
    await update.message.reply_text("⏸️ Bot paused.")


@require_admin
async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        StateRepository(db).update_mode(paused=False)
    await update.message.reply_text("▶️ Bot resumed.")


@require_admin
async def why_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        outcomes = StateRepository(db).get_recent_outcomes()
        
        if not outcomes:
            await update.message.reply_text("📭 No recent signals reported.")
            return
            
        last = outcomes[0]
        msg = (
            f"🧠 *Signal Explanation*\n\n"
            f"📍 *Symbol*: {last.get('symbol')}\n"
            f"🎯 *Signal*: {last.get('signal')}\n"
            f"⚡ *Confidence*: {last.get('confidence', 0):.1f}%\n"
            f"🛡️ *Risk*: {last.get('risk_note')}\n\n"
            f"📖 *AI Explanation*:\n_{last.get('ai_explanation', 'N/A')}_"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")


@require_admin
async def insights_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        state = StateRepository(db).get_runtime_state_snapshot()
        recent = state.signals[:50]
        longs = len([s for s in recent if s.signal.value == "LONG"])
        shorts = len([s for s in recent if s.signal.value == "SHORT"])
        holds = len([s for s in recent if s.signal.value == "HOLD"])
        await update.message.reply_text(
            f"📉 *Insights* (last {len(recent)} signals)\n\n"
            f"🟢 Longs: {longs}\n"
            f"🔴 Shorts: {shorts}\n"
            f"⚪ Holds: {holds}\n",
            parse_mode="Markdown",
        )


@require_admin
async def backtest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.optimization.backtester import BacktestService
    from app.schemas.backtest import BacktestRequest
    
    # Simple parsing for args: /backtest [symbol] [days]
    symbol = "BTC/USDT"
    days = 30
    if context.args:
        symbol = context.args[0]
        if len(context.args) > 1:
            try:
                days = int(context.args[1])
            except ValueError:
                pass

    await update.message.reply_text(f"⏳ *Starting {days}-day {symbol} backtest...*", parse_mode="Markdown")
    
    try:
        service = BacktestService()
        request = BacktestRequest(symbol=symbol, timeframe="1h", days=days)
        with SessionLocal() as db:
            repo = StateRepository(db)
            result = service.run_backtest(request, repo=repo)
        
        msg = (
            f"📈 *Backtest Results ({days} Days)*\n\n"
            f"Symbol: `{result.symbol}`\n"
            f"Win Rate: `{result.win_rate:.1f}%` 🎯\n"
            f"Trades: `{result.total_trades}`\n"
            f"Sharpe: `{result.sharpe_ratio:.2f}`\n"
            f"Max Drawdown: `{result.max_drawdown_percent:.1f}%` 📉\n\n"
            f"💰 *Final Balance*: `${result.final_balance:,.2f}`"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as exc:
        logger.error("Backtest failed: %s", exc)
        await update.message.reply_text(f"❌ *Backtest failed*: {str(exc)}", parse_mode="Markdown")





@require_admin
async def rejected_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        repo = StateRepository(db)
        rejected = repo.get_rejected_signals(limit=5)
        
        if not rejected:
            await update.message.reply_text("📭 No recently filtered signals.")
            return

        lines = ["🚫 *Recently Filtered Signals*\n"]
        for s in rejected:
            lines.append(
                f"• {s['symbol']} ({s['signal']}) @ {s['timestamp'].strftime('%H:%M')}\n"
                f"  _Reason: {s['reason']}_"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@require_admin
async def optimize_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.schemas.optimizer import OptimizerRequest
    from app.services.optimizer import OptimizerEngine

    symbol = "BTC/USDT"
    await update.message.reply_text(f"🧪 *Starting Genetic Optimization for {symbol}...*\nThis will take several seconds.", parse_mode="Markdown")
    
    try:
        engine = OptimizerEngine()
        # Small population for Telegram to avoid long wait
        request = OptimizerRequest(symbol=symbol, population_size=10, generations=2)
        result = engine.run(request)
        
        params_str = "\n".join([f"• {k}: `{v}`" for k, v in result.best_params.items()])
        msg = (
            "🧬 *Optimization Complete*\n\n"
            f"Best Sharpe: `{result.best_sharpe:.2f}`\n"
            f"Best Return: `{result.best_return_pct:.1f}%` 💰\n\n"
            f"⚙️ *Optimized Parameters*:\n{params_str}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as exc:
        logger.error("Optimization failed: %s", exc)
        await update.message.reply_text(f"❌ *Optimization failed*: {str(exc)}", parse_mode="Markdown")


# --- Callback handler for approvals ---


@require_admin
async def approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle approve/reject button presses."""
    query = update.callback_query
    await query.answer()

    try:
        action, approval_id = query.data.split(":", 1)
    except ValueError:
        await query.edit_message_text("❌ Invalid callback data.")
        return

    approved = action == "approve"
    pipeline = get_pipeline()
    
    with SessionLocal() as db:
        result = pipeline.apply_approval_decision(db, approval_id, approved)

    status = result.get("result", "unknown")

    if status == "expired":
        emoji, label = "⏰", "EXPIRED"
    elif status == "approved":
        emoji, label = "✅", "APPROVED"
    elif status == "rejected":
        emoji, label = "❌", "REJECTED"
    elif status == "not_found":
        emoji, label = "❓", "NOT FOUND"
    else:
        emoji, label = "⚠️", status.upper()

    text = f"{emoji} *{label}*\nID: `{approval_id[:8]}...`"
    if result.get("execution"):
        text += f"\n{result['execution']}"

    await query.edit_message_text(text, parse_mode="Markdown")


def build_approval_keyboard(approval_id: str) -> InlineKeyboardMarkup:
    """Build inline approve/reject buttons for a signal."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve:{approval_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject:{approval_id}"),
            ]
        ]
    )
