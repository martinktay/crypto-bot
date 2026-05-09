import logging
import time
from typing import Any

import ccxt

from app.core.config import settings

logger = logging.getLogger(__name__)


# Read-only public market-data mirror for Binance spot. Many networks (UK/EU
# ISPs, corporate DNS filters, Cloudflare for Families) block api.binance.com
# at DNS/category level but leave the CDN hostname alone — chart embeds and
# TradingView reach Binance through this same endpoint. We fall back to it
# automatically so the bot keeps working in restricted environments without
# manual proxy configuration.
_BINANCE_PUBLIC_DATA_HOST = "https://data-api.binance.vision"


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

        # If the upstream Binance API isn't reachable (geoblock / DNS filter),
        # transparently route public read-only calls (klines, exchangeInfo,
        # tickers) through the public data mirror. This only works for SPOT —
        # there's no futures equivalent — so we also force market_type to spot
        # when the fallback is engaged.
        #
        # IMPORTANT: ccxt's binance ``urls['api']`` dict has many sub-keys
        # (public, private, sapi, fapi, fapiPublic, web, ...). We only override
        # the ones that actually serve spot read-only data — clobbering the
        # whole dict breaks any attribute ccxt resolves lazily.
        #
        # Equally important: ccxt's binance.load_markets() calls four
        # exchangeInfo endpoints by default (spot api + fapi + dapi + eapi),
        # because that's how it discovers every tradable market. On a network
        # where only the spot CDN is reachable, we *must* limit market loading
        # to spot only, otherwise the first fetch_ohlcv call dies trying to
        # reach fapi.binance.com regardless of defaultType.
        if self.exchange_id == "binance" and self._upstream_unreachable():
            self.market_type = "spot"
            self.exchange.options["defaultType"] = "spot"
            self.exchange.options["fetchMarkets"] = ["spot"]
            self.exchange.urls["api"]["public"] = f"{_BINANCE_PUBLIC_DATA_HOST}/api/v3"
            logger.warning(
                "api.binance.com unreachable; routing public spot requests through "
                "%s and limiting market discovery to spot. Keep "
                "EXCHANGE_MARKET_TYPE=spot in .env on this network.",
                _BINANCE_PUBLIC_DATA_HOST,
            )

    def _upstream_unreachable(self) -> bool:
        """Cheap reachability probe to decide whether to use the data mirror.

        Uses a short HTTP HEAD/GET to ``api.binance.com`` with a ~2s timeout,
        falling back to True (i.e. *use* the mirror) on any failure.
        """
        import urllib.error
        import urllib.request

        try:
            req = urllib.request.Request(
                "https://api.binance.com/api/v3/ping",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status >= 400
        except (urllib.error.URLError, OSError, ValueError):
            return True

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
