"""Market data provider — public OHLCV / ticker fetcher across exchanges.

The provider holds a *registry* of ccxt exchange clients (Binance, Bybit,
MEXC, …). Symbols can be either bare (``BTC/USDT``) or qualified
(``bybit:SOL/USDT``); the qualifier picks the exchange in the registry.

Two non-obvious pieces of robustness live here, both required to keep the
bot working in restricted environments:

1. **Binance public-data CDN fallback.** Many UK/EU consumer ISPs and
   corporate DNS filters block ``api.binance.com`` while leaving
   ``data-api.binance.vision`` (the read-only spot CDN behind chart
   embeds) reachable. When the upstream probe fails for Binance, we
   reroute spot OHLCV / exchangeInfo / ticker requests through that CDN
   and constrain market discovery to spot — futures endpoints aren't
   served by the CDN.

2. **HTTPS_PROXY / HTTP_PROXY plumbing.** Bybit and MEXC have *no*
   equivalent CDN, so they're either reachable or they're not. If the
   user provides a proxy via env vars, every ccxt client is configured
   with it (sync requests via ``exchange.proxies``) and the urllib
   reachability probe inherits it from the OS env. Without a proxy on a
   blocked network, those exchanges raise ``ExchangeUnavailable`` and
   the pipeline simply skips their symbols rather than crashing the
   whole cycle.
"""

from __future__ import annotations

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


class ExchangeUnavailable(RuntimeError):
    """Raised when an exchange id is requested but not in the registry."""


