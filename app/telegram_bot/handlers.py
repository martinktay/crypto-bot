"""Telegram command and callback handlers."""

from __future__ import annotations

import html
import logging

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.repository import StateRepository
from app.telegram_bot.middleware import is_admin, require_admin
from app.utils.agent_debug_log import agent_debug_log

logger = logging.getLogger(__name__)


# --- Public commands ---


def _admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["/status", "/signals", "/why"],
            ["/mode", "/insights", "/rejected"],
            ["/backtest", "/optimize"],
            ["/pause", "/resume"],
            ["/chatinfo", "/telegramtest"],
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
        "/chatinfo — IDs for `.env` (run in the group once)\n"
        "/telegramtest — Ping group + DM (delivery test only)\n"
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # #region agent log
    chat = update.effective_chat
    user = update.effective_user
    agent_debug_log(
        "handlers.py:start_command",
        "/start received",
        "H4",
        chat_type=chat.type if chat else None,
        admin_user_id_configured=bool(settings.telegram_admin_user_id),
        is_admin_user=bool(user and is_admin(user.id)),
    )
    # #endregion
    admin = bool(user and is_admin(user.id))
    await update.message.reply_text(
        f"🤖 *{settings.app_display_name}*\n\n"
        "I generate trading signals from configured exchanges and timeframes, with optional AI context.\n\n"
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


# Telegram text messages: ~4096 chars max (UTF-16 code units in some clients).
_TELEGRAM_MESSAGE_MAX = 4096
_TELEGRAM_SAFE_MARGIN = 64
_SYMBOL_CHUNK_CHARS = 2800


def _symbol_list_html_chunks_budgets(
    symbols: list[str],
    *,
    first_max: int,
    rest_max: int,
) -> list[str]:
    """Split symbols into comma-separated HTML-escaped chunks with per-chunk limits."""
    if not symbols:
        return []
    chunks: list[str] = []
    bucket: list[str] = []
    running = 0
    chunk_limit = first_max
    for s in symbols:
        piece = html.escape(s)
        sep_len = 2 if bucket else 0
        if bucket and running + sep_len + len(piece) > chunk_limit:
            chunks.append(html.escape(", ".join(bucket)))
            bucket = [s]
            running = len(html.escape(s))
            chunk_limit = rest_max
        else:
            bucket.append(s)
            running += sep_len + len(piece)
    if bucket:
        chunks.append(html.escape(", ".join(bucket)))
    return chunks


def _symbol_list_html_chunks(
    symbols: list[str], *, max_chars: int = _SYMBOL_CHUNK_CHARS
) -> list[str]:
    return _symbol_list_html_chunks_budgets(
        symbols, first_max=max_chars, rest_max=max_chars
    )


# --- Admin commands ---


@require_admin
async def chatinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show effective chat id/type so admins can fill TELEGRAM_GROUP_CHAT_ID (or admin DM id)."""
    chat = update.effective_chat
    if not chat:
        return
    type_s = html.escape(str(chat.type))
    id_s = html.escape(str(chat.id))
    title = getattr(chat, "title", None) or getattr(chat, "full_name", None)
    username = getattr(chat, "username", None)
    parts = [
        "📎 <b>Chat info</b> (paste into <code>.env</code> as needed)",
        "",
        f"chat.type — <code>{type_s}</code>",
        f"chat.id — <code>{id_s}</code>",
    ]
    if title:
        parts.append("")
        parts.append(f"Title — <b>{html.escape(str(title))}</b>")
    if username:
        parts.append(f"@{html.escape(username)}")
    bot_uname_raw = getattr(context.bot, "username", None) or ""
    bot_uname_esc = html.escape(bot_uname_raw) if bot_uname_raw else "your_bot_username"
    hint = ""
    if chat.type in ("group", "supergroup"):
        hint = (
            "\nPut this in <code>.env</code> as <code>TELEGRAM_GROUP_CHAT_ID=" + id_s + "</code> "
            "(no spaces, keep the <code>-</code>). Restart the API process so settings reload.\n"
            "If you still only get signals in your DM, open <code>.env</code> and confirm the group line "
            "is exactly this id — not your private DM id (typically a shorter positive number).\n"
            "If Telegram enabled &quot;Topics&quot; / forum mode for this group, also set "
            "<code>TELEGRAM_GROUP_MESSAGE_THREAD_ID=1</code> (often &quot;General&quot;) or the "
            "thread id Telegram shows when you deep-link an existing topic.\n"
            "Check server logs for <code>Telegram send failed</code> (wrong id, bot removed, missing thread id, "
            "or no permission to send messages)."
        )
    elif chat.type == "private":
        hint = (
            "\n<b>Your DM with the bot:</b> use <code>TELEGRAM_ADMIN_CHAT_ID=" + id_s + "</code> "
            "(this is <i>not</i> where group signals are configured).\n\n"
            "<b>To get the group id for signal cards:</b>\n"
            "1) In Telegram, open the <b>group chat</b> (header shows the group name; you are not in this private bot chat).\n"
            "2) Send <code>/chatinfo</code> in that group. If nothing happens, send "
            f"<code>/chatinfo@{bot_uname_esc}</code>.\n"
            "3) You should see <code>chat.type — group</code> or <code>supergroup</code> and "
            "<code>chat.id — -100…</code> (supergroups/channels-as-target often start with <code>-100</code>).\n"
            "4) Copy <i>that</i> id into <code>TELEGRAM_GROUP_CHAT_ID</code> in <code>.env</code>, save, "
            "restart the app (Docker or <code>uvicorn</code>).\n\n"
            "<i>If you see Unauthorized in the group, <code>TELEGRAM_ADMIN_USER_ID</code> in <code>.env</code> "
            "does not match the numeric id of the account sending /chatinfo.</i>"
        )
    parts.append(hint)
    if bot_uname_raw and chat.type not in ("private",):
        parts.append(
            "\n<i>If your client ignores slash commands in this group, use "
            f"<code>/chatinfo@{html.escape(bot_uname_raw)}</code>.</i>"
        )
    await update.message.reply_text("\n".join(parts), parse_mode="HTML")


@require_admin
async def telegramtest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a non-trading ping to TELEGRAM_GROUP_CHAT_ID then admin DM."""
    from app.telegram_bot.service import TelegramNotifier

    notifier = TelegramNotifier()
    pings = notifier.ping_destinations()
    if not notifier.enabled:
        await update.message.reply_text(
            "⚠️ Telegram notifier disabled. Set TELEGRAM_BOT_TOKEN and "
            "TELEGRAM_GROUP_CHAT_ID and/or TELEGRAM_ADMIN_CHAT_ID, restart the API."
        )
        return
    if not pings:
        await update.message.reply_text(
            "⚠️ No broadcast chat ids configured."
        )
        return
    lines = ["📡 Telegram delivery test sent:"]
    for row in pings:
        tick = "✅" if row.get("ok") else "❌"
        lines.append(f"{tick} chat {row.get('chat', '?')}")
    await update.message.reply_text("\n".join(lines))


@require_admin
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        with SessionLocal() as db:
            repo = StateRepository(db)
            state = repo.get_runtime_state_snapshot()
            lessons = repo.count_knowledge_documents()
    except Exception:
        logger.exception("status_command: database error")
        await update.message.reply_text(
            "⚠️ Could not load status (database unreachable). "
            "Check DATABASE_URL / network, restart the bot, and try again."
        )
        return

    n = len(state.symbols)
    tf = html.escape(", ".join(state.timeframes))
    strat = html.escape(state.strategy)
    batch = settings.scan_symbols_batch_size
    batch_note = (
        f"Scan batch: <b>{batch}</b> symbols/tick (round-robin)"
        if batch > 0
        else "Scan batch: <b>all</b> symbols/tick"
    )
    footer = (
        f"Timeframes: {tf}\n\n"
        "Alerts: only <b>LONG</b> or <b>SHORT</b> that pass risk checks are posted. "
        "<b>HOLD</b> bars are silent (no trade this bar)."
    )
    header_top = (
        "📊 <b>Bot Status</b>\n\n"
        f"Paused: {'⏸️ Yes' if state.paused else '▶️ No'}\n"
        f"Strategy: {strat}\n"
        f"Lessons learned: {lessons} 🧠\n"
        f"{batch_note}\n"
    )
    # First message = header + symbol intro + chunk + footer; reserve using worst-case intro length.
    worst_sym_intro = f"Symbols ({n}), part 1/999:\n"
    budget_first = (
        _TELEGRAM_MESSAGE_MAX
        - _TELEGRAM_SAFE_MARGIN
        - len(header_top)
        - len(worst_sym_intro)
        - len(footer)
    )
    budget_first = max(400, min(2_600, budget_first))
    follow_prefix = f"📊 <b>Symbols</b> ({n}) part 99/99\n"
    budget_follow = _TELEGRAM_MESSAGE_MAX - _TELEGRAM_SAFE_MARGIN - len(follow_prefix)
    budget_follow = max(400, min(3_800, budget_follow))

    sym_chunks = _symbol_list_html_chunks_budgets(
        state.symbols,
        first_max=budget_first,
        rest_max=budget_follow,
    )
    sym_intro = (
        f"Symbols ({n}), part 1/{len(sym_chunks)}:\n"
        if len(sym_chunks) > 1
        else f"Symbols ({n}):\n"
    )
    body0 = sym_chunks[0] if sym_chunks else html.escape("(none)")
    text = f"{header_top}{sym_intro}{body0}\n{footer}"
    await update.message.reply_text(text, parse_mode="HTML")
    for i, chunk in enumerate(sym_chunks[1:], start=2):
        part = f"📊 <b>Symbols</b> ({n}) part {i}/{len(sym_chunks)}\n{chunk}"
        await update.message.reply_text(part, parse_mode="HTML")


def _level_str(value: float) -> str:
    """Trim trailing zeros so 80347.620 -> 80347.62, 80300.00 -> 80300."""
    return f"{float(value):.2f}".rstrip("0").rstrip(".")


@require_admin
async def signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        with SessionLocal() as db:
            state = StateRepository(db).get_runtime_state_snapshot()
    except Exception:
        logger.exception("signals_command: database error")
        await update.message.reply_text(
            "⚠️ Could not load signals (database unreachable). "
            "Check DATABASE_URL / network and restart the bot."
        )
        return

    # HOLD is the explicit "no trade this bar" state in this build — it's
    # never broadcast and shouldn't appear in /signals either, otherwise
    # the list is mostly noise (every closed bar that didn't cross).
    actionable = [s for s in state.signals if s.signal.value in ("LONG", "SHORT")][:5]

    if not actionable:
        await update.message.reply_text("📭 No actionable signals yet.")
        return

    # HTML: avoid legacy Markdown breaking on symbols like BTC/USDT:USDT or em dashes.
    blocks = ["📡 <b>Recent Signals</b>"]
    for sig in actionable:
        ex = html.escape((sig.exchange_id or "").title())
        exchange_tag = f" ({ex})" if sig.exchange_id else ""
        dir_s = html.escape(sig.signal.value)
        sym_s = html.escape(sig.symbol)
        tf_s = html.escape(sig.timeframe)
        audit_html = (
            f"\nEMA audit: {sig.confidence_audit_ema_bps:.1f}%"
            if sig.confidence_audit_ema_bps is not None
            else ""
        )
        blocks.append(
            f"\n<b>{dir_s}</b> — {sym_s} {tf_s}{exchange_tag}\n"
            f"Confidence: {sig.confidence:.1f}%{audit_html}\n"
            f"Entry: {_level_str(sig.entry_price)}\n"
            f"TP/SL: {_level_str(sig.take_profit)} / {_level_str(sig.stop_loss)}"
        )
    await update.message.reply_text("\n".join(blocks), parse_mode="HTML")





@require_admin
async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with SessionLocal() as db:
        state = StateRepository(db).get_runtime_state_snapshot()
        await update.message.reply_text(
            f"⚙️ *Mode*\n"
            f"Execution: `{state.execution_mode}`",
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
        audit_txt = ""
        if last.get("confidence_audit_ema_bps") is not None:
            audit_txt = f"\n⚡ *EMA audit*: {last['confidence_audit_ema_bps']:.1f}%"
        msg = (
            f"🧠 *Signal Explanation*\n\n"
            f"📍 *Symbol*: {last.get('symbol')}\n"
            f"🎯 *Signal*: {last.get('signal')}\n"
            f"⚡ *Confidence*: {last.get('quality_score', last.get('confidence', 0)):.1f}%{audit_txt}\n"
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
