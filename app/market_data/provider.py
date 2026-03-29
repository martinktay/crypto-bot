from __future__ import annotations

from typing import Any

import ccxt


class MarketDataProvider:
    def __init__(self, exchange_name: str = "binance") -> None:
        exchange_cls = getattr(ccxt, exchange_name)
        self.exchange = exchange_cls({"enableRateLimit": True, "timeout": 10000})

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> list[list[float]]:
        return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        return self.exchange.fetch_ticker(symbol)
