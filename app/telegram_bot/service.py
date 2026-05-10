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


def _telegram_api_chat_id(raw: str) -> int | str:
    """Telegram accepts int chat ids for numeric supergroups; normalize JSON payload."""
    s = (raw or "").strip()
    if s.startswith("@"):
        return s
    if s.startswith("+"):
        tail = s[1:]
        return int(tail) if tail.lstrip("-").isdigit() else s
    if s.lstrip("-").isdigit():
        return int(s)
    return s


class TelegramNotifier:
    """Sends Telegram messages synchronously using the Bot HTTP API.

    This is used by the scheduler (sync context). The python-telegram-bot
    Application handles incoming updates separately.
    """

    def __init__(self) -> None:
        self.token = settings.telegram_bot_token
        self.admin_chat_id = settings.telegram_admin_chat_id
        self.group_chat_id = settings.telegram_group_chat_id
        self.group_message_thread_id = settings.telegram_group_message_thread_id
        self.enabled = bool(self.token and (self.admin_chat_id or self.group_chat_id))
        if self.enabled:
            self.url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def _default_outbound_chat_id(self) -> str | None:
        """Prefer admin DM for ad-hoc sends; fall back to group if only the group is set."""
        a = self.admin_chat_id.strip()
        if a:
            return a
        g = self.group_chat_id.strip()
        return g or None

    def _signal_broadcast_chat_ids(self) -> list[str]:
        """Signal cards go here: group first (if set), then admin DM, deduped."""
        seen: set[str] = set()
        out: list[str] = []
        for raw in (self.group_chat_id, self.admin_chat_id):
            cid = raw.strip()
            if cid and cid not in seen:
                seen.add(cid)
                out.append(cid)
        return out

    def log_signal_broadcast_plan(self) -> None:
        """One startup line: where risk-passing signals are posted (ids redacted)."""
        if not self.enabled:
            logger.info(
                "Telegram outbound: disabled (set TELEGRAM_BOT_TOKEN and at least one of "
                "TELEGRAM_GROUP_CHAT_ID / TELEGRAM_ADMIN_CHAT_ID)"
            )
            return
        order: list[str] = []
        if self.group_chat_id.strip():
            order.append(f"group={_redact_chat_id(self.group_chat_id)}")
        if self.admin_chat_id.strip():
            order.append(f"admin_dm={_redact_chat_id(self.admin_chat_id)}")
        if not order:
            logger.warning(
                "Telegram token set but no chat IDs — signal broadcast has nowhere to go"
            )
            return
        logger.info(
            "Telegram signal broadcast order (LONG/SHORT after risk): %s",
            " then ".join(order),
        )
        if self.group_message_thread_id is not None and self.group_chat_id.strip():
            logger.info(
                "Telegram group posts use message_thread_id=%s (Topics/forum mode)",
                self.group_message_thread_id,
            )

    def ping_destinations(self) -> list[dict[str, object]]:
        """Post a benign HTML ping to each signal-broadcast chat (verify routing)."""
        if not self.enabled or not self._signal_broadcast_chat_ids():
            return []
        name = html.escape((settings.app_display_name or "Signal bot").strip())
        msg = (
            f"<b>{name}</b> — <b>Telegram delivery test</b>\n"
            "<i>Not a trade signal — only checks that outbound messages reach this chat.</i>"
        )
        out: list[dict[str, object]] = []
        for cid in self._signal_broadcast_chat_ids():
            ok = self.send_message(msg, chat_id=cid, parse_mode="HTML")
            out.append({"chat": _redact_chat_id(cid), "ok": ok})
        return out

    def send_message(
        self,
        text: str,
        chat_id: str | None = None,
        reply_markup: dict | None = None,
        *,
        parse_mode: str | None = None,
    ) -> bool:
        """Send a message. Returns ``True`` only when Telegram returns HTTP 200."""
        target_raw = chat_id or self._default_outbound_chat_id()
        if not self.enabled or not target_raw:
            return False
        api_chat_id = _telegram_api_chat_id(str(target_raw))
        payload: dict[str, Any] = {
            "chat_id": api_chat_id,
            "text": _truncate(text),
        }
        if (
            self.group_message_thread_id is not None
            and self.group_chat_id.strip()
            and str(target_raw).strip() == self.group_chat_id.strip()
        ):
            payload["message_thread_id"] = self.group_message_thread_id
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
                    _redact_chat_id(str(target_raw)),
                    resp.status_code,
                    detail,
                )
                return False
            logger.debug(
                "Telegram message sent OK (chat %s)",
                _redact_chat_id(str(target_raw)),
            )
            return True
        except Exception as exc:
            from app.monitoring.metrics import notifications_failed

            notifications_failed.labels(kind="telegram").inc()
            logger.error(
                "Telegram send error to %s: %s",
                _redact_chat_id(str(target_raw)),
                exc.__class__.__name__,
            )
            return False

    def notify(self, event_type: str, **kwargs: Any) -> None:
        """Notification callback for SignalPipeline."""
        signal: SignalContract | None = kwargs.get("signal")
        outcome: dict | None = kwargs.get("outcome")
        signal_id: int | None = kwargs.get("signal_id")

        if event_type == "signal" and signal and outcome:
            chunks = self.build_signal_message_chunks(
                signal, outcome, signal_id=signal_id
            )
            destinations = self._signal_broadcast_chat_ids()
            if not destinations:
                logger.warning(
                    "Telegram signal broadcast skipped: set TELEGRAM_GROUP_CHAT_ID and/or "
                    "TELEGRAM_CHAT_ID (admin / TELEGRAM_ADMIN_CHAT_ID) so the bot knows where to post."
                )
                return
            for target_chat in destinations:
                dest_ok = True
                for part in chunks:
                    if not self.send_message(
                        part, chat_id=target_chat, parse_mode="HTML"
                    ):
                        dest_ok = False
                if dest_ok:
                    logger.info(
                        "Telegram signal broadcast delivered (%s %s → chat %s, parts=%d)",
                        (signal.symbol or "").upper(),
                        signal.signal.value,
                        _redact_chat_id(target_chat),
                        len(chunks),
                    )
                else:
                    logger.warning(
                        "Telegram signal broadcast incomplete for chat %s (%s %s, parts=%d). "
                        "Check logs above; Topics/forum groups often need TELEGRAM_GROUP_MESSAGE_THREAD_ID "
                        "(try 1 for General).",
                        _redact_chat_id(target_chat),
                        (signal.symbol or "").upper(),
                        signal.signal.value,
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
            for target_chat in self._signal_broadcast_chat_ids():
                self.send_message(text, chat_id=target_chat, parse_mode="Markdown")

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
        # Same numeric value as ``quality_score``; users expect the word "Confidence".
        meta_parts.append(f"Confidence {signal.confidence:.1f}%")
        if signal.confidence_audit_ema_bps is not None:
            meta_parts.append(f"EMA audit {signal.confidence_audit_ema_bps:.1f}%")
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
