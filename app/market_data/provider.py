import logging
import time
from typing import Any

import ccxt

from app.core.config import settings

logger = logging.getLogger(__name__)


class MarketDataProvider:
    def __init__(self, exchange_name: str | None = None, market_type: str | None = None) -> None:
        self.exchange_id = exchange_name or settings.exchange_name
        self.market_type = market_type or settings.exchange_market_type
        exchange_cls = getattr(ccxt, self.exchange_id)

        config = {
            "enableRateLimit": True,
            "timeout": 10000,
            "options": {"defaultType": self.market_type},
        }

        self.exchange = exchange_cls(config)

        if settings.exchange_testnet and hasattr(self.exchange, "set_sandbox_mode"):
            self.exchange.set_sandbox_mode(True)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500, since: int | None = None) -> list[list[float]]:
        """Fetch OHLCV data with pagination if limit > exchange limit."""
        all_ohlcv = []
        current_since = since
        remaining = limit
        
        while remaining > 0:
            fetch_limit = min(remaining, 1000)
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, current_since, fetch_limit)
                if not ohlcv:
                    break
                
                all_ohlcv.extend(ohlcv)
                remaining -= len(ohlcv)
                
                last_ts = ohlcv[-1][0]
                current_since = last_ts + 1
                
                if remaining > 0:
                    time.sleep(self.exchange.rateLimit / 1000)
            except Exception as exc:
                logger.error("Failed to fetch OHLCV segment for %s: %s", symbol, exc)
                break
                
        return all_ohlcv[:limit]

    def fetch_futures_symbols(self) -> list[str]:
        """Fetch all active swap/futures symbols."""
        markets = self.exchange.load_markets()
        return [
            m["symbol"] for m in markets.values() 
            if m["active"] and (m.get("type") == "swap" or m.get("type") == "future")
        ]

    def fetch_top_volume_symbols(self, limit: int = 50) -> list[str]:
        """Fetch top N futures symbols by 24h volume for scan efficiency."""
        tickers = self.exchange.fetch_tickers()
        futures_symbols = self.fetch_futures_symbols()
        
        # Filter for futures and sort by baseVolume or quoteVolume
        valid_tickers = []
        for symbol in futures_symbols:
            if symbol in tickers:
                valid_tickers.append(tickers[symbol])
        
        # Sort by quoteVolume (usually USDT volume) descending
        sorted_tickers = sorted(
            valid_tickers, 
            key=lambda x: x.get("quoteVolume") or 0, 
            reverse=True
        )
        
        return [t["symbol"] for t in sorted_tickers[:limit]]

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        attempts = 3
        for attempt in range(1, attempts + 1):
            try:
                return self.exchange.fetch_ticker(symbol)
            except ccxt.NetworkError:
                if attempt == attempts:
                    raise
                time.sleep(attempt)
            except (ccxt.AuthenticationError, ccxt.ExchangeError):
                # Don't retry logic / auth errors.
                raise
        return {}
