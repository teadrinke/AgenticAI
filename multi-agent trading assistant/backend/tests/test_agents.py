import app.graph as graph_module
from app.agents import HORIZON_WEIGHTS, _weighted_decision, decision_for_signal_score, run_critic_agent, run_final_response_agent, run_fundamental_earnings_agent, run_market_data_agent, validate_final_decision_consistency
from app.models import AnalyzeRequest, CriticOutput, DISCLAIMER, FinalRecommendation, FundamentalEarningsOutput, MarketDataOutput, NewsSentimentOutput, Recommendation


def test_full_graph_returns_wait_for_fixture_nvda(monkeypatch):
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
    request = AnalyzeRequest(query="Should I trade NVDA after earnings?", ticker="NVDA")
    state = graph_module.run_analysis_graph(request)

    assert state["final"].recommendation == Recommendation.wait
    assert state["final"].disclaimer == DISCLAIMER
    assert state["critic"].reliability == "pass_with_cautions"
    assert state["metrics"]["critic_issue_count"] >= 1
    assert state["metrics"]["data_mode"] == "fixture"


def test_ticker_is_normalized():
    request = AnalyzeRequest(query="Should I trade nvda after earnings?", ticker="nvda")
    assert request.ticker == "NVDA"


def test_supervisor_defaults_horizon_and_risk_profile():
    request = AnalyzeRequest(query="Should I trade NVDA after earnings?", ticker="NVDA", time_horizon="", risk_profile="")

    assert request.time_horizon == "swing"
    assert request.risk_profile == "unknown"
    assert request.horizon_source == "defaulted"
    assert request.risk_profile_source == "defaulted"


def test_horizon_weights_prioritize_expected_agents():
    assert HORIZON_WEIGHTS["long-term"]["fundamental"] > HORIZON_WEIGHTS["long-term"]["technical"]
    assert HORIZON_WEIGHTS["intraday"]["technical"] > HORIZON_WEIGHTS["intraday"]["fundamental"]


def test_signal_score_maps_to_deterministic_decisions():
    assert decision_for_signal_score(1) == Recommendation.avoid
    assert decision_for_signal_score(2) == Recommendation.wait
    assert decision_for_signal_score(3) == Recommendation.neutral
    assert decision_for_signal_score(4) == Recommendation.buy_setup
    assert decision_for_signal_score(5) == Recommendation.strong_buy_setup


def test_score_decision_mismatch_causes_critic_failure_shape():
    final = FinalRecommendation(
        recommendation=Recommendation.wait,
        confidence=0.4,
        confidence_label="Moderate",
        technical_data_confidence=0.7,
        news_data_confidence=0.6,
        fundamental_data_confidence=0.6,
        final_trade_confidence=0.4,
        time_horizon="swing",
        risk_level="high",
        summary="Mismatch test.",
        reasoning={},
        entry_idea="Wait.",
        stop_loss_idea="Use invalidation.",
        key_risks=[],
        missing_data=[],
        critic_review={"signal_score": 1},
        disclaimer=DISCLAIMER,
    )

    issues = validate_final_decision_consistency(final)

    assert issues
    assert issues[0].severity == "critical"
    assert issues[0].type == "decision_score_mismatch"


def test_valuation_wording_avoids_fair_when_risk_is_elevated():
    output = run_fundamental_earnings_agent(
        {
            "fundamentals": {
                "data_source": "yfinance",
                "structured_fundamentals_available": True,
                "valuation": "expensive",
                "metrics": {"eps": 5.0, "pe_ratio": 45.0, "de_ratio": 20.0, "fcf": 1000.0, "roe": 0.2},
                "segments": [],
                "management": [],
            },
            "fundamentals_missing_data": [],
        }
    )

    assert "fair" not in output.summary.lower()
    assert any("valuation" in flag.lower() for flag in output.risk_flags)


