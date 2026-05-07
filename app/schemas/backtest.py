from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel
from app.core.enums import SignalDirection

class BacktestRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    strategy_name: str = "ema_rsi"
    params: Optional[dict[str, Any]] = None
    days: int = 30
    initial_balance: float = 10000.0

class BacktestTrade(BaseModel):
    symbol: str
    direction: SignalDirection
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    pnl: float
    roi_percent: float
    reason: str

class BacktestResult(BaseModel):
    symbol: str
    strategy: str
    params: Optional[dict[str, Any]] = None
    timeframe: str
    period_days: int
    initial_balance: float
    final_balance: float
    total_trades: int
    win_rate: float
    max_drawdown_percent: float
    sharpe_ratio: float
    trades: List[BacktestTrade]
