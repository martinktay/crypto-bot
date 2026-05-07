import logging
import asyncio
import pandas as pd
from datetime import datetime, timezone
from typing import Any

from app.market_data.provider import MarketDataProvider
from app.strategies.registry import build_strategy
from app.core.config import settings

logger = logging.getLogger(__name__)

class FuturesScanner:
    def __init__(self):
        # Market type is taken from EXCHANGE_MARKET_TYPE so the scanner and
        # the live signal pipeline always operate on the same product family.
        self.market_data = MarketDataProvider()
        self.strategy = build_strategy(settings.strategy)

    async def scan(self, limit: int = 50, timeframe: str = "15m") -> list[dict]:
        """
        Scans top futures pairs and returns ranked opportunities.
        This is an async-friendly wrapper around sequential exchange calls.
        """
        logger.info("Starting global futures scan for top %d symbols...", limit)
        
        try:
            symbols = self.market_data.fetch_top_volume_symbols(limit=limit)
        except Exception as exc:
            logger.error("Failed to fetch top volume symbols: %s", exc)
            return []

        tasks = []
        for symbol in symbols:
            tasks.append(self._analyze_symbol(symbol, timeframe))
        
        # To avoid overwhelming the exchange and hitting rate limits, 
        # we could chunk these, but CCXT handles rate limiting internally if enabled.
        # However, for a broad scan, we'll run them and collect results.
        results = await asyncio.gather(*tasks)
        
        # Filter for actual signals (Long/Short, not Hold)
        opportunities = [r for r in results if r and r["signal"] != "HOLD"]
        
        # Sort by confidence descending
        opportunities.sort(key=lambda x: x["confidence"], reverse=True)
        
        logger.info("Scan complete. Found %d candidates.", len(opportunities))
        return opportunities

    async def _analyze_symbol(self, symbol: str, timeframe: str) -> dict | None:
        """Fetch data and run strategy for a single symbol."""
        try:
            # We run the synchronous CCXT calls in a thread pool to keep the loop free
            loop = asyncio.get_event_loop()
            raw = await loop.run_in_executor(None, self.market_data.fetch_ohlcv, symbol, timeframe, 100)
            
            if not raw or len(raw) < 50:
                return None

            df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
            # Drop the in-progress bar — strategies should only see closed candles.
            if len(df) > 1:
                df = df.iloc[:-1].reset_index(drop=True)
            signal = self.strategy.generate(symbol, timeframe, df)
            
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "signal": signal.signal.value,
                "entry_price": signal.entry_price,
                "confidence": signal.confidence,
                "reason": signal.reason,
                "timestamp": (signal.timestamp or datetime.now(timezone.utc)).isoformat(),
            }
        except Exception as exc:
            logger.debug("Scanner failed for %s: %s", symbol, exc)
            return None
