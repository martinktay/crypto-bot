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
        notifier = TelegramNotifier()
        msg = notifier.build_signal_message(_signal(), {"signal_status": "Signal Recorded 📝"})
        assert "NEW SIGNAL" in msg
        assert "Result: LONG for BTC/USDT" in msg
        assert "🧠 AI INSIGHT" in msg
        assert "EMA crossover bullish" in msg
        assert "85.0%" in msg
        assert "LONG" in msg
        assert "Entry:" in msg
        assert "TP/SL:" in msg
        assert "64000 / 58000" in msg

    def test_rejection_message_includes_risk_note(self) -> None:
        notifier = TelegramNotifier()
        outcome = {"risk_note": "R:R too low", "limits_note": "OK"}
        msg = notifier.build_rejection_message(_signal(), outcome)
        assert "REJECTED" in msg
        assert "R:R too low" in msg
        assert "Pair: BTC/USDT" in msg
        assert "Timeframe: 15m" in msg
        assert "Risk: R:R too low" in msg
        assert "Limits: OK" in msg


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

    def test_approval_needed_sends_no_inline_keyboard(self) -> None:
        """Manual approval notification does not include inline buttons (disabled)."""
        notifier = TelegramNotifier()
        notifier.enabled = True
        notifier.send_message = MagicMock()

        notifier.notify(
            "approval_needed",
            signal=_signal(),
            approval_id="abc-123-def-456",
            outcome={"signal_status": "waiting"},
        )

        notifier.send_message.assert_called_once()
        call_kwargs = notifier.send_message.call_args
        # Ensure no reply_markup was provided.
        assert call_kwargs[1].get("reply_markup") is None

    def test_disabled_notifier_skips_send(self) -> None:
        """With no token, send_message does nothing and doesn't raise."""
        notifier = TelegramNotifier()
        notifier.enabled = False
        # Should not raise even though no URL is set
        notifier.send_message("This should be a no-op")
