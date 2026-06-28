from __future__ import annotations

from statistics import mean
from typing import Any

from langsmith import traceable

from .llm_provider import refine_final_with_groq
from .models import (
    DISCLAIMER,
    AgentIssue,
    ConfidenceAdjustment,
    ConfidenceLabel,
    CriticOutput,
    FinalRecommendation,
    FundamentalEarningsOutput,
    MarketDataOutput,
    NewsSentimentOutput,
    Recommendation,
)


def confidence_label(score: float) -> ConfidenceLabel:
    if score < 0.4:
        return ConfidenceLabel.low
    if score < 0.7:
        return ConfidenceLabel.moderate
    return ConfidenceLabel.high


DECISION_BY_SIGNAL_SCORE: dict[int, Recommendation] = {
    1: Recommendation.avoid,
    2: Recommendation.wait,
    3: Recommendation.neutral,
    4: Recommendation.buy_setup,
    5: Recommendation.strong_buy_setup,
}

HORIZON_WEIGHTS: dict[str, dict[str, float]] = {
    "intraday": {"technical": 0.60, "news": 0.30, "fundamental": 0.10},
    "swing": {"technical": 0.50, "news": 0.20, "fundamental": 0.30},
    "multi-week": {"technical": 0.35, "news": 0.25, "fundamental": 0.40},
    "long-term": {"technical": 0.20, "news": 0.20, "fundamental": 0.60},
}


def decision_for_signal_score(signal_score: int) -> Recommendation:
    return DECISION_BY_SIGNAL_SCORE[max(1, min(5, signal_score))]


def _signal_score_from_adjusted_score(adjusted_score: float) -> int:
    if adjusted_score <= -1.00:
        return 1
    if adjusted_score <= -0.25:
        return 2
    if adjusted_score <= 0.50:
        return 3
    if adjusted_score <= 1.25:
        return 4
    return 5


def _score_label(score: int) -> str:
    return {
        -2: "strongly_bearish",
        -1: "bearish",
        0: "neutral",
        1: "bullish",
        2: "strongly_bullish",
    }[max(-2, min(2, score))]


def _bounded_agent_score(value: int) -> int:
    return max(-2, min(2, value))


def _risk_profile_adjustment(
    risk_profile: str,
    market: MarketDataOutput,
    news: NewsSentimentOutput,
    fundamentals: FundamentalEarningsOutput,
    critic: CriticOutput,
) -> tuple[float, list[str]]:
    adjustment = 0.0
    reasons: list[str] = []
    signals = [market.numeric_score, news.numeric_score, fundamentals.numeric_score]
    conflict = max(signals) > 0 and min(signals) < 0
    valuation_risk = fundamentals.valuation_assessment == "expensive" or any("valuation" in flag.lower() for flag in fundamentals.risk_flags)
    technical_missing = market.numeric_score <= 0
    source_weak = news.source_quality == "low" or any(issue.type == "source_mismatch" for issue in critic.issues)

    if risk_profile == "conservative":
        if conflict:
            adjustment -= 0.20
            reasons.append("conservative profile penalized conflicting signals")
        if valuation_risk:
            adjustment -= 0.20
            reasons.append("conservative profile penalized elevated valuation risk")
        if technical_missing:
            adjustment -= 0.20
            reasons.append("conservative profile penalized missing technical confirmation")
        if critic.reliability == "pass_with_cautions":
            adjustment -= 0.15
            reasons.append("conservative profile penalized critic cautions")
    elif risk_profile == "aggressive":
        if sum(score > 0 for score in signals) >= 2 and critic.reliability == "pass" and not source_weak and not valuation_risk:
            adjustment += 0.10
            reasons.append("aggressive profile allowed a small upgrade for aligned positive evidence")
    else:
        reasons.append("moderate/unknown profile used base score unless critic adjusted it")

    return adjustment, reasons


def _critic_adjustment(critic: CriticOutput) -> tuple[float, float]:
    if critic.reliability == "fail":
        return -99.0, 0.60
    if critic.reliability == "pass_with_cautions":
        return -0.15, 0.15
    return 0.0, 0.0


