"""Tests for Telegram notification message formatting and dispatch."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.core.enums import SignalDirection
from app.schemas.signal import SignalContract
from app.telegram_bot.service import TelegramNotifier


def _signal() -> SignalContract:
    return SignalContract(
        symbol="BTC/USDT",
        timeframe="15m",
        signal=SignalDirection.LONG,
        entry_price=60000.0,
        stop_loss=58000.0,
        take_profit=64000.0,
        confidence=85.0,
        reason="EMA crossover bullish",
        timestamp=datetime.now(timezone.utc),
    )


class TestMessageFormatting:
    def test_signal_message_contains_required_fields(self) -> None:
        """Card uses the unique-callsign header and never announces 'AI'."""
        notifier = TelegramNotifier()
        msg = notifier.build_signal_message(
            _signal(),
            {"signal_status": "Signal Recorded 📝"},
            signal_id=42,
        )
        # New header format: emoji DIRECTION #id — SYMBOL
        assert "🟢" in msg
        assert "<b>LONG #0042</b>" in msg
        assert "BTC/USDT" in msg
        # AI labels removed.
        assert "AI INSIGHT" not in msg
        assert "NEW SIGNAL" not in msg
        # Body and data rows still rendered.
        assert "EMA crossover bullish" in msg
        assert "Confidence 85.0%" in msg
        assert "15m" in msg
        assert "Entry:" in msg
        assert "TP/SL:" in msg
        assert "64000 / 58000" in msg

    def test_signal_message_callsign_falls_back_to_content_hash(self) -> None:
        """Without a DB id, the callsign is a 4-char content hash so two
        distinct signals still render as visually distinct messages."""
        notifier = TelegramNotifier()
        msg = notifier.build_signal_message(_signal())
        import re

        match = re.search(r"<b>LONG #([0-9A-F]{4})</b>", msg)
        assert match, f"expected hash callsign, got: {msg!r}"

    def test_rejection_notify_does_not_send_telegram(self) -> None:
        """Risk rejections are not pushed to Telegram (signal-only product)."""
        notifier = TelegramNotifier()
        notifier.enabled = True
        notifier.send_message = MagicMock()

        notifier.notify(
            "rejection",
            signal=_signal(),
            outcome={"risk_note": "R:R too low", "limits_note": "OK"},
        )

        notifier.send_message.assert_not_called()


class TestNotifyDispatch:
    def test_signal_insight_notification_format(self) -> None:
        """Invoking notify('signal_insight') sends properly formatted message."""
        notifier = TelegramNotifier()
        notifier.enabled = True
        notifier.send_message = MagicMock()

        notifier.notify(
            "signal_insight",
            symbol="BTC/USDT",
            reason="TAKE_PROFIT",
            roi_percent=8.33,
            duration_seconds=3600,
        )

        notifier.send_message.assert_called_once()
        text = notifier.send_message.call_args[0][0]
        assert "SIGNAL INSIGHT" in text
        assert "🟢" in text
        assert "Target Hit" in text
        assert "8.33%" in text
        assert "60 mins" in text

    def test_signal_broadcast_uses_admin_chat_when_group_unset(self) -> None:
        """Broadcasts fall back to TELEGRAM_CHAT_ID when group is empty."""
        notifier = TelegramNotifier()
        notifier.enabled = True
        notifier.group_chat_id = ""
        notifier.admin_chat_id = "999888777"
        notifier.send_message = MagicMock()

        notifier.notify(
            "signal",
            signal=_signal(),
            outcome={"signal_status": "Signal Broadcast"},
            signal_id=7,
        )

        notifier.send_message.assert_called_once()
        kwargs = notifier.send_message.call_args[1]
        assert kwargs.get("chat_id") == "999888777"
        assert kwargs.get("parse_mode") == "HTML"

    def test_signal_broadcast_skips_when_no_chat_configured(self) -> None:
        notifier = TelegramNotifier()
        notifier.enabled = True
        notifier.group_chat_id = ""
        notifier.admin_chat_id = ""
        notifier.send_message = MagicMock()

        notifier.notify(
            "signal",
            signal=_signal(),
            outcome={"signal_status": "Signal Broadcast"},
            signal_id=1,
        )

        notifier.send_message.assert_not_called()

    def test_disabled_notifier_skips_send(self) -> None:
        """With no token, send_message does nothing and doesn't raise."""
        notifier = TelegramNotifier()
        notifier.enabled = False
        # Should not raise even though no URL is set
        notifier.send_message("This should be a no-op")
