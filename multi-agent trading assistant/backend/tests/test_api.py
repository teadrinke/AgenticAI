from fastapi.testclient import TestClient
from sqlmodel import Session, select

import app.graph as graph_module
from app.database import CandleRow, engine
from app.main import app
from app.models import SourceReference


def test_analyze_route_persists_and_lists_result(monkeypatch):
    def unavailable_yfinance(_: str):
        raise RuntimeError("offline")

    monkeypatch.setattr(graph_module, "fetch_yfinance_market_snapshot", unavailable_yfinance)
    monkeypatch.setattr(
        graph_module,
        "fetch_tavily_context",
        lambda *_: {
            "status": "unavailable",
            "missing_data": ["missing key"],
            "sources": [],
            "news": None,
            "fundamentals": None,
            "metrics": {"tavily_call_count": 0, "tavily_credits": 0, "tavily_status": "missing_key"},
        },
    )
    with TestClient(app) as client:
        response = client.post(
            "/analyze",
            json={
                "query": "Should I trade NVDA after earnings?",
                "ticker": "NVDA",
                "time_horizon": "swing",
                "risk_profile": "unknown",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["final"]["recommendation"] == "Wait"
        assert payload["critic"]["reliability"] == "pass_with_cautions"

        history = client.get("/analyses")
        assert history.status_code == 200
        assert any(item["id"] == payload["id"] for item in history.json())


def test_analyze_route_persists_yfinance_candles(monkeypatch):
    def fake_yfinance(_: str):
        return {
            "market": {
                "current_price": 110.0,
                "previous_close": 108.0,
                "ma_20": 104.0,
                "ma_50": 100.0,
                "ma_200": None,
                "rsi": 66.0,
                "macd_direction": "positive",
                "relative_volume": 1.2,
                "atr_percent": 2.5,
                "support_levels": [101.0, 103.0],
                "resistance_levels": [112.0, 115.0],
                "recent_gaps": [],
                "candle_count": 2,
                "last_candle_date": "2026-06-12",
                "data_source": "yfinance",
            },
            "candles": [
                {
                    "date": "2026-06-11",
                    "open": 107.0,
                    "high": 109.0,
                    "low": 106.0,
                    "close": 108.0,
                    "adjusted_close": 108.0,
                    "volume": 1000000,
                    "source": "yfinance",
                },
                {
                    "date": "2026-06-12",
                    "open": 108.5,
                    "high": 111.0,
                    "low": 108.0,
                    "close": 110.0,
                    "adjusted_close": 110.0,
                    "volume": 1200000,
                    "source": "yfinance",
                },
            ],
            "sources": [
                SourceReference(
                    source_type="market_data",
                    name="yfinance historical candles",
                    dataset_id="yfinance:TEST:6mo:1d",
                    reliability_tier="tier_2",
                )
            ],
            "missing_data": ["200-day moving average requires at least 200 daily candles"],
            "status": "available",
        }

    monkeypatch.setattr(graph_module, "fetch_yfinance_market_snapshot", fake_yfinance)
    monkeypatch.setattr(
        graph_module,
        "fetch_tavily_context",
        lambda *_: {
            "status": "unavailable",
            "missing_data": ["missing key"],
            "sources": [],
            "news": None,
            "fundamentals": None,
            "metrics": {"tavily_call_count": 0, "tavily_credits": 0, "tavily_status": "missing_key"},
        },
    )
    with TestClient(app) as client:
        response = client.post(
            "/analyze",
            json={"query": "Should I trade TEST after earnings?", "ticker": "TEST"},
        )

    assert response.status_code == 200
    analysis_id = response.json()["id"]
    with Session(engine) as session:
        candles = session.exec(select(CandleRow).where(CandleRow.analysis_id == analysis_id)).all()
    assert len(candles) == 2
    assert candles[-1].source == "yfinance"