def _weighted_decision(
    market: MarketDataOutput,
    news: NewsSentimentOutput,
    fundamentals: FundamentalEarningsOutput,
    critic: CriticOutput,
    time_horizon: str,
    risk_profile: str,
    horizon_source: str,
    risk_profile_source: str,
) -> dict[str, Any]:
    weights = HORIZON_WEIGHTS.get(time_horizon, HORIZON_WEIGHTS["swing"])
    weighted_score = (
        market.numeric_score * weights["technical"]
        + news.numeric_score * weights["news"]
        + fundamentals.numeric_score * weights["fundamental"]
    )
    risk_adjustment, risk_reasons = _risk_profile_adjustment(risk_profile, market, news, fundamentals, critic)
    critic_score_penalty, critic_confidence_penalty = _critic_adjustment(critic)
    adjusted_score = weighted_score + risk_adjustment + critic_score_penalty
    signal_score = _signal_score_from_adjusted_score(adjusted_score)
    if any("fixture" in ref for output in [market, news, fundamentals] for ref in output.evidence_references):
        signal_score = min(signal_score, 2)
    if news.missing_data or fundamentals.missing_data:
        signal_score = min(signal_score, 3)
    if risk_profile == "unknown" and signal_score == 5 and not all(output.numeric_score > 0 for output in [market, news, fundamentals]):
        signal_score = 4
    if risk_profile == "aggressive" and signal_score == 5 and (news.source_quality == "low" or fundamentals.valuation_assessment == "expensive"):
        signal_score = 4
    return {
        "technical": market.numeric_score,
        "fundamental": fundamentals.numeric_score,
        "news": news.numeric_score,
        "weights": weights,
        "weighted_score": round(weighted_score, 3),
        "risk_adjustment": round(risk_adjustment, 3),
        "critic_score_penalty": critic_score_penalty,
        "critic_confidence_penalty": critic_confidence_penalty,
        "adjusted_score": round(adjusted_score, 3),
        "signal_score": signal_score,
        "technical_reasons": market.findings or market.key_findings,
        "fundamental_reasons": fundamentals.findings or fundamentals.key_findings,
        "news_reasons": news.findings or news.key_findings,
        "risk_adjustment_reasons": risk_reasons,
        "horizon_source": horizon_source,
        "risk_profile_source": risk_profile_source,
    }


def _trade_framing(market: MarketDataOutput) -> tuple[str, str]:
    support = market.support_levels[-1] if market.support_levels else None
    resistance = market.resistance_levels[0] if market.resistance_levels else None
    near_term: list[str] = []
    if market.ma_20:
        near_term.append(f"reclaim MA20 around {market.ma_20}")
    if market.ma_50:
        near_term.append(f"hold or reclaim MA50 around {market.ma_50}")

    if support and resistance and near_term:
        entry = (
            f"For a swing horizon, near-term confirmation would be to {' and '.join(near_term)} with stronger volume. "
            f"Major breakout sits near {resistance}; deeper support is around {support}."
        )
    elif support and resistance:
        entry = f"For a swing horizon, consider waiting near support around {support} or for a confirmed breakout above resistance around {resistance}."
    elif support and near_term:
        entry = f"For a swing horizon, near-term confirmation would be to {' and '.join(near_term)}; deeper support is around {support}."
    elif support:
        entry = f"For a swing horizon, consider waiting for price to hold support around {support} before considering a new entry."
    elif resistance:
        entry = f"For a swing horizon, consider waiting for a confirmed breakout above resistance around {resistance}; avoid chasing below it."
    else:
        entry = "For a swing horizon, consider waiting until clear support or resistance levels are available."

    invalidation_reference = market.ma_50 or support
    stop_reference = invalidation_reference * 0.985 if invalidation_reference else None
    if stop_reference and market.ma_50:
        stop = f"If entry is based on reclaiming MA20/MA50, one invalidation area is back below MA50 around {round(stop_reference, 2)}."
    elif stop_reference:
        stop = f"One possible invalidation area is below support, around {round(stop_reference, 2)}, adjusted for position size and volatility."
    else:
        stop = "Use a predefined invalidation level; stop-loss framing is limited because support data is missing."
    return entry, stop


def _recommendation_from_signals(
    market: MarketDataOutput,
    news: NewsSentimentOutput,
    fundamentals: FundamentalEarningsOutput,
    critic: CriticOutput,
) -> tuple[Recommendation, str, str, int]:
    scoring = _score_trade_setup(market, news, fundamentals, critic)
    signal_score = scoring["signal_score"]
    recommendation = decision_for_signal_score(signal_score)
    risk = _risk_for_signal_score(signal_score, market, fundamentals)
    return recommendation, f"Deterministic signal score is {signal_score}/5 from component evidence.", risk, signal_score


def _display_signal_score(raw_score: int) -> int:
    return max(1, min(5, raw_score))


def _trade_confidence(signal_score: int, critic: CriticOutput, market: MarketDataOutput, news: NewsSentimentOutput) -> float:
    confidence = 0.26 + (signal_score * 0.08)
    if critic.issues:
        confidence -= 0.08
    if critic.contradictions:
        confidence -= 0.05
    if market.trend in {"mixed", "bearish"}:
        confidence -= 0.05
    if news.priced_in_assessment in {"possible", "likely"}:
        confidence -= 0.03
    return round(max(0.25, min(confidence, 0.78)), 2)


