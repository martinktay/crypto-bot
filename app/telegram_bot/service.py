"""Telegram notification service — sync HTTP sending via httpx."""

from __future__ import annotations

import hashlib
import html
import json
import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.enums import SignalDirection
from app.schemas.signal import SignalContract

logger = logging.getLogger(__name__)

_TELEGRAM_MAX_MESSAGE_LEN = 3800  # leave room for markup/edits; Telegram hard limit is 4096


def _truncate(text: str, max_len: int = _TELEGRAM_MAX_MESSAGE_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 1)] + "…"


class TelegramNotifier:
    """Sends Telegram messages synchronously using the Bot HTTP API.

    This is used by the scheduler (sync context). The python-telegram-bot
    Application handles incoming updates separately.
    """

    def __init__(self) -> None:
        self.token = settings.telegram_bot_token
        self.admin_chat_id = settings.telegram_admin_chat_id
        self.group_chat_id = settings.telegram_group_chat_id
        self.enabled = bool(self.token and (self.admin_chat_id or self.group_chat_id))
        if self.enabled:
            self.url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_message(
        self,
        text: str,
        chat_id: str | None = None,
        reply_markup: dict | None = None,
        *,
        parse_mode: str | None = None,
    ) -> None:
        """Send a message to a specific chat (defaults to admin)."""
        target_id = chat_id or self.admin_chat_id
        if not self.enabled or not target_id:
            return
        payload: dict[str, Any] = {
            "chat_id": target_id,
            "text": _truncate(text),
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        try:
            resp = httpx.post(self.url, json=payload, timeout=10)
            if resp.status_code != 200:
                from app.monitoring.metrics import notifications_failed

                notifications_failed.labels(kind="telegram").inc()
                logger.warning(
                    "Telegram send failed to %s (status=%s)",
                    target_id,
                    resp.status_code,
                )
        except Exception as exc:
            from app.monitoring.metrics import notifications_failed

            notifications_failed.labels(kind="telegram").inc()
            logger.error("Telegram send error: %s", exc.__class__.__name__)

    def notify(self, event_type: str, **kwargs: Any) -> None:
        """Notification callback for SignalPipeline."""
        signal: SignalContract | None = kwargs.get("signal")
        outcome: dict | None = kwargs.get("outcome")
        signal_id: int | None = kwargs.get("signal_id")

        if event_type == "signal" and signal and outcome:
            text = self.build_signal_message(signal, outcome, signal_id=signal_id)
            self.send_message(text, chat_id=self.group_chat_id, parse_mode="HTML")

        elif event_type == "signal_insight":
            symbol = kwargs.get("symbol", "Unknown")
            reason = kwargs.get("reason", "Unknown")
            roi_pct = kwargs.get("roi_percent", 0.0)
            duration = kwargs.get("duration_seconds", 0.0)

            emoji = "🟢" if roi_pct > 0 else "🔴"
            target = "Target Hit 🎯" if reason == "TAKE_PROFIT" else "Stop Triggered 🛡️"
            
            text = (
                f"*🎯 SIGNAL INSIGHT* {emoji}\n"
                f"Pair: `{symbol}`\n"
                f"Result: {target}\n"
                f"Virtual ROI: `{roi_pct:.2f}%`"
                f"\nDuration: `{int(duration // 60)} mins`"
            )
            self.send_message(text, parse_mode="Markdown")

    def build_signal_message(
        self,
        signal: SignalContract,
        outcome: dict | None = None,
        *,
        signal_id: int | None = None,
    ) -> str:
        """Build the broadcast signal card.

        Each card opens with a unique, glance-able callsign so messages
        are trivially distinguishable in a busy group chat — the format is
        ``<emoji> <DIRECTION> #<id> — <SYMBOL>``, e.g.
        ``🟢 LONG #0042 — BTC/USDT``. The id is the auto-incrementing DB
        primary key when available, or a deterministic 4-char content
        hash when the message is built outside the pipeline (e.g. unit
        tests). The explanation body is rendered as italic prose with no
        section header — keeping it visually distinct from the data
        fields without flagging it as machine-generated.

        Rendered with Telegram's HTML parse mode (chosen over Markdown
        because the explanation can contain raw ``*``/``_``/`` ` ``
        characters that would otherwise corrupt or be rejected).
        """
        _ = outcome  # retained for API compatibility with callers / tests

        explanation = (signal.ai_explanation or signal.reason or "").strip()
        if len(explanation) > 2800:
            explanation = _truncate(explanation, 2800)

        def _level_str(value: float) -> str:
            return f"{float(value):.2f}".rstrip("0").rstrip(".")

        entry_s = _level_str(signal.entry_price)
        tp_s = _level_str(signal.take_profit)
        sl_s = _level_str(signal.stop_loss)

        # html.escape neutralises &, <, > inside untrusted strings (the
        # explanation, symbol, and direction enum value) so a stray '<'
        # in the model output can't open a fake tag and trip Telegram's
        # parser into rejecting the whole message with HTTP 400.
        symbol_safe = html.escape(signal.symbol)
        direction = signal.signal.value
        direction_safe = html.escape(direction)
        explanation_safe = html.escape(explanation)
        # Title-case for visual parity with how exchanges brand themselves
        # ("Binance", "Bybit", "Mexc" rather than the lowercase ccxt id).
        exchange_safe = html.escape((signal.exchange_id or "").title())

        callsign = _signal_callsign(signal, signal_id)
        emoji = _direction_emoji(signal.signal)

        # Compact meta line under the callsign. Only include components
        # that have a meaningful value, separated by middle dots.
        meta_parts: list[str] = []
        if exchange_safe:
            meta_parts.append(exchange_safe)
        meta_parts.append(html.escape(signal.timeframe))
        meta_parts.append(f"Confidence {signal.confidence:.1f}%")
        meta_line = " • ".join(meta_parts)

        explanation_block = (
            f"<i>{explanation_safe}</i>\n\n" if explanation_safe else ""
        )

        msg = (
            f"{emoji} <b>{direction_safe} {callsign}</b> — {symbol_safe}\n"
            f"{meta_line}\n"
            "\n"
            f"{explanation_block}"
            f"Entry: {entry_s}\n"
            f"TP/SL: {tp_s} / {sl_s}"
        )
        return _truncate(msg)


def _direction_emoji(direction: SignalDirection) -> str:
    """Map signal direction to a glanceable colour cue in the title."""
    if direction == SignalDirection.LONG:
        return "🟢"
    if direction == SignalDirection.SHORT:
        return "🔴"
    return "🟡"


def _signal_callsign(signal: SignalContract, signal_id: int | None) -> str:
    """Short, unique-per-signal token rendered in the title.

    With a DB-assigned id the format is ``#0042`` (zero-padded to 4
    digits, then naturally widening) so signals can be referenced by
    name in the chat — "look at #0042". Without an id (tests, ad-hoc
    calls) we hash the signal's identifying fields into a 4-char base16
    code so the same fixture always renders the same callsign and two
    distinct signals never collide visually in chat.
    """
    if signal_id is not None and signal_id > 0:
        return f"#{signal_id:04d}"
    payload = "|".join(
        [
            signal.symbol or "",
            signal.timeframe or "",
            signal.signal.value,
            f"{signal.entry_price:.8f}",
            signal.timestamp.isoformat() if signal.timestamp else "",
        ]
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:4].upper()
    return f"#{digest}"
