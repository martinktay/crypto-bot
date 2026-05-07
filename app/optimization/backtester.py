import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from app.market_data.provider import MarketDataProvider
from app.schemas.backtest import BacktestRequest, BacktestResult, BacktestTrade
from app.strategies.registry import STRATEGIES
from app.core.enums import SignalDirection
from app.db.repository import StateRepository

logger = logging.getLogger(__name__)

class BacktestService:
    def __init__(self, provider: Optional[MarketDataProvider] = None) -> None:
        self.provider = provider or MarketDataProvider()

    def run_backtest(self, request: BacktestRequest, repo: Optional[StateRepository] = None) -> BacktestResult:
        logger.info("Starting backtest for %s on %s (%d days)", request.strategy_name, request.symbol, request.days)
        
        # 1. Fetch Data
        # Approximate limit based on days and timeframe
        limit = self._calculate_limit(request.timeframe, request.days)
        # Add 100 candles for indicator warmup
        ohlcv = self.provider.fetch_ohlcv(request.symbol, request.timeframe, limit=limit + 100)
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        
        # 2. Setup Strategy
        if request.strategy_name not in STRATEGIES:
            raise ValueError(f"Strategy {request.strategy_name} not found in registry")
            
        strategy_cls = STRATEGIES[request.strategy_name]
        strategy = strategy_cls(**(request.params or {}))
        
        # 3. Simulation Loop
        balance = request.initial_balance
        position = None # None or {'direction': SignalDirection, 'entry_price': float, 'entry_time': datetime}
        trades: List[BacktestTrade] = []
        
        # Start after warmup period
        for i in range(100, len(df)):
            current_row = df.iloc[i]
            history = df.iloc[:i+1] # Visible history up to now
            
            # Check for exits if in position
            if position:
                exit_price = current_row['close']
                is_exit = False
                exit_reason = ""
                
                # Simple SL/TP check or Opposite Signal
                # Note: In a real backtester, we'd check High/Low for SL/TP hits during the candle
                
                # For this MVP, we generate signal every step to see if we should flip
                signal_contract = strategy.generate(request.symbol, request.timeframe, history, params=request.params)
                
                # Exit if signal is HOLD or opposite direction
                if signal_contract.signal == SignalDirection.HOLD or signal_contract.signal != position['direction']:
                    is_exit = True
                    exit_reason = "Signal Change"
                
                if is_exit:
                    pnl = 0
                    if position['direction'] == SignalDirection.LONG:
                        pnl = (exit_price - position['entry_price']) / position['entry_price'] * balance
                    else:
                        pnl = (position['entry_price'] - exit_price) / position['entry_price'] * balance
                    
                    balance += pnl
                    trade = BacktestTrade(
                        symbol=request.symbol,
                        direction=position['direction'],
                        entry_time=position['entry_time'],
                        entry_price=position['entry_price'],
                        exit_time=current_row['timestamp'],
                        exit_price=exit_price,
                        pnl=pnl,
                        roi_percent=(pnl / (balance - pnl)) * 100 if (balance - pnl) != 0 else 0,
                        reason=exit_reason
                    )
                    trades.append(trade)
                    position = None

            # Check for entries if not in position
            if not position:
                signal_contract = strategy.generate(request.symbol, request.timeframe, history, params=request.params)
                if signal_contract.signal in [SignalDirection.LONG, SignalDirection.SHORT]:
                    position = {
                        'direction': signal_contract.signal,
                        'entry_price': current_row['close'],
                        'entry_time': current_row['timestamp']
                    }

        # 4. Finalize Metrics
        total_trades = len(trades)
        win_rate = (len([t for t in trades if t.pnl > 0]) / total_trades * 100) if total_trades > 0 else 0
        
        # Simple Sharpe (assuming daily returns)
        roi_list = [t.roi_percent / 100 for t in trades]
        sharpe = np.mean(roi_list) / np.std(roi_list) * np.sqrt(252) if len(roi_list) > 1 and np.std(roi_list) > 0 else 0
        
        # Max Drawdown
        pnl_series = pd.Series([t.pnl for t in trades]).cumsum() + request.initial_balance
        running_max = pnl_series.cummax()
        drawdown = (pnl_series - running_max) / running_max
        max_dd = abs(drawdown.min() * 100) if not drawdown.empty else 0

        result = BacktestResult(
            symbol=request.symbol,
            strategy=request.strategy_name,
            params=request.params,
            timeframe=request.timeframe,
            period_days=request.days,
            initial_balance=request.initial_balance,
            final_balance=balance,
            total_trades=total_trades,
            win_rate=win_rate,
            max_drawdown_percent=max_dd,
            sharpe_ratio=sharpe,
            trades=trades
        )
        
        if repo:
            repo.save_backtest_history(result)
            
        return result

    def _calculate_limit(self, timeframe: str, days: int) -> int:
        # Convert days to minutes
        total_minutes = days * 24 * 60
        # Timeframe is like '1m', '5m', '1h', '1d'
        unit = timeframe[-1]
        val = int(timeframe[:-1])
        
        if unit == 'm':
            return total_minutes // val
        elif unit == 'h':
            return (total_minutes // 60) // val
        elif unit == 'd':
            return days // val
        return 500 # Default fallback
