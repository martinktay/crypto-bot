from app.strategies.breakout_volume import BreakoutVolumeStrategy
from app.strategies.ema_rsi import EmaRsiStrategy
from app.strategies.registry import build_strategy


def test_build_known_strategy() -> None:
    strategy = build_strategy("breakout_volume")
    assert isinstance(strategy, BreakoutVolumeStrategy)


def test_build_unknown_strategy_defaults_to_ema_rsi() -> None:
    strategy = build_strategy("does_not_exist")
    assert isinstance(strategy, EmaRsiStrategy)
