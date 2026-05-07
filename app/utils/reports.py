import numpy as np
import pandas as pd
from typing import List
from app.schemas.backtest import BacktestTrade

def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.0) -> float:
    if not returns:
        return 0.0
    arr = np.array(returns)
    avg_return = np.mean(arr)
    std_dev = np.std(arr)
    if std_dev == 0:
        return 0.0
    return (avg_return - risk_free_rate) / std_dev * np.sqrt(252) # Annualized

def calculate_max_drawdown(equity_curve: List[float]) -> float:
    if not equity_curve:
        return 0.0
    series = pd.Series(equity_curve)
    rolling_max = series.cummax()
    drawdowns = (series - rolling_max) / rolling_max
    return float(drawdowns.min() * 100) # Percentage

def generate_performance_summary(trades: List[BacktestTrade], initial_balance: float) -> dict:
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "final_balance": initial_balance,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0
        }
    
    pnls = [t.pnl for t in trades]
    roi_pcts = [t.roi_percent / 100 for t in trades]
    wins = [p for p in pnls if p > 0]
    
    current_balance = initial_balance
    equity_curve = [initial_balance]
    for pnl in pnls:
        current_balance += pnl
        equity_curve.append(current_balance)
    
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0
    
    return {
        "total_trades": len(trades),
        "win_rate": round(win_rate, 2),
        "final_balance": round(current_balance, 2),
        "max_drawdown": round(calculate_max_drawdown(equity_curve), 2),
        "sharpe_ratio": round(calculate_sharpe_ratio(roi_pcts), 2)
    }
