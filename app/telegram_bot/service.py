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

_TELEGRAM_MAX_MESSAGE_LEN = 4090  # under Telegram's 4096 ceiling (UTF-16 quirks)


def _truncate(text: str, max_len: int = _TELEGRAM_MAX_MESSAGE_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 1)] + "…"


def _html_italic_chunks(plain: str, max_len: int = _TELEGRAM_MAX_MESSAGE_LEN) -> list[str]:
    """Split long explanation text into Telegram-sized HTML italic segments."""
    t = plain.strip()
    if not t:
        return []
    overhead = len("<i></i>")
    budget = max(256, max_len - overhead)
    out: list[str] = []
    for i in range(0, len(t), budget):
        piece = t[i : i + budget]
        out.append(f"<i>{html.escape(piece)}</i>")
    return out


def _redact_chat_id(chat_id: str) -> str:
    """Avoid dumping full chat IDs into logs while keeping support correlation."""
    s = str(chat_id).strip()
    if len(s) <= 4:
        return "(short id)"
    return f"…{s[-4:]}"


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
                detail = resp.text[:500]
                try:
                    body = resp.json()
                    if isinstance(body, dict) and body.get("description"):
                        detail = str(body["description"])
                except (ValueError, TypeError, AttributeError):
                    pass
                logger.warning(
                    "Telegram send failed to %s (status=%s): %s",
                    _redact_chat_id(str(target_id)),
                    resp.status_code,
                    detail,
                )
            else:
                logger.debug(
                    "Telegram message sent OK (chat %s)",
                    _redact_chat_id(str(target_id)),
                )
        except Exception as exc:
            from app.monitoring.metrics import notifications_failed

            notifications_failed.labels(kind="telegram").inc()
            logger.error(
                "Telegram send error to %s: %s",
                _redact_chat_id(str(target_id)),
                exc.__class__.__name__,
            )

    def notify(self, event_type: str, **kwargs: Any) -> None:
        """Notification callback for SignalPipeline."""
        signal: SignalContract | None = kwargs.get("signal")
        outcome: dict | None = kwargs.get("outcome")
        signal_id: int | None = kwargs.get("signal_id")

        if event_type == "signal" and signal and outcome:
            chunks = self.build_signal_message_chunks(
                signal, outcome, signal_id=signal_id
            )
            target_chat = (self.group_chat_id or self.admin_chat_id).strip()
            if not target_chat:
                logger.warning(
                    "Telegram signal broadcast skipped: set TELEGRAM_GROUP_CHAT_ID and/or "
                    "TELEGRAM_CHAT_ID (admin / TELEGRAM_ADMIN_CHAT_ID) so the bot knows where to post."
                )
                return
            for part in chunks:
                self.send_message(part, chat_id=target_chat, parse_mode="HTML")
            logger.info(
                "Signal broadcast dispatched (%s %s → chat %s, parts=%d)",
                (signal.symbol or "").upper(),
                signal.signal.value,
                _redact_chat_id(target_chat),
                len(chunks),
            )

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

    def build_signal_message_chunks(
        self,
        signal: SignalContract,
        outcome: dict | None = None,
        *,
        signal_id: int | None = None,
    ) -> list[str]:
        """Build one or more HTML messages for a signal broadcast.

        When the card plus explanation exceeds Telegram's size limit, the
        first message carries header + entry/levels; following messages
        carry the explanation (split again if needed).
        """
        _ = outcome  # retained for API compatibility with callers / tests

        explanation = (signal.ai_explanation or signal.reason or "").strip()
        # Soft cap so a single-message layout stays likely; hard splitting
        # below still protects Telegram's API if the model returns a novel.
        if len(explanation) > 12000:
            explanation = _truncate(explanation, 12000)

        def _level_str(value: float) -> str:
            return f"{float(value):.2f}".rstrip("0").rstrip(".")

        entry_s = _level_str(signal.entry_price)
        tp_s = _level_str(signal.take_profit)
        sl_s = _level_str(signal.stop_loss)

        symbol_safe = html.escape(signal.symbol)
        direction = signal.signal.value
        direction_safe = html.escape(direction)
        # Title-case for visual parity with how exchanges brand themselves
        exchange_safe = html.escape((signal.exchange_id or "").title())

        callsign = _signal_callsign(signal, signal_id)
        emoji = _direction_emoji(signal.signal)

        meta_parts: list[str] = []
        if exchange_safe:
            meta_parts.append(exchange_safe)
        meta_parts.append(html.escape(signal.timeframe))
        meta_parts.append(f"Confidence {signal.confidence:.1f}%")
        meta_line = " • ".join(meta_parts)

        header = (
            f"{emoji} <b>{direction_safe} {callsign}</b> — {symbol_safe}\n"
            f"{meta_line}\n"
        )
        data_rows = f"Entry: {entry_s}\nTP/SL: {tp_s} / {sl_s}"
        compact = f"{header}\n{data_rows}"

        if not explanation:
            return [_truncate(compact)]

        explanation_safe = html.escape(explanation)
        explanation_block = f"<i>{explanation_safe}</i>\n\n"
        single = f"{header}\n{explanation_block}{data_rows}"
        if len(single) <= _TELEGRAM_MAX_MESSAGE_LEN:
            return [_truncate(single)]

        chunks: list[str] = [_truncate(compact)]
        chunks.extend(_html_italic_chunks(explanation))
        return chunks

    def build_signal_message(
        self,
        signal: SignalContract,
        outcome: dict | None = None,
        *,
        signal_id: int | None = None,
    ) -> str:
        """Build the broadcast signal card (all parts joined for tests / logging).

        See ``build_signal_message_chunks`` for multi-message behaviour.
        """
        return "\n".join(
            self.build_signal_message_chunks(
                signal, outcome, signal_id=signal_id
            )
        )


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
