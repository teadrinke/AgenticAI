from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import SourceReference


FUNDAMENTAL_KEYS = {
    "eps": "trailingEps",
    "pe_ratio": "trailingPE",
    "de_ratio": "debtToEquity",
    "fcf": "freeCashflow",
    "roe": "returnOnEquity",
}


def fetch_yfinance_fundamentals(ticker: str) -> dict[str, Any]:
    import yfinance as yf

    info = yf.Ticker(ticker).info or {}
    metrics = {name: info.get(yahoo_key) for name, yahoo_key in FUNDAMENTAL_KEYS.items()}
    source = SourceReference(
        source_type="fundamentals",
        name="yfinance fundamentals snapshot",
        dataset_id=f"yfinance-fundamentals:{ticker}",
        timestamp=datetime.now(timezone.utc).date().isoformat(),
        retrieved_at=datetime.now(timezone.utc),
        reliability_tier="tier_2",
    )
    missing = [name for name, value in metrics.items() if value is None]
    return {
        "status": "available" if any(value is not None for value in metrics.values()) else "unavailable",
        "metrics": metrics,
        "missing_data": [f"Missing {name}" for name in missing],
        "sources": [source],
    }

