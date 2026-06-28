import types

import pandas as pd

from app.market_data_provider import fetch_yfinance_market_snapshot


def make_candles(count: int = 80) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=count, freq="D")
    close = pd.Series([100 + index * 0.5 for index in range(count)], index=dates)
    return pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Adj Close": close,
            "Volume": [1_000_000 + index * 1000 for index in range(count)],
        },
        index=dates,
    )


def test_yfinance_provider_returns_candles_and_source(monkeypatch):
    fake_yfinance = types.SimpleNamespace(download=lambda **_: make_candles(80))

    import sys

    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)

    snapshot = fetch_yfinance_market_snapshot("NVDA")

    assert snapshot["status"] == "available"
    assert snapshot["market"]["data_source"] == "yfinance"
    assert len(snapshot["candles"]) == 80
    assert snapshot["sources"][0].name == "yfinance historical candles"


def test_yfinance_provider_raises_for_empty_response(monkeypatch):
    fake_yfinance = types.SimpleNamespace(download=lambda **_: pd.DataFrame())

    import sys

    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)

    try:
        fetch_yfinance_market_snapshot("BAD")
    except ValueError as exc:
        assert "No yfinance candles returned" in str(exc)
    else:
        raise AssertionError("Expected empty yfinance response to raise")
