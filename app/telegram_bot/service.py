"""Telegram notification service — sync HTTP sending via httpx."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import settings
from app.schemas.signal import SignalContract

logger = logging.getLogger(__name__)

_TELEGRAM_MAX_MESSAGE_LEN = 3800  # leave room for markup/edits; Telegram hard limit is 4096


def _truncate(text: str, max_len: int = _TELEGRAM_MAX_MESSAGE_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 1)] + "…"


def _md_escape(text: str) -> str:
    """
    Escape Telegram Markdown (legacy) special characters in user/LLM-provided text.

    We keep using parse_mode="Markdown" for compatibility with current formatting.
    """
    # Telegram's legacy Markdown is quirky; this conservative escape prevents most breakage.
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


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

    def send_message(self, text: str, chat_id: str | None = None, reply_markup: dict | None = None) -> None:
        """Send a message to a specific chat (defaults to admin)."""
        target_id = chat_id or self.admin_chat_id
        if not self.enabled or not target_id:
            return
        payload: dict[str, Any] = {
            "chat_id": target_id,
            "text": _truncate(text),
            "parse_mode": "Markdown",
        }
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
        approval_id: str | None = kwargs.get("approval_id")

        if event_type == "approval_needed" and signal and approval_id:
            # Send to ADMIN only
            text = self.build_signal_message(signal, outcome)
            text += f"\n\n⏳ *ADMIN REVIEW REQUIRED* (`{approval_id[:8]}...`)"
            markup = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Approve & Broadcast", "callback_data": f"approve:{approval_id}"},
                        {"text": "❌ Reject", "callback_data": f"reject:{approval_id}"},
                    ]
                ]
            }
            self.send_message(text, chat_id=self.admin_chat_id, reply_markup=markup)

        elif event_type == "signal" and signal and outcome:
            # Send to GROUP for broadcast
            text = self.build_signal_message(signal, outcome)
            self.send_message(text, chat_id=self.group_chat_id)

        elif event_type == "rejection" and signal and outcome:
            # Send to ADMIN for feedback
            text = self.build_rejection_message(signal, outcome)
            self.send_message(text, chat_id=self.admin_chat_id)

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
            self.send_message(text)

    def build_signal_message(self, signal: SignalContract, outcome: dict | None = None) -> str:
        """Build a professional, data-dense signal message for Telegram."""
        dir_emoji = (
            "🟢"
            if signal.signal.value == "LONG"
            else "🔴"
            if signal.signal.value == "SHORT"
            else "⚪"
        )
        status_line = (outcome or {}).get("signal_status") or "Processed"

        # Compute RR if prices are sensible
        rr: float | None = None
        per_unit_risk = abs(signal.entry_price - signal.stop_loss)
        per_unit_reward = abs(signal.take_profit - signal.entry_price)
        if per_unit_risk > 0:
            rr = per_unit_reward / per_unit_risk

        # Escape free-text to avoid Markdown breakage / spoofing.
        reason = _md_escape(signal.reason or "")
        explanation = _md_escape(signal.ai_explanation or "")
        if len(explanation) > 900:
            explanation = _truncate(explanation, 900)

        ts = signal.timestamp.isoformat(timespec="seconds")
        atr_line = (
            f"\n• ATR: `{signal.atr_value:,.2f}`"
            if signal.atr_value is not None
            else ""
        )
        rr_line = f"\n• RR: `{rr:.2f}`" if rr is not None else ""

        msg = (
            f"💎 *TRADE SIGNAL*  `{signal.symbol}`\n"
            f"Timeframe: `{signal.timeframe}`  |  Type: `{signal.order_type}`\n"
            f"Timestamp: `{ts}`\n"
            "\n"
            f"*Direction*: `{signal.signal.value}` {dir_emoji}\n"
            f"*Confidence*: `{signal.confidence:.1f}%`\n"
            "\n"
            "*Levels*\n"
            f"• Entry: `{signal.entry_price:,.2f}`\n"
            f"• Take Profit: `{signal.take_profit:,.2f}`\n"
            f"• Stop Loss: `{signal.stop_loss:,.2f}`"
            f"{rr_line}"
            f"{atr_line}\n"
            "\n"
            f"*Setup*\n_{reason}_\n"
            "\n"
            f"*AI rationale (advisory)*\n_{explanation}_\n"
            "\n"
            f"*Status*: { _md_escape(str(status_line)) }"
        )

        return _truncate(msg)

    def build_rejection_message(self, signal: SignalContract, outcome: dict) -> str:
        risk_note = _md_escape(str(outcome.get("risk_note", "N/A")))
        limits_note = _md_escape(str(outcome.get("limits_note", "N/A")))
        return _truncate(
            "⚠️ *SIGNAL REJECTED*\n"
            f"Pair: `{signal.symbol}`\n"
            f"Timeframe: `{signal.timeframe}`\n"
            f"Signal: `{signal.signal.value}`\n"
            f"Reason: _{_md_escape(signal.reason or '')}_\n"
            "\n"
            f"Risk: _{risk_note}_\n"
            f"Limits: _{limits_note}_"
        )
