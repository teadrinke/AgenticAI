from __future__ import annotations

import time
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .agents import (
    run_critic_agent,
    run_final_response_agent,
    run_fundamental_earnings_agent,
    run_market_data_agent,
    run_news_sentiment_agent,
)
from .fundamentals_provider import fetch_yfinance_fundamentals
from .llm_provider import groq_is_configured, groq_model_name
from .market_data_provider import fetch_yfinance_market_snapshot
from .models import (
    AnalyzeRequest,
    CriticOutput,
    FinalRecommendation,
    FundamentalEarningsOutput,
    MarketDataOutput,
    NewsSentimentOutput,
    SourceReference,
)
from .sample_data import build_fixture_snapshot
from .web_search_provider import fetch_tavily_context


class TradingGraphState(TypedDict, total=False):
    request: dict[str, Any]
    snapshot: dict[str, Any]
    market_data: MarketDataOutput
    news_sentiment: NewsSentimentOutput
    fundamentals: FundamentalEarningsOutput
    critic: CriticOutput
    final: FinalRecommendation
    sources: list[SourceReference]
    candles: list[dict[str, Any]]
    metrics: dict[str, Any]


def load_data_node(state: TradingGraphState) -> TradingGraphState:
    ticker = state["request"]["ticker"]
    started = time.perf_counter()
    snapshot = build_fixture_snapshot(ticker)
    snapshot["time_horizon"] = state["request"].get("time_horizon", "swing")
    snapshot["risk_profile"] = state["request"].get("risk_profile", "unknown")
    snapshot["horizon_source"] = state["request"].get("horizon_source", "provided")
    snapshot["risk_profile_source"] = state["request"].get("risk_profile_source", "provided")
    candles: list[dict[str, Any]] = []
    tool_call_count = 1
    data_mode = "fixture"
    try:
        market_data = fetch_yfinance_market_snapshot(ticker)
        snapshot["market"] = market_data["market"]
        snapshot["market_missing_data"] = market_data["missing_data"]
        snapshot["sources"] = [
            *market_data["sources"],
            *[source for source in snapshot["sources"] if not str(source.dataset_id).startswith("fixture-market")],
        ]
        candles = market_data["candles"]
        tool_call_count += 1
        data_mode = "yfinance"
    except Exception as exc:
        snapshot["market_missing_data"] = [f"yfinance unavailable, fixture fallback used: {exc}"]
    try:
        tavily_context = fetch_tavily_context(ticker, state["request"]["query"])
        if tavily_context["status"] == "available":
            snapshot["news"] = tavily_context["news"]
            snapshot["fundamentals"] = {**snapshot["fundamentals"], **tavily_context["fundamentals"]}
            snapshot["sources"] = [*snapshot["sources"], *tavily_context["sources"]]
            snapshot["tavily_missing_data"] = tavily_context["missing_data"]
        else:
            snapshot["tavily_missing_data"] = tavily_context["missing_data"]
        tavily_metrics = tavily_context["metrics"]
    except Exception as exc:
        snapshot["tavily_missing_data"] = [f"Search provider unavailable, fixture news/fundamentals used: {exc}"]
        tavily_metrics = {"tavily_call_count": 0, "tavily_credits": 0, "tavily_status": "error"}
    try:
        fundamental_data = fetch_yfinance_fundamentals(ticker)
        if fundamental_data["status"] == "available":
            snapshot["fundamentals"] = {
                **snapshot["fundamentals"],
                "metrics": fundamental_data["metrics"],
                "structured_fundamentals_available": True,
                "data_source": "yfinance",
            }
            snapshot["sources"] = [*snapshot["sources"], *fundamental_data["sources"]]
        snapshot["fundamentals_missing_data"] = fundamental_data["missing_data"]
    except Exception as exc:
        snapshot["fundamentals_missing_data"] = [f"yfinance fundamentals unavailable: {exc}"]
    return {
        "snapshot": snapshot,
        "sources": snapshot["sources"],
        "candles": candles,
        "metrics": {
            "tool_call_count": tool_call_count,
            "data_load_latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "data_mode": data_mode,
            "candle_count": len(candles),
            "source_count": len(snapshot["sources"]),
            **tavily_metrics,
        },
    }


def market_node(state: TradingGraphState) -> TradingGraphState:
    started = time.perf_counter()
    output = run_market_data_agent(state["snapshot"])
    metrics = dict(state.get("metrics", {}))
    metrics["market_agent_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return {"market_data": output, "metrics": metrics}


def news_node(state: TradingGraphState) -> TradingGraphState:
    started = time.perf_counter()
    output = run_news_sentiment_agent(state["snapshot"])
    metrics = dict(state.get("metrics", {}))
    metrics["news_agent_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return {"news_sentiment": output, "metrics": metrics}


def fundamentals_node(state: TradingGraphState) -> TradingGraphState:
    started = time.perf_counter()
    output = run_fundamental_earnings_agent(state["snapshot"])
    metrics = dict(state.get("metrics", {}))
    metrics["fundamental_agent_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return {"fundamentals": output, "metrics": metrics}


def critic_node(state: TradingGraphState) -> TradingGraphState:
    started = time.perf_counter()
    output = run_critic_agent(state["market_data"], state["news_sentiment"], state["fundamentals"])
    metrics = dict(state.get("metrics", {}))
    metrics["critic_review_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    metrics["critic_issue_count"] = len(output.issues)
    return {"critic": output, "metrics": metrics}


def final_node(state: TradingGraphState) -> TradingGraphState:
    started = time.perf_counter()
    output = run_final_response_agent(
        state["request"],
        state["market_data"],
        state["news_sentiment"],
        state["fundamentals"],
        state["critic"],
    )
    metrics = dict(state.get("metrics", {}))
    metrics["final_agent_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    metrics["groq_enabled"] = groq_is_configured()
    metrics["groq_model"] = groq_model_name() if groq_is_configured() else None
    return {"final": output, "metrics": metrics}


def route_after_critic(state: TradingGraphState) -> str:
    return "final" if state["critic"].show_to_user else "final"


def build_trading_graph():
    graph = StateGraph(TradingGraphState)
    graph.add_node("load_data", load_data_node)
    graph.add_node("market_data_agent", market_node)
    graph.add_node("news_sentiment_agent", news_node)
    graph.add_node("fundamental_earnings_agent", fundamentals_node)
    graph.add_node("critic_validation_agent", critic_node)
    graph.add_node("final_response_agent", final_node)

    graph.add_edge(START, "load_data")
    graph.add_edge("load_data", "market_data_agent")
    graph.add_edge("market_data_agent", "news_sentiment_agent")
    graph.add_edge("news_sentiment_agent", "fundamental_earnings_agent")
    graph.add_edge("fundamental_earnings_agent", "critic_validation_agent")
    graph.add_conditional_edges(
        "critic_validation_agent",
        route_after_critic,
        {"final": "final_response_agent"},
    )
    graph.add_edge("final_response_agent", END)
    return graph.compile()


trading_graph = build_trading_graph()


def run_analysis_graph(request: AnalyzeRequest) -> TradingGraphState:
    started = time.perf_counter()
    state = trading_graph.invoke({"request": request.model_dump()})
    metrics = dict(state.get("metrics", {}))
    metrics["total_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    metrics.setdefault("token_usage", 0)
    metrics.setdefault("estimated_cost_usd", 0)
    state["metrics"] = metrics
    return state
