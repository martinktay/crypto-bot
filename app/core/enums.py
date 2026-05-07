from enum import Enum


class ApprovalMode(str, Enum):
    AUTO = "auto"
    MANUAL_APPROVAL = "manual_approval"


class SignalDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    HOLD = "HOLD"
