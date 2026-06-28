from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import SourceReference
from .technical_indicators import calculate_technicals, candles_to_records, normalize_candles


def fetch_yfinance_market_snapshot(ticker: str, period: str = "2y", interval: str = "1d") -> dict[str, Any]:
    """Fetch yfinance candles and calculate technicals.

    yfinance is imported lazily so tests and fixture-only runs can avoid requiring network access.
    """
    import yfinance as yf

    retrieved_at = datetime.now(timezone.utc)
    raw = yf.download(
        tickers=ticker,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    candles = normalize_candles(raw)
    technicals = calculate_technicals(candles)
    if candles.empty:
        raise ValueError(f"No yfinance candles returned for {ticker}")

    source = SourceReference(
        source_type="market_data",
        name="yfinance historical candles",
        dataset_id=f"yfinance:{ticker}:{period}:{interval}",
        timestamp=technicals.market.get("last_candle_date"),
        retrieved_at=retrieved_at,
        reliability_tier="tier_2",
    )
    return {
        "market": technicals.market,
        "candles": candles_to_records(candles),
        "sources": [source],
        "missing_data": technicals.missing_data,
        "status": "available",
    }
