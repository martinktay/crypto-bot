from app.strategies.base import Strategy
from app.strategies.breakout_volume import BreakoutVolumeStrategy
from app.strategies.ema_rsi import EmaRsiStrategy


STRATEGIES: dict[str, type[Strategy]] = {
    EmaRsiStrategy.name: EmaRsiStrategy,
    BreakoutVolumeStrategy.name: BreakoutVolumeStrategy,
}


def build_strategy(name: str) -> Strategy:
    strategy_cls = STRATEGIES.get(name, EmaRsiStrategy)
    return strategy_cls()