def _trade_confidence_from_decision(
    decision_data: dict[str, Any],
    market: MarketDataOutput,
    news: NewsSentimentOutput,
    fundamentals: FundamentalEarningsOutput,
    critic: CriticOutput,
) -> float:
    confidence = 50.0 + abs(float(decision_data["adjusted_score"])) * 12.0
    signals = [market.numeric_score, news.numeric_score, fundamentals.numeric_score]
    if all(score > 0 for score in signals) or all(score < 0 for score in signals):
        confidence += 10
    if max(signals) > 0 and min(signals) < 0:
        confidence -= 15
    if market.numeric_score <= 0:
        confidence -= 8
    if fundamentals.valuation_assessment == "expensive":
        confidence -= 8
    if news.priced_in_assessment in {"possible", "likely"}:
        confidence -= 6
    confidence -= float(decision_data.get("critic_confidence_penalty", 0)) * 100
    if decision_data.get("horizon_source") == "defaulted":
        confidence -= 5
    if decision_data.get("risk_profile_source") == "defaulted":
        confidence -= 5
    return round(max(15, min(confidence, 90)) / 100, 2)


def _decision_rule_text(recommendation: Recommendation) -> str:
    if recommendation == Recommendation.needs_review:
        return "Needs review is used when critic validation fails or reliable data is insufficient."
    if recommendation == Recommendation.strong_buy_setup:
        return "Strong buy setup requires broad technical confirmation, supportive fundamentals/news, and manageable critic cautions."
    if recommendation == Recommendation.buy_setup:
        return "Buy setup requires mostly positive evidence and clear near-term confirmation levels."
    if recommendation == Recommendation.neutral:
        return "Neutral / Watchlist means evidence is balanced enough to monitor, but not strong enough for a high-conviction setup."
    if recommendation == Recommendation.wait:
        return "Wait is used when technical confirmation is missing, signals conflict, valuation risk is elevated, or data quality cautions remain."
    return "Avoid is used when the evidence leans materially negative or the setup has poor confirmation."


def _confidence_explanation(
    market: MarketDataOutput,
    news: NewsSentimentOutput,
    fundamentals: FundamentalEarningsOutput,
    critic: CriticOutput,
) -> str:
    parts = [
        f"Technical Agent data confidence is {round(market.confidence * 100)}%.",
        f"News Agent data confidence is {round(news.confidence * 100)}%.",
        f"Fundamental Agent data confidence is {round(fundamentals.confidence * 100)}%.",
    ]
    if market.trend in {"mixed", "bearish"}:
        parts.append("Final trade confidence is lower because the swing setup lacks clean technical confirmation.")
    if critic.issues:
        parts.append("Critic cautions further reduce decision confidence.")
    if news.priced_in_assessment in {"possible", "likely"}:
        parts.append("News may already be partly priced in.")
    return " ".join(parts)


def _risk_for_signal_score(signal_score: int, market: MarketDataOutput, fundamentals: FundamentalEarningsOutput) -> str:
    if signal_score <= 2 or market.volatility_assessment == "high":
        return "high"
    if signal_score >= 4 and fundamentals.valuation_assessment != "expensive":
        return "low"
    return "moderate"


def _risk_from_decision_data(
    signal_score: int,
    risk_profile: str,
    market: MarketDataOutput,
    news: NewsSentimentOutput,
    fundamentals: FundamentalEarningsOutput,
    critic: CriticOutput,
) -> str:
    risk_points = 0
    if market.volatility_assessment == "high":
        risk_points += 1
    if market.numeric_score < 0:
        risk_points += 1
    if fundamentals.valuation_assessment == "expensive":
        risk_points += 1
    if news.risk_flags or news.source_quality == "low":
        risk_points += 1
    if critic.reliability == "pass_with_cautions":
        risk_points += 1
    if risk_profile == "conservative" and signal_score < 4:
        risk_points += 1
    if signal_score <= 2:
        risk_points += 1
    if risk_points >= 3:
        return "high"
    if risk_points >= 1:
        return "moderate"
    return "low"


def validate_final_decision_consistency(final: FinalRecommendation) -> list[AgentIssue]:
    if final.recommendation == Recommendation.needs_review:
        return []
    signal_score = int(final.critic_review.get("signal_score", 0) or 0)
    expected = decision_for_signal_score(signal_score)
    if final.recommendation != expected:
        return [
            AgentIssue(
                severity="critical",
                type="decision_score_mismatch",
                description=f"Decision {final.recommendation.value} does not match signal score {signal_score}/5.",
                affected_agent="Final Response Agent",
                required_fix=f"Use decision {expected.value} for signal score {signal_score}/5.",
            )
        ]
    return []


def _summary_from_components(
    ticker: str,
    recommendation: Recommendation,
    signal_score: int,
    trade_confidence: float,
    scoring: dict[str, Any],
    market: MarketDataOutput,
    news: NewsSentimentOutput,
    fundamentals: FundamentalEarningsOutput,
) -> str:
    technical = "; ".join(scoring["technical_reasons"][:3]) or market.summary
    news_text = "; ".join(scoring["news_reasons"][:2]) or news.summary
    fundamental = "; ".join(scoring["fundamental_reasons"][:3]) or fundamentals.summary
    return (
        f"{ticker}: {recommendation.value}. Signal score is {signal_score}/5 with "
        f"{round(trade_confidence * 100)}% trade confidence. "
        f"Technicals: {technical}. News: {news_text}. Fundamentals: {fundamental}."
    )