class MarketDataProvider:
    """Multi-exchange OHLCV / ticker provider.

    A single instance holds one ccxt client per exchange listed in
    :pyattr:`Settings.exchange_list`. Public methods accept symbols in
    either ``"BTC/USDT"`` or ``"binance:BTC/USDT"`` form; the prefix
    routes to the matching client.
    """

    def __init__(
        self,
        exchange_name: str | None = None,
        market_type: str | None = None,
        exchanges: list[str] | None = None,
    ) -> None:
        self.exchange_id = (exchange_name or settings.exchange_name).lower()
        self.market_type = market_type or settings.exchange_market_type

        configured = exchanges if exchanges is not None else settings.exchange_list
        # Make sure the default exchange is always present so unqualified
        # symbols always resolve to *something*. Preserve user-provided order.
        ordered: list[str] = []
        for ex in [*configured, self.exchange_id]:
            ex = (ex or "").lower()
            if ex and ex not in ordered:
                ordered.append(ex)

        self._exchanges: dict[str, ccxt.Exchange] = {}
        for ex_id in ordered:
            try:
                self._exchanges[ex_id] = self._build_exchange(ex_id)
            except (AttributeError, ccxt.NotSupported) as exc:
                # Unknown / unsupported exchange id — log & skip rather than
                # crash. Legitimate failures (bad credentials, throttling)
                # surface later from fetch_ohlcv with a clearer message.
                logger.error(
                    "MarketDataProvider: skipping unsupported exchange %r (%s)",
                    ex_id,
                    exc.__class__.__name__,
                )

        # Keep ``self.exchange`` as a convenience alias for the default
        # exchange — single-exchange callers and tests rely on it.
        self.exchange = self._exchanges.get(self.exchange_id)
        if self.exchange is None:
            raise ExchangeUnavailable(
                f"Default exchange {self.exchange_id!r} could not be initialised"
            )

    # ------------------------------------------------------------------ #
    #  Construction helpers
    # ------------------------------------------------------------------ #

    def _build_exchange(self, exchange_id: str) -> ccxt.Exchange:
        """Construct one ccxt client with the standard per-exchange tuning."""
        exchange_cls = getattr(ccxt, exchange_id)
        config: dict[str, Any] = {
            "enableRateLimit": True,
            "timeout": 10000,
            "options": {"defaultType": self.market_type},
        }
        client = exchange_cls(config)

        # Proxies: ccxt's sync HTTP path uses ``requests`` which honours
        # ``exchange.proxies``. Setting both 'http' and 'https' covers
        # whichever scheme the underlying URLs end up using.
        proxy = settings.https_proxy or settings.http_proxy
        if proxy:
            client.proxies = {"http": proxy, "https": proxy}
            logger.info(
                "MarketDataProvider: %s using proxy %s",
                exchange_id,
                _mask_proxy(proxy),
            )

        if settings.exchange_testnet and hasattr(client, "set_sandbox_mode"):
            client.set_sandbox_mode(True)

        # Binance-only: transparent rerouting through data-api.binance.vision
        # when api.binance.com is geo-blocked. Constrain market discovery to
        # spot so load_markets() doesn't hit fapi/dapi/eapi.
        if exchange_id == "binance" and self._upstream_unreachable():
            # Force *this* Binance client to spot + the public-data CDN only.
            # Do not mutate ``self.market_type``: other exchanges in the same
            # registry must keep ``settings.exchange_market_type`` (e.g. swap)
            # or ``fetch_ohlcv`` will hit the wrong market category.
            client.options["defaultType"] = "spot"
            client.options["fetchMarkets"] = ["spot"]
            client.urls["api"]["public"] = f"{_BINANCE_PUBLIC_DATA_HOST}/api/v3"
            logger.warning(
                "api.binance.com unreachable; routing public spot requests through "
                "%s and limiting market discovery to spot. Keep "
                "EXCHANGE_MARKET_TYPE=spot in .env on this network.",
                _BINANCE_PUBLIC_DATA_HOST,
            )

        return client

    def _upstream_unreachable(self) -> bool:
        """Cheap reachability probe to decide whether to use the data mirror.

        Uses a short HTTP GET to ``api.binance.com`` with a ~2s timeout,
        falling back to True (i.e. *use* the mirror) on any failure.
        ``urllib.request`` automatically picks up ``HTTPS_PROXY`` from the
        OS environment, so this respects the user's proxy config.
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

    # ------------------------------------------------------------------ #
    #  Public surface
    # ------------------------------------------------------------------ #

    @property
    def exchange_ids(self) -> list[str]:
        """Ids of every exchange in the registry, in registration order."""
        return list(self._exchanges.keys())

    def get_exchange(self, exchange_id: str) -> ccxt.Exchange:
        """Look up a ccxt client by id, or raise :class:`ExchangeUnavailable`."""
        ex_id = (exchange_id or self.exchange_id).lower()
        client = self._exchanges.get(ex_id)
        if client is None:
            raise ExchangeUnavailable(
                f"Exchange {ex_id!r} is not initialised. "
                f"Add it to EXCHANGES (current: {self.exchange_ids})."
            )
        return client

    def parse(self, symbol: str) -> tuple[str, str]:
        """Resolve ``"BTC/USDT"`` or ``"bybit:SOL/USDT"`` to ``(exchange, raw)``.

        Thin wrapper around :meth:`Settings.parse_symbol` that also forces
        the resulting exchange id to one that's actually in the registry —
        unknown prefixes fall back to the default exchange (so the user
        gets *some* result rather than an opaque KeyError).
        """
        ex_id, raw = settings.parse_symbol(symbol)
        if ex_id not in self._exchanges:
            logger.debug(
                "Unknown exchange prefix %r for symbol %r; falling back to %s",
                ex_id,
                symbol,
                self.exchange_id,
            )
            ex_id = self.exchange_id
        return ex_id, raw

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
        since: int | None = None,
    ) -> list[list[float]]:
        """Fetch OHLCV data with pagination if ``limit`` exceeds the per-call cap."""
        exchange_id, raw_symbol = self.parse(symbol)
        client = self.get_exchange(exchange_id)

        all_ohlcv: list[list[float]] = []
        current_since = since
        remaining = limit

        while remaining > 0:
            fetch_limit = min(remaining, 1000)
            try:
                ohlcv = client.fetch_ohlcv(
                    raw_symbol, timeframe, current_since, fetch_limit
                )
                if not ohlcv:
                    break

                all_ohlcv.extend(ohlcv)
                remaining -= len(ohlcv)

                last_ts = ohlcv[-1][0]
                current_since = last_ts + 1

                if remaining > 0:
                    time.sleep(client.rateLimit / 1000)
            except Exception as exc:
                logger.error(
                    "Failed to fetch OHLCV segment for %s on %s: %s",
                    raw_symbol,
                    exchange_id,
                    exc,
                )
                break

        return all_ohlcv[:limit]

    def usdt_linear_swap_symbols(self, exchange_id: str) -> list[str]:
        """List active USDT-settled linear perpetual symbols (ccxt unified).

        Includes both ``type`` ``swap`` and linear ``future`` listings where
        settlement is USDT. Coin-margined (inverse) contracts use a non-USDT
        ``settle`` and are excluded.
        """
        client = self.get_exchange(exchange_id)
        markets = client.load_markets()
        found: set[str] = set()
        for m in markets.values():
            if not m.get("active"):
                continue
            if m.get("type") not in ("swap", "future"):
                continue
            settle = m.get("settle")
            linear = m.get("linear")
            # USDT-margined linear perp (exclude inverse / coin-margined).
            if settle == "USDT":
                if linear is False:
                    continue
                found.add(m["symbol"])
            elif (
                linear is True
                and m.get("quote") == "USDT"
                and (settle in (None, "USDT"))
            ):
                found.add(m["symbol"])
        return sorted(found)

    def fetch_futures_symbols(self, exchange_id: str | None = None) -> list[str]:
        """Fetch all active swap/futures symbols from the chosen exchange."""
        client = self.get_exchange(exchange_id or self.exchange_id)
        markets = client.load_markets()
        return [
            m["symbol"]
            for m in markets.values()
            if m["active"] and (m.get("type") == "swap" or m.get("type") == "future")
        ]

    def fetch_top_volume_symbols(
        self, limit: int = 50, exchange_id: str | None = None
    ) -> list[str]:
        """Fetch top N futures symbols on the chosen exchange by 24h volume."""
        client = self.get_exchange(exchange_id or self.exchange_id)
        tickers = client.fetch_tickers()
        futures_symbols = self.fetch_futures_symbols(exchange_id)

        valid_tickers = []
        for sym in futures_symbols:
            if sym in tickers:
                valid_tickers.append(tickers[sym])

        sorted_tickers = sorted(
            valid_tickers,
            key=lambda x: x.get("quoteVolume") or 0,
            reverse=True,
        )

        return [t["symbol"] for t in sorted_tickers[:limit]]

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        exchange_id, raw_symbol = self.parse(symbol)
        client = self.get_exchange(exchange_id)
        attempts = 3
        for attempt in range(1, attempts + 1):
            try:
                return client.fetch_ticker(raw_symbol)
            except ccxt.NetworkError:
                if attempt == attempts:
                    raise
                time.sleep(attempt)
            except (ccxt.AuthenticationError, ccxt.ExchangeError):
                # Don't retry auth / exchange errors.
                raise
        return {}


def _mask_proxy(proxy: str) -> str:
    """Strip credentials from a proxy URL for logging."""
    if "@" not in proxy:
        return proxy
    scheme, _, rest = proxy.partition("://")
    _, _, host = rest.rpartition("@")
    return f"{scheme}://***@{host}" if scheme else f"***@{host}"
