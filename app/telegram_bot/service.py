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

        if event_type == "signal" and signal and outcome:
            text = self.build_signal_message(signal, outcome)
            self.send_message(text, chat_id=self.group_chat_id)

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

    def build_signal_message(self, signal: SignalContract, outcome: dict | None = None) -> str:
        """Build the broadcast signal card (plain text — matches product template)."""
        _ = outcome  # retained for API compatibility with callers / tests
        explanation = (signal.ai_explanation or signal.reason or "").strip()
        if len(explanation) > 2800:
            explanation = _truncate(explanation, 2800)

        def _level_str(value: float) -> str:
            return f"{float(value):.2f}".rstrip("0").rstrip(".")

        entry_s = _level_str(signal.entry_price)
        tp_s = _level_str(signal.take_profit)
        sl_s = _level_str(signal.stop_loss)

        msg = (
            "🚨 NEW SIGNAL\n"
            f"Result: {signal.signal.value} for {signal.symbol}\n"
            f"Confidence: {signal.confidence:.1f}%\n"
            "\n"
            "🧠 AI INSIGHT\n"
            f"{explanation}\n"
            "\n"
            f"Entry: {entry_s}\n"
            f"TP/SL: {tp_s} / {sl_s}"
        )
        return _truncate(msg)
