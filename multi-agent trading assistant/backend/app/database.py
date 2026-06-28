from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Field, Session, SQLModel, create_engine, select

from .models import (
    AnalysisResponse,
    AnalysisSummary,
    AnalyzeRequest,
    CriticOutput,
    FinalRecommendation,
    FundamentalEarningsOutput,
    MarketDataOutput,
    NewsSentimentOutput,
    SourceReference,
)


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./financial_assistant.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})


LEGACY_RECOMMENDATIONS = {
    "Buy": "Buy setup",
    "Sell": "Avoid / No trade",
    "Hold": "Neutral / Watchlist",
    "Avoid": "Avoid / No trade",
}


def _normalize_recommendation(value: str) -> str:
    return LEGACY_RECOMMENDATIONS.get(value, value)


class Analysis(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    query: str
    ticker: str = Field(index=True)
    recommendation: str
    confidence: float
    risk_level: str
    status: str = "completed"
    final_json: str
    sources_json: str
    metrics_json: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)


class AgentOutputRow(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    analysis_id: int = Field(index=True, foreign_key="analysis.id")
    agent_name: str = Field(index=True)
    confidence: float | None = None
    missing_data_json: str = "[]"
    output_json: str


class CandleRow(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    analysis_id: int = Field(index=True, foreign_key="analysis.id")
    ticker: str = Field(index=True)
    date: str = Field(index=True)
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int
    source: str = "yfinance"
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def _dump_model(value: Any) -> str:
    if hasattr(value, "model_dump"):
        return json.dumps(value.model_dump(mode="json"), default=str)
    if isinstance(value, list):
        return json.dumps(
            [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value],
            default=str,
        )
    return json.dumps(value, default=str)


def save_analysis(
    request: AnalyzeRequest,
    final: FinalRecommendation,
    market: MarketDataOutput,
    news: NewsSentimentOutput,
    fundamentals: FundamentalEarningsOutput,
    critic: CriticOutput,
    sources: list[SourceReference],
    metrics: dict[str, Any],
    candles: list[dict[str, Any]] | None = None,
) -> int:
    init_db()
    with Session(engine) as session:
        analysis = Analysis(
            query=request.query,
            ticker=request.ticker,
            recommendation=final.recommendation.value,
            confidence=final.confidence,
            risk_level=final.risk_level,
            final_json=_dump_model(final),
            sources_json=_dump_model(sources),
            metrics_json=json.dumps(metrics, default=str),
        )
        session.add(analysis)
        session.commit()
        session.refresh(analysis)
        assert analysis.id is not None

        agent_rows = [
            AgentOutputRow(
                analysis_id=analysis.id,
                agent_name=market.agent,
                confidence=market.confidence,
                missing_data_json=json.dumps(market.missing_data),
                output_json=_dump_model(market),
            ),
            AgentOutputRow(
                analysis_id=analysis.id,
                agent_name=news.agent,
                confidence=news.confidence,
                missing_data_json=json.dumps(news.missing_data),
                output_json=_dump_model(news),
            ),
            AgentOutputRow(
                analysis_id=analysis.id,
                agent_name=fundamentals.agent,
                confidence=fundamentals.confidence,
                missing_data_json=json.dumps(fundamentals.missing_data),
                output_json=_dump_model(fundamentals),
            ),
            AgentOutputRow(
                analysis_id=analysis.id,
                agent_name=critic.agent,
                confidence=None,
                missing_data_json=json.dumps(critic.missing_evidence),
                output_json=_dump_model(critic),
            ),
        ]
        session.add_all(agent_rows)
        candle_rows = [
            CandleRow(
                analysis_id=analysis.id,
                ticker=request.ticker,
                date=candle["date"],
                open=candle["open"],
                high=candle["high"],
                low=candle["low"],
                close=candle["close"],
                adjusted_close=candle["adjusted_close"],
                volume=candle["volume"],
                source=candle.get("source", "yfinance"),
            )
            for candle in (candles or [])
        ]
        session.add_all(candle_rows)
        session.commit()
        return analysis.id


def list_analyses(limit: int = 20) -> list[AnalysisSummary]:
    with Session(engine) as session:
        rows = session.exec(select(Analysis).order_by(Analysis.created_at.desc()).limit(limit)).all()
        return [
            AnalysisSummary(
                id=row.id or 0,
                query=row.query,
                ticker=row.ticker,
                recommendation=_normalize_recommendation(row.recommendation),
                confidence=row.confidence,
                risk_level=row.risk_level,
                status=row.status,
                created_at=row.created_at,
            )
            for row in rows
        ]


def get_analysis(analysis_id: int) -> AnalysisResponse | None:
    with Session(engine) as session:
        analysis = session.get(Analysis, analysis_id)
        if analysis is None:
            return None
        rows = session.exec(select(AgentOutputRow).where(AgentOutputRow.analysis_id == analysis_id)).all()

    by_agent = {row.agent_name: json.loads(row.output_json) for row in rows}
    final_payload = json.loads(analysis.final_json)
    if "recommendation" in final_payload:
        final_payload["recommendation"] = _normalize_recommendation(final_payload["recommendation"])
    final_payload.setdefault("technical_data_confidence", final_payload.get("confidence", 0.0))
    final_payload.setdefault("news_data_confidence", final_payload.get("confidence", 0.0))
    final_payload.setdefault("fundamental_data_confidence", final_payload.get("confidence", 0.0))
    final_payload.setdefault("final_trade_confidence", final_payload.get("confidence", 0.0))
    return AnalysisResponse(
        id=analysis.id or 0,
        query=analysis.query,
        ticker=analysis.ticker,
        status=analysis.status,
        final=FinalRecommendation.model_validate(final_payload),
        market_data=MarketDataOutput.model_validate(by_agent["Market Data Agent"]),
        news_sentiment=NewsSentimentOutput.model_validate(by_agent["News and Sentiment Agent"]),
        fundamentals=FundamentalEarningsOutput.model_validate(by_agent["Fundamental and Earnings Agent"]),
        critic=CriticOutput.model_validate(by_agent["Critic and Validation Agent"]),
        sources=[SourceReference.model_validate(item) for item in json.loads(analysis.sources_json)],
        metrics=json.loads(analysis.metrics_json),
        created_at=analysis.created_at,
    )