def _technical_confidence(market: dict[str, Any], missing_data: list[str], volatility: str) -> float:
    if market.get("data_source") != "yfinance":
        return 0.48
    score = 0.52
    available = ["ma_20", "ma_50", "ma_200", "rsi", "atr_percent"]
    score += 0.04 * sum(1 for key in available if market.get(key) is not None)
    if market.get("macd_direction") != "unknown":
        score += 0.04
    if market.get("support_levels") and market.get("resistance_levels"):
        score += 0.06
    if volatility == "high":
        score -= 0.06
    score -= min(len(missing_data) * 0.03, 0.12)
    return round(max(0.35, min(score, 0.82)), 2)


def _market_numeric_score(market: dict[str, Any], horizon: str) -> int:
    score = 0
    current = market.get("current_price")
    if current is not None and market.get("ma_20") is not None and current > market["ma_20"]:
        score += 1
    if horizon in {"swing", "multi-week", "intraday"} and current is not None and market.get("ma_50") is not None and current > market["ma_50"]:
        score += 1
    if horizon in {"multi-week", "long-term"} and current is not None and market.get("ma_200") is not None and current > market["ma_200"]:
        score += 1
    if market.get("macd_direction") == "positive":
        score += 1
    elif market.get("macd_direction") == "negative":
        score -= 1
    if market.get("rsi") is not None and 50 <= market["rsi"] <= 70:
        score += 1
    if market.get("relative_volume") is not None and market["relative_volume"] >= 1.2:
        score += 1
    if current is not None and market.get("ma_20") is not None and current < market["ma_20"] and market.get("macd_direction") == "negative":
        score -= 1
    return _bounded_agent_score(score)


@traceable(name="market_data_agent")
def run_market_data_agent(snapshot: dict[str, Any]) -> MarketDataOutput:
    ticker = snapshot.get("ticker", "The stock")
    horizon = snapshot.get("time_horizon", "swing")
    market = snapshot["market"]
    key_signals: list[str] = []
    risk_flags: list[str] = []

    current = float(market["current_price"])
    missing_data = list(snapshot.get("market_missing_data", []))
    data_source = market.get("data_source", "fixture")
    ma_values_available = all(market.get(key) is not None for key in ["ma_20", "ma_50", "ma_200"])
    if ma_values_available and current > market["ma_20"] > market["ma_50"] > market["ma_200"]:
        trend = "bullish"
        key_signals.append("Price is above the 20-day, 50-day, and 200-day moving averages.")
    elif ma_values_available and current < market["ma_20"] < market["ma_50"]:
        trend = "bearish"
        key_signals.append("Price is below the 20-day and 50-day moving averages, showing weak short-term trend.")
    elif all(market.get(key) is not None for key in ["ma_20", "ma_50"]) and current > market["ma_20"] > market["ma_50"]:
        trend = "bullish"
        key_signals.append("Price is above the 20-day and 50-day moving averages; 200-day data is unavailable.")
    elif all(market.get(key) is not None for key in ["ma_20", "ma_50"]) and current < market["ma_20"] < market["ma_50"]:
        trend = "bearish"
        key_signals.append("Price is below the 20-day and 50-day moving averages.")
    else:
        trend = "mixed"
        key_signals.append("Moving-average alignment is not fully bullish.")

    if market.get("rsi") is None:
        missing_data.append("RSI was not calculated because candle history is insufficient")
    elif market["rsi"] >= 70:
        risk_flags.append(f"RSI is near or above overbought territory at {market['rsi']}.")
    elif market["rsi"] >= 65:
        risk_flags.append(f"RSI is elevated at {market['rsi']}, so chasing momentum may carry reversal risk.")
    elif market["rsi"] <= 35:
        risk_flags.append(f"RSI is weak at {market['rsi']}, so momentum has not confirmed a bullish turn.")
    else:
        key_signals.append(f"RSI is {market['rsi']}, which is not at an extreme.")

    if market.get("ma_20") is not None and current < market["ma_20"]:
        risk_flags.append("Price has not reclaimed MA20.")

    if market["relative_volume"] >= 1.5:
        key_signals.append(f"Relative volume is {market['relative_volume']}x average, showing active participation.")
    else:
        key_signals.append(f"Relative volume is {market['relative_volume']}x average.")
        if market["relative_volume"] < 1.0:
            risk_flags.append("Relative volume is below average.")

    if market.get("atr_percent") is None:
        missing_data.append("ATR volatility was not calculated because candle history is insufficient")
        volatility = "unknown"
    elif market["atr_percent"] >= 4:
        risk_flags.append("Volatility is high relative to normal daily movement.")
        volatility = "high"
    elif market["atr_percent"] <= 2:
        volatility = "low"
        key_signals.append(f"ATR is about {market['atr_percent']}% of price, suggesting calmer daily movement.")
    else:
        volatility = "moderate"
        key_signals.append(f"ATR is about {market['atr_percent']}% of price, suggesting moderate volatility.")

    if market.get("macd_direction") != "unknown":
        key_signals.append(f"MACD momentum is {market['macd_direction']}.")
        if market.get("macd_direction") == "negative":
            risk_flags.append("MACD momentum is negative.")

    if market["recent_gaps"]:
        risk_flags.append("Recent earnings gap may create gap-fill risk.")
    if trend in {"mixed", "bearish"} and horizon == "long-term":
        risk_flags.append("Short-term entry timing lacks confirmation.")
    elif trend in {"mixed", "bearish"}:
        risk_flags.append("Swing setup lacks breakout confirmation.")

    support_text = ", ".join(str(level) for level in market["support_levels"]) or "not available"
    resistance_text = ", ".join(str(level) for level in market["resistance_levels"]) or "not available"
    indicator_bits = [
        f"last close {current}",
        f"RSI {market.get('rsi') if market.get('rsi') is not None else 'unknown'}",
        f"MA20 {market.get('ma_20') if market.get('ma_20') is not None else 'unknown'}",
        f"MA50 {market.get('ma_50') if market.get('ma_50') is not None else 'unknown'}",
        f"MA200 {market.get('ma_200') if market.get('ma_200') is not None else 'unknown'}",
    ]
    summary = (
        f"{ticker} technicals are {trend}: "
        f"{', '.join(indicator_bits)}. "
        f"Support: {support_text}. Resistance: {resistance_text}."
    )
    confidence = _technical_confidence(market, missing_data, volatility)
    numeric_score = _market_numeric_score(market, horizon)

    return MarketDataOutput(
        agent="Market Data Agent",
        agent_name="Market Data Agent",
        summary=summary,
        numeric_score=numeric_score,
        label=_score_label(numeric_score),
        data_confidence=confidence,
        trend=trend,
        key_findings=key_signals,
        findings=key_signals,
        key_signals=key_signals,
        risk_flags=risk_flags,
        support_levels=market["support_levels"],
        resistance_levels=market["resistance_levels"],
        volatility_assessment=volatility,
        recent_gaps=market["recent_gaps"],
        current_price=market.get("current_price"),
        ma_20=market.get("ma_20"),
        ma_50=market.get("ma_50"),
        ma_200=market.get("ma_200"),
        rsi=market.get("rsi"),
        macd_direction=market.get("macd_direction", "unknown"),
        relative_volume=market.get("relative_volume"),
        atr_percent=market.get("atr_percent"),
        last_candle_date=market.get("last_candle_date"),
        missing_data=missing_data,
        source_quality="moderate" if data_source == "yfinance" else "low",
        evidence_references=[f"{data_source}-market-data"],
        evidence=[f"last close {current}", f"horizon {horizon}", f"source {data_source}"],
        confidence=confidence,
        assumptions=["Market data source is the configured candle provider."],
    )


