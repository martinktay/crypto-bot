"""Unit tests for Telegram handler helpers."""

import html

from app.telegram_bot.handlers import _symbol_list_html_chunks, _symbol_list_html_chunks_budgets


def test_symbol_chunks_empty() -> None:
    assert _symbol_list_html_chunks([]) == []


def test_symbol_chunks_budgets_first_smaller_than_rest() -> None:
    sym = [f"x{i}" for i in range(30)]
    chunks = _symbol_list_html_chunks_budgets(sym, first_max=10, rest_max=50)
    assert len(chunks) >= 2
    assert len(chunks[0]) <= 12


def test_symbol_chunks_single_small() -> None:
    sym = ["bybit:BTC/USDT:USDT", "mexc:ETH/USDT:USDT"]
    chunks = _symbol_list_html_chunks(sym, max_chars=5000)
    assert len(chunks) == 1
    assert chunks[0] == html.escape(", ".join(sym))


def test_symbol_chunks_splits_on_budget() -> None:
    sym = ["a", "b", "c", "d"]
    chunks = _symbol_list_html_chunks(sym, max_chars=4)
    assert len(chunks) >= 2
    joined = ", ".join(sym)
    recovered = html.unescape(", ".join(chunks))
    assert recovered == joined


def test_symbol_chunks_long_entries() -> None:
    sym = [f"mexc:COIN{i}/USDT:USDT" for i in range(200)]
    chunks = _symbol_list_html_chunks(sym, max_chars=200)
    assert len(chunks) > 1
    for ch in chunks:
        assert len(ch) <= 200
