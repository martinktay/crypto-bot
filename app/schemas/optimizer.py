from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.schemas.backtest import BacktestResult

class OptimizerRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    strategy_name: str = "ema_rsi"
    days: int = 30
    population_size: int = 10
    generations: int = 3

class OptimizerResult(BaseModel):
    symbol: str
    strategy: str
    best_params: Dict[str, Any]
    best_sharpe: float
    best_return_pct: float
    total_simulations: int
    top_performers: List[BacktestResult]
