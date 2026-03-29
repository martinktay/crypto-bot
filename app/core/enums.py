from enum import Enum


class TradingMode(str, Enum):
    SIGNAL_ONLY = "signal_only"
    MANUAL_APPROVAL = "manual_approval"
    PAPER_TRADING = "paper_trading"
    AUTO_TRADE_LIVE = "auto_trade_live"


class SignalDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    HOLD = "HOLD"


class TradeStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    REJECTED = "rejected"
    ERROR = "error"