@traceable(name="news_sentiment_agent")
def run_news_sentiment_agent(snapshot: dict[str, Any]) -> NewsSentimentOutput:
    news = snapshot["news"]
    data_source = news.get("data_source", "fixture")
    score = float(news["sentiment_score"])
    sentiment = "positive" if score >= 0.6 else "negative" if score <= 0.4 else "mixed"
    risk_flags = []

    if news["hype_risk"] == "high":
        risk_flags.append("High social and headline enthusiasm may create hype risk.")
    if news["priced_in"] in {"possible", "likely"}:
        risk_flags.append("Some good news may already be reflected in the post-earnings price move.")

    missing_data = list(snapshot.get("tavily_missing_data", []))
    if data_source not in {"tavily", "groq_news"}:
        missing_data.extend(["Live headline feed", "Verified analyst upgrade/downgrade feed"])
    numeric_score = 0
    if sentiment == "positive":
        numeric_score += 1
    elif sentiment == "negative":
        numeric_score -= 1
    if news["priced_in"] in {"possible", "likely"}:
        numeric_score -= 1
    if missing_data:
        numeric_score -= 1
    numeric_score = _bounded_agent_score(numeric_score)
    source_quality = "low" if missing_data else "moderate"
    return NewsSentimentOutput(
        agent="News and Sentiment Agent",
        agent_name="News and Sentiment Agent",
        summary=news.get("summary") or "News tone is mixed and should be read with source-quality cautions.",
        numeric_score=numeric_score,
        label=_score_label(numeric_score),
        data_confidence=0.68 if data_source == "groq_news" else 0.66 if data_source == "tavily" else 0.61,
        sentiment=sentiment,
        key_findings=news["headlines"],
        findings=news["headlines"],
        factual_news=news.get("factual_news") or news["headlines"],
        speculation=news["speculation"],
        analyst_actions=news["analyst_actions"],
        sector_and_macro_context=news["sector_macro"],
        hype_risk=news["hype_risk"],
        priced_in_assessment=news["priced_in"],
        risk_flags=risk_flags,
        missing_data=missing_data,
        source_quality=source_quality,
        evidence_references=[f"{data_source}-news-data"],
        evidence=list(news.get("factual_news") or news["headlines"])[:5],
        confidence=0.68 if data_source == "groq_news" else 0.66 if data_source == "tavily" else 0.61,
        assumptions=["News and sentiment source is the configured web/news provider."],
    )


