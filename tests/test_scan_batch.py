"""Round-robin batching for large SYMBOLS universes."""

from app.services.signal_service import _symbol_batch_slice


def test_batch_returns_all_when_under_cap() -> None:
    syms = ["a", "b", "c"]
    chunk, off = _symbol_batch_slice(syms, 80, 99)
    assert chunk == syms
    assert off == 0


def test_batch_zero_means_all() -> None:
    syms = ["x", "y"]
    chunk, off = _symbol_batch_slice(syms, 0, 3)
    assert chunk == syms
    assert off == 0


def test_batch_wraps_offset() -> None:
    syms = ["a", "b", "c", "d"]
    c1, o1 = _symbol_batch_slice(syms, 3, 0)
    assert c1 == ["a", "b", "c"]
    assert o1 == 3
    c2, o2 = _symbol_batch_slice(syms, 3, o1)
    assert c2 == ["d", "a", "b"]
    assert o2 == 2
