from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import SourceReference


def build_fixture_snapshot(ticker: str) -> dict[str, Any]:
    """Return deterministic fixture data until paid/free provider adapters are added."""
    now = datetime.now(timezone.utc)
    upper = ticker.upper()
    return {
        "ticker": upper,
        "market": {
            "current_price": 128.75,
            "previous_close": 124.2,
            "ma_20": 122.1,
            "ma_50": 117.4,
            "ma_200": 101.8,
            "rsi": 68.5,
            "macd_direction": "positive",
            "relative_volume": 1.8,
            "atr_percent": 4.6,
            "support_levels": [121.5, 116.8],
            "resistance_levels": [132.0, 139.5],
            "recent_gaps": ["Post-earnings gap higher remains partly untested"],
            "candle_count": 0,
            "last_candle_date": None,
            "data_source": "fixture",
        },
        "news": {
            "headlines": [
                f"{upper} earnings headlines are broadly positive in the fixture snapshot",
                "Analyst commentary remains constructive but highlights valuation sensitivity",
            ],
            "speculation": [
                "Social discussion shows momentum interest that may exaggerate near-term expectations",
            ],
            "analyst_actions": ["Fixture analyst set: several positive notes, no verified exact target changes"],
            "sector_macro": [
                "Semiconductor sector sentiment remains sensitive to AI demand and interest-rate expectations",
            ],
            "sentiment_score": 0.65,
            "hype_risk": "high",
            "priced_in": "possible",
        },
        "fundamentals": {
            "revenue_growth": "strong",
            "eps_surprise": "positive",
            "guidance": "positive",
            "margins": "improving",
            "free_cash_flow": "strong",
            "debt_risk": "low",
            "valuation": "expensive",
            "segments": ["Data center growth remains the main bullish driver in this fixture"],
            "management": ["Management commentary is assumed constructive in the fixture snapshot"],
        },
        "sources": [
            SourceReference(
                source_type="fixture",
                name="MVP fixture market data",
                dataset_id=f"fixture-market-{upper}",
                timestamp=now.isoformat(),
                reliability_tier="unknown",
            ),
            SourceReference(
                source_type="fixture",
                name="MVP fixture news and fundamentals",
                dataset_id=f"fixture-news-fundamentals-{upper}",
                timestamp=now.isoformat(),
                reliability_tier="unknown",
            ),
        ],
    }