@traceable(name="fundamental_earnings_agent")
def run_fundamental_earnings_agent(snapshot: dict[str, Any]) -> FundamentalEarningsOutput:
    fundamentals = snapshot["fundamentals"]
    data_source = fundamentals.get("data_source", "fixture")
    risk_flags = []
    structured_available = bool(fundamentals.get("structured_fundamentals_available", data_source == "fixture"))
    if structured_available and fundamentals["valuation"] == "expensive":
        risk_flags.append("Valuation risk is elevated and depends on continued strong growth.")
    elif not structured_available:
        risk_flags.append("Structured fundamentals are not connected yet, so earnings and valuation claims are limited.")

    if structured_available:
        metrics = fundamentals.get("metrics") or {}
        eps = metrics.get("eps")
        pe_ratio = metrics.get("pe_ratio")
        de_ratio = metrics.get("de_ratio")
        fcf = metrics.get("fcf")
        roe = metrics.get("roe")
        key_findings = [
            f"EPS: {eps if eps is not None else 'unknown'}",
            f"P/E ratio: {pe_ratio if pe_ratio is not None else 'unknown'}",
            f"D/E ratio: {de_ratio if de_ratio is not None else 'unknown'}",
            f"FCF: {fcf if fcf is not None else 'unknown'}",
            f"ROE: {roe if roe is not None else 'unknown'}",
        ]
        earnings_summary = {
            "eps": eps,
            "pe_ratio": pe_ratio,
        }
        quality_indicators = {
            "de_ratio": de_ratio,
            "fcf": fcf,
            "roe": roe,
        }
        valuation = "unknown" if pe_ratio is None else "expensive" if pe_ratio > 30 else "fair" if pe_ratio >= 15 else "cheap"
        positives = sum(
            [
                eps is not None and eps > 0,
                fcf is not None and fcf > 0,
                roe is not None and roe > 0.12,
                pe_ratio is not None and pe_ratio <= 30,
                de_ratio is not None and de_ratio <= 150,
            ]
        )
        negatives = sum(
            [
                eps is not None and eps <= 0,
                fcf is not None and fcf <= 0,
                roe is not None and roe < 0.05,
                pe_ratio is not None and pe_ratio > 30,
                de_ratio is not None and de_ratio > 150,
            ]
        )
        if de_ratio is not None and de_ratio > 150:
            risk_flags.append("Debt-to-equity is elevated on the yfinance snapshot.")
        if pe_ratio is not None and pe_ratio > 30:
            risk_flags.append("P/E is elevated, so valuation depends on continued strong growth.")
        if fcf is not None and fcf <= 0:
            risk_flags.append("Free cash flow is negative in the available yfinance snapshot.")
        if positives >= 4 and negatives == 0:
            view = "supportive"
        elif negatives >= 2:
            view = "unsupportive"
        else:
            view = "mixed"
        if positives >= 4 and valuation != "expensive" and negatives == 0:
            numeric_score = 2
        elif positives >= 3 and negatives <= 2:
            numeric_score = 1
        elif negatives >= 3:
            numeric_score = -2
        elif negatives >= 2:
            numeric_score = -1
        else:
            numeric_score = 0
        if valuation == "expensive" and view == "supportive":
            summary = "Five-metric fundamentals are supportive, but valuation remains dependent on continued high growth."
        else:
            valuation_text = "valuation risk is elevated" if valuation == "expensive" else f"{valuation} valuation read"
            summary = f"Five-metric fundamental view is {view}: EPS, cash flow, leverage, valuation, and ROE give {valuation_text}."
        confidence = round(0.48 + 0.04 * sum(value is not None for value in [eps, pe_ratio, de_ratio, fcf, roe]), 2)
    else:
        key_findings = [
            "Web context is available, but exact revenue, EPS, margin, cash-flow, debt, and valuation fields are not from a structured fundamentals API.",
        ]
        earnings_summary = {
            "revenue_growth": "unknown",
            "eps_surprise": "unknown",
            "guidance": "unknown",
        }
        quality_indicators = {
            "margins": "unknown",
            "free_cash_flow": "unknown",
            "debt_risk": "unknown",
        }
        valuation = "unknown"
        summary = "Structured fundamentals are not available yet; only web context is available."
        view = "unknown"
        confidence = 0.4
        numeric_score = 0

    return FundamentalEarningsOutput(
        agent="Fundamental and Earnings Agent",
        agent_name="Fundamental and Earnings Agent",
        summary=summary,
        numeric_score=numeric_score,
        label=_score_label(numeric_score),
        data_confidence=confidence,
        fundamental_view=view,
        key_findings=key_findings,
        findings=key_findings,
        earnings_summary=earnings_summary,
        quality_indicators=quality_indicators,
        valuation_assessment=valuation,
        segment_growth_notes=fundamentals["segments"],
        management_commentary=fundamentals["management"],
        risk_flags=risk_flags,
        missing_data=list(snapshot.get("fundamentals_missing_data", [])),
        source_quality="moderate" if structured_available else "low",
        evidence_references=[f"{data_source}-fundamentals-data"],
        evidence=key_findings,
        confidence=confidence,
        assumptions=["Fundamental view is based only on EPS, P/E, D/E, FCF, and ROE from the configured snapshot source."],
    )


