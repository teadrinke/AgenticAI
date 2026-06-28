import pandas as pd

from app.technical_indicators import calculate_technicals, candles_to_records, normalize_candles


def make_candles(count: int = 220) -> pd.DataFrame:
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


def test_normalize_candles_standardizes_columns():
    candles = normalize_candles(make_candles())

    assert "adjusted_close" in candles.columns
    assert "close" in candles.columns
    assert len(candles) == 220


def test_calculate_technicals_with_enough_candles():
    candles = normalize_candles(make_candles())
    snapshot = calculate_technicals(candles)

    assert snapshot.market["ma_20"] is not None
    assert snapshot.market["ma_50"] is not None
    assert snapshot.market["ma_200"] is not None
    assert snapshot.market["rsi"] is not None
    assert snapshot.market["macd_direction"] in {"positive", "negative"}
    assert len(snapshot.market["support_levels"]) == 2
    assert len(snapshot.market["resistance_levels"]) == 2
    assert candles_to_records(candles)[0]["source"] == "yfinance"


def test_calculate_technicals_flags_short_history():
    candles = normalize_candles(make_candles(10))
    snapshot = calculate_technicals(candles)

    assert snapshot.market["ma_20"] is None
    assert snapshot.market["rsi"] is None
    assert any("RSI" in item for item in snapshot.missing_data)
    assert any("200-day" in item for item in snapshot.missing_data)
