from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


DISCLAIMER = "This is not financial advice. It is for research and decision support only."


class Recommendation(str, Enum):
    avoid = "Avoid / No trade"
    wait = "Wait"
    neutral = "Neutral / Watchlist"
    buy_setup = "Buy setup"
    strong_buy_setup = "Strong buy setup"
    needs_review = "Needs review / insufficient reliable data"


class ConfidenceLabel(str, Enum):
    low = "Low"
    moderate = "Moderate"
    high = "High"


class AnalyzeRequest(BaseModel):
    query: str = Field(..., min_length=3)
    ticker: str = Field(..., min_length=1, max_length=12)
    event_context: str = "post_earnings"
    time_horizon: str = "swing"
    risk_profile: str = "unknown"
    horizon_source: str = "provided"
    risk_profile_source: str = "provided"

    @model_validator(mode="before")
    @classmethod
    def mark_defaulted_context(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        copied = dict(data)
        if not copied.get("time_horizon"):
            copied["time_horizon"] = "swing"
            copied["horizon_source"] = "defaulted"
        if not copied.get("risk_profile"):
            copied["risk_profile"] = "unknown"
            copied["risk_profile_source"] = "defaulted"
        return copied

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("time_horizon")
    @classmethod
    def normalize_time_horizon(cls, value: str) -> str:
        normalized = (value or "swing").strip().lower().replace("_", "-")
        aliases = {
            "day": "intraday",
            "short": "swing",
            "medium": "multi-week",
            "multiweek": "multi-week",
            "long": "long-term",
        }
        normalized = aliases.get(normalized, normalized)
        return normalized if normalized in {"intraday", "swing", "multi-week", "long-term"} else "swing"

    @field_validator("risk_profile")
    @classmethod
    def normalize_risk_profile(cls, value: str) -> str:
        normalized = (value or "unknown").strip().lower()
        return normalized if normalized in {"unknown", "conservative", "moderate", "aggressive"} else "unknown"


class SourceReference(BaseModel):
    source_type: str
    name: str
    url: str | None = None
    dataset_id: str | None = None
    timestamp: str | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reliability_tier: Literal["tier_1", "tier_2", "tier_3", "unknown"] = "unknown"


class AgentIssue(BaseModel):
    severity: Literal["low", "medium", "high", "critical"]
    type: str
    description: str
    affected_agent: str | None = None
    required_fix: str | None = None


class AgentOutput(BaseModel):
    agent: str
    agent_name: str | None = None
    summary: str
    numeric_score: int = Field(default=0, ge=-2, le=2)
    label: Literal["strongly_bearish", "bearish", "neutral", "bullish", "strongly_bullish"] = "neutral"
    data_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    key_findings: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    source_quality: Literal["high", "moderate", "low", "unknown"] = "unknown"
    evidence_references: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    assumptions: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MarketDataOutput(AgentOutput):
    trend: Literal["bullish", "bearish", "neutral", "mixed", "unknown"]
    key_signals: list[str] = Field(default_factory=list)
    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    volatility_assessment: Literal["low", "moderate", "high", "unknown"]
    recent_gaps: list[str] = Field(default_factory=list)
    current_price: float | None = None
    ma_20: float | None = None
    ma_50: float | None = None
    ma_200: float | None = None
    rsi: float | None = None
    macd_direction: str = "unknown"
    relative_volume: float | None = None
    atr_percent: float | None = None
    last_candle_date: str | None = None


class NewsSentimentOutput(AgentOutput):
    sentiment: Literal["positive", "negative", "neutral", "mixed", "unknown"]
    factual_news: list[str] = Field(default_factory=list)
    speculation: list[str] = Field(default_factory=list)
    analyst_actions: list[str] = Field(default_factory=list)
    sector_and_macro_context: list[str] = Field(default_factory=list)
    hype_risk: Literal["low", "moderate", "high", "unknown"]
    priced_in_assessment: Literal["unlikely", "possible", "likely", "unknown"]


class FundamentalEarningsOutput(AgentOutput):
    fundamental_view: Literal["supportive", "unsupportive", "mixed", "unknown"]
    earnings_summary: dict[str, Any] = Field(default_factory=dict)
    quality_indicators: dict[str, Any] = Field(default_factory=dict)
    valuation_assessment: Literal["cheap", "fair", "expensive", "unknown"]
    segment_growth_notes: list[str] = Field(default_factory=list)
    management_commentary: list[str] = Field(default_factory=list)


class ConfidenceAdjustment(BaseModel):
    target: str
    original_confidence: float = Field(..., ge=0.0, le=1.0)
    adjusted_confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str


class CriticOutput(BaseModel):
    agent: str = "Critic and Validation Agent"
    reliability: Literal["pass", "pass_with_cautions", "fail"]
    show_to_user: bool
    issues: list[AgentIssue] = Field(default_factory=list)
    confidence_adjustments: list[ConfidenceAdjustment] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    final_notes: list[str] = Field(default_factory=list)
    required_fixes: list[str] = Field(default_factory=list)
    confidence_penalty: float = 0.0
    score_penalty: float = 0.0
    can_publish: bool = True


class FinalRecommendation(BaseModel):
    recommendation: Recommendation
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_label: ConfidenceLabel
    technical_data_confidence: float = Field(..., ge=0.0, le=1.0)
    news_data_confidence: float = Field(..., ge=0.0, le=1.0)
    fundamental_data_confidence: float = Field(..., ge=0.0, le=1.0)
    final_trade_confidence: float = Field(..., ge=0.0, le=1.0)
    time_horizon: str
    risk_level: Literal["low", "moderate", "high", "unknown"]
    summary: str
    reasoning: dict[str, str]
    entry_idea: str
    stop_loss_idea: str
    key_risks: list[str]
    missing_data: list[str]
    critic_review: dict[str, Any]
    disclaimer: str = DISCLAIMER


class AnalysisResponse(BaseModel):
    id: int
    query: str
    ticker: str
    status: str
    final: FinalRecommendation
    market_data: MarketDataOutput
    news_sentiment: NewsSentimentOutput
    fundamentals: FundamentalEarningsOutput
    critic: CriticOutput
    sources: list[SourceReference]
    metrics: dict[str, Any]
    created_at: datetime


class AnalysisSummary(BaseModel):
    id: int
    query: str
    ticker: str
    recommendation: Recommendation
    confidence: float
    risk_level: str
    status: str
    created_at: datetime