@traceable(name="critic_validation_agent")
def run_critic_agent(
    market: MarketDataOutput,
    news: NewsSentimentOutput,
    fundamentals: FundamentalEarningsOutput,
) -> CriticOutput:
    issues: list[AgentIssue] = []
    missing_evidence: list[str] = []
    contradictions: list[str] = []

    for output in [market, news, fundamentals]:
        if output.confidence > 0.7 and output.missing_data:
            issues.append(
                AgentIssue(
                    severity="medium",
                    type="overconfidence",
                    description=f"{output.agent} confidence is high despite missing data.",
                    affected_agent=output.agent,
                    required_fix="Reduce confidence or obtain the missing data.",
                )
            )

    if any("Excluded" in item or "No search results" in item for item in news.missing_data):
        issues.append(
            AgentIssue(
                severity="high",
                type="source_mismatch",
                description="Some search results did not clearly match the requested ticker and were excluded.",
                affected_agent=news.agent,
                required_fix="Use stricter ticker/company filters or better source queries before trusting sentiment.",
            )
        )

    if market.volatility_assessment == "high" and fundamentals.fundamental_view == "supportive":
        contradictions.append("Strong fundamentals conflict with elevated short-term technical volatility.")
    if fundamentals.valuation_assessment == "fair" and any("valuation" in flag.lower() and "elevated" in flag.lower() for flag in fundamentals.risk_flags):
        issues.append(
            AgentIssue(
                severity="high",
                type="contradiction",
                description="Valuation cannot be described as fair while valuation risk is flagged as elevated.",
                affected_agent=fundamentals.agent,
                required_fix="Use valuation-sensitive wording instead of fair valuation wording.",
            )
        )

    for output in [market, news, fundamentals]:
        if not output.evidence_references:
            missing_evidence.append(output.agent)
            issues.append(
                AgentIssue(
                    severity="high",
                    type="missing_data",
                    description=f"{output.agent} has no evidence references.",
                    affected_agent=output.agent,
                    required_fix="Attach source references before generating the final answer.",
                )
            )

    has_fixture_any = any("fixture" in ref for output in [market, news, fundamentals] for ref in output.evidence_references)
    if has_fixture_any:
        issues.append(
            AgentIssue(
                severity="medium",
                type="missing_data",
                description="At least one agent is using fixture data rather than live sources.",
                required_fix="Connect live adapters before treating the result as current market research.",
            )
        )
    if any("yfinance" in ref for ref in market.evidence_references) and market.missing_data:
        issues.append(
            AgentIssue(
                severity="medium",
                type="missing_data",
                description="Market candles were available, but some technical indicators could not be calculated.",
                affected_agent=market.agent,
                required_fix="Fetch a longer period or avoid claims about missing indicators.",
            )
        )

    base_confidence = mean([market.confidence, news.confidence, fundamentals.confidence])
    adjusted = min(base_confidence, 0.58 if issues else base_confidence)
    if any(issue.severity == "critical" for issue in issues):
        reliability = "fail"
    elif issues or contradictions:
        reliability = "pass_with_cautions"
    else:
        reliability = "pass"

    return CriticOutput(
        reliability=reliability,
        show_to_user=reliability != "fail",
        issues=issues,
        confidence_adjustments=[
            ConfidenceAdjustment(
                target="final_recommendation",
                original_confidence=round(base_confidence, 2),
                adjusted_confidence=round(adjusted, 2),
                reason="Trade confidence is capped when data quality, volatility, or source matching limits reliability.",
            )
        ],
        contradictions=contradictions,
        missing_evidence=missing_evidence,
        final_notes=["Output is suitable for MVP demonstration, not live trading decisions."],
        required_fixes=[issue.required_fix for issue in issues if issue.required_fix],
        confidence_penalty=0.15 if reliability == "pass_with_cautions" else 0.6 if reliability == "fail" else 0.0,
        score_penalty=0.15 if reliability == "pass_with_cautions" else 99.0 if reliability == "fail" else 0.0,
        can_publish=reliability != "fail",
    )