def test_technical_risk_flags_for_weak_swing_setup():
    output = run_market_data_agent(
        {
            "ticker": "TEST",
            "market": {
                "current_price": 95.0,
                "previous_close": 96.0,
                "ma_20": 100.0,
                "ma_50": 102.0,
                "ma_200": 110.0,
                "rsi": 42.0,
                "macd_direction": "negative",
                "relative_volume": 0.8,
                "atr_percent": 2.2,
                "support_levels": [90.0],
                "resistance_levels": [105.0],
                "recent_gaps": [],
                "last_candle_date": "2026-06-12",
                "data_source": "yfinance",
            },
            "market_missing_data": [],
        }
    )

    joined = " ".join(output.risk_flags).lower()
    assert "ma20" in joined
    assert "macd" in joined
    assert "relative volume" in joined
    assert "breakout confirmation" in joined


def test_agent_confidence_and_trade_confidence_are_separate_fields():
    market = MarketDataOutput(
        agent="Market Data Agent",
        summary="Weak technicals.",
        confidence=0.8,
        trend="mixed",
        key_signals=[],
        support_levels=[90.0],
        resistance_levels=[110.0],
        volatility_assessment="moderate",
        current_price=95.0,
        ma_20=100.0,
        ma_50=101.0,
        rsi=45.0,
        macd_direction="negative",
        relative_volume=0.8,
    )
    news = NewsSentimentOutput(
        agent="News and Sentiment Agent",
        summary="Mixed news.",
        confidence=0.68,
        sentiment="mixed",
        hype_risk="moderate",
        priced_in_assessment="possible",
    )
    fundamentals = run_fundamental_earnings_agent(
        {
            "fundamentals": {
                "data_source": "yfinance",
                "structured_fundamentals_available": True,
                "valuation": "expensive",
                "metrics": {"eps": 5.0, "pe_ratio": 45.0, "de_ratio": 20.0, "fcf": 1000.0, "roe": 0.2},
                "segments": [],
                "management": [],
            },
            "fundamentals_missing_data": [],
        }
    )
    critic = run_critic_agent(market, news, fundamentals)

    final = run_final_response_agent({"ticker": "TEST", "time_horizon": "swing"}, market, news, fundamentals, critic)

    assert final.technical_data_confidence == market.confidence
    assert final.final_trade_confidence == final.confidence
    assert final.final_trade_confidence != final.technical_data_confidence


def test_long_term_conservative_case_is_not_automatic_avoid():
    market = MarketDataOutput(
        agent="Market Data Agent",
        summary="Short-term entry timing lacks confirmation.",
        confidence=0.8,
        data_confidence=0.8,
        numeric_score=-1,
        label="bearish",
        trend="mixed",
        support_levels=[90.0],
        resistance_levels=[120.0],
        volatility_assessment="moderate",
        current_price=100.0,
        ma_20=105.0,
        ma_50=104.0,
        ma_200=90.0,
        macd_direction="negative",
        source_quality="moderate",
    )
    news = NewsSentimentOutput(
        agent="News and Sentiment Agent",
        summary="News is positive but may be priced in.",
        confidence=0.68,
        data_confidence=0.68,
        numeric_score=1,
        label="bullish",
        sentiment="positive",
        hype_risk="moderate",
        priced_in_assessment="possible",
        source_quality="moderate",
    )
    fundamentals = FundamentalEarningsOutput(
        agent="Fundamental and Earnings Agent",
        summary="Fundamentals are supportive, but valuation risk is elevated.",
        confidence=0.68,
        data_confidence=0.68,
        numeric_score=1,
        label="bullish",
        fundamental_view="supportive",
        valuation_assessment="expensive",
        risk_flags=["P/E is elevated, so valuation depends on continued strong growth."],
    )
    critic = CriticOutput(reliability="pass_with_cautions", show_to_user=True, issues=[])

    final = run_final_response_agent(
        {
            "ticker": "NVDA",
            "time_horizon": "long-term",
            "risk_profile": "conservative",
            "horizon_source": "provided",
            "risk_profile_source": "provided",
        },
        market,
        news,
        fundamentals,
        critic,
    )

    assert final.recommendation in {Recommendation.wait, Recommendation.neutral}
    assert final.risk_level == "high"
    assert "swing setup" not in final.summary.lower()