@traceable(name="final_response_agent")
def run_final_response_agent(
    request_context: dict[str, Any],
    market: MarketDataOutput,
    news: NewsSentimentOutput,
    fundamentals: FundamentalEarningsOutput,
    critic: CriticOutput,
) -> FinalRecommendation:
    ticker = request_context.get("ticker", "The stock")
    time_horizon = request_context.get("time_horizon", "swing")
    risk_profile = request_context.get("risk_profile", "unknown")
    horizon_source = request_context.get("horizon_source", "provided")
    risk_profile_source = request_context.get("risk_profile_source", "provided")

    scoring = _weighted_decision(
        market,
        news,
        fundamentals,
        critic,
        time_horizon,
        risk_profile,
        horizon_source,
        risk_profile_source,
    )
    display_signal_score = scoring["signal_score"]
    if critic.reliability == "fail":
        recommendation = Recommendation.needs_review
        risk_level = "high"
        trade_confidence = 0.15
    else:
        recommendation = decision_for_signal_score(display_signal_score)
        risk_level = _risk_from_decision_data(display_signal_score, risk_profile, market, news, fundamentals, critic)
        trade_confidence = _trade_confidence_from_decision(scoring, market, news, fundamentals, critic)
    confidence_explanation = _confidence_explanation(market, news, fundamentals, critic)
    summary = _summary_from_components(
        ticker=ticker,
        recommendation=recommendation,
        signal_score=display_signal_score,
        trade_confidence=trade_confidence,
        scoring=scoring,
        market=market,
        news=news,
        fundamentals=fundamentals,
    )

    missing_data = sorted(set(market.missing_data + news.missing_data + fundamentals.missing_data))
    key_risks = sorted(set(market.risk_flags + news.risk_flags + fundamentals.risk_flags))
    entry_idea, stop_loss_idea = _trade_framing(market)

    baseline = FinalRecommendation(
        recommendation=recommendation,
        confidence=trade_confidence,
        confidence_label=confidence_label(trade_confidence),
        technical_data_confidence=market.confidence,
        news_data_confidence=news.confidence,
        fundamental_data_confidence=fundamentals.confidence,
        final_trade_confidence=trade_confidence,
        time_horizon=time_horizon,
        risk_level=risk_level,
        summary=summary,
        reasoning={
            "technical": market.summary,
            "news_sentiment": news.summary,
            "fundamentals_earnings": fundamentals.summary,
            "critic": f"{critic.reliability}: {critic.issues[0].description if critic.issues else 'No critical validation issues.'}",
            "decision_rule": _decision_rule_text(recommendation),
            "confidence": confidence_explanation,
        },
        entry_idea=entry_idea,
        stop_loss_idea=stop_loss_idea,
        key_risks=key_risks,
        missing_data=missing_data,
        critic_review={
            "reliability": critic.reliability,
            "main_cautions": [issue.description for issue in critic.issues],
            "contradictions": critic.contradictions,
            "checks": [
                "Checked that final conclusion is supported by technical, news, and fundamental agents.",
                "Checked for unsupported claims, missing evidence, contradictions, and overconfidence.",
                "Adjusted trade confidence when signals were mixed or source quality was limited.",
            ],
            "signal_score": display_signal_score,
            "signal_score_scale": "1 = Avoid / No trade, 2 = Wait, 3 = Neutral / Watchlist, 4 = Buy setup, 5 = Strong buy setup",
            "component_scores": {
                "technical": scoring["technical"],
                "fundamental": scoring["fundamental"],
                "news": scoring["news"],
                "weighted_score": scoring["weighted_score"],
                "adjusted_score": scoring["adjusted_score"],
                "risk_adjustment": scoring["risk_adjustment"],
                "critic_score_penalty": scoring["critic_score_penalty"],
            },
            "weights": scoring["weights"],
            "risk_profile": risk_profile,
            "horizon_source": horizon_source,
            "risk_profile_source": risk_profile_source,
            "trade_confidence_explanation": confidence_explanation,
        },
        disclaimer=DISCLAIMER,
    )
    try:
        refined = refine_final_with_groq(
            baseline=baseline,
            market=market.model_dump(mode="json"),
            news=news.model_dump(mode="json"),
            fundamentals=fundamentals.model_dump(mode="json"),
            critic=critic.model_dump(mode="json"),
        )
        # The LLM may polish wording, but deterministic trade fields stay locked.
        refined.recommendation = baseline.recommendation
        refined.confidence = baseline.confidence
        refined.confidence_label = baseline.confidence_label
        refined.technical_data_confidence = baseline.technical_data_confidence
        refined.news_data_confidence = baseline.news_data_confidence
        refined.fundamental_data_confidence = baseline.fundamental_data_confidence
        refined.final_trade_confidence = baseline.final_trade_confidence
        refined.risk_level = baseline.risk_level
        refined.critic_review = baseline.critic_review
        return refined
    except Exception as exc:
        baseline.critic_review["main_cautions"] = [
            *baseline.critic_review.get("main_cautions", []),
            f"Groq reasoning layer unavailable; deterministic final response used: {exc}",
        ]
        return baseline
