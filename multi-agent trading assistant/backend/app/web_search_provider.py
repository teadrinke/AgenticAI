from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from .models import SourceReference


def _accepted_terms(ticker: str) -> list[str]:
    terms = [ticker.lower()]
    company_aliases = {
        "NVDA": ["nvidia", "nvidia corporation"],
        "MSFT": ["microsoft", "microsoft corporation"],
        "AAPL": ["apple", "apple inc"],
        "TSLA": ["tesla", "tesla inc"],
        "AMZN": ["amazon", "amazon.com"],
        "GOOGL": ["alphabet", "google"],
        "GOOG": ["alphabet", "google"],
        "META": ["meta platforms", "facebook"],
    }
    terms.extend(company_aliases.get(ticker.upper(), []))
    return terms


def _matches_ticker(result: dict[str, Any], ticker: str) -> bool:
    haystack = " ".join(
        str(result.get(key) or "") for key in ["title", "content", "url"]
    ).lower()
    return any(term in haystack for term in _accepted_terms(ticker))


def _compact_result(result: dict[str, Any]) -> str:
    title = result.get("title") or "Untitled source"
    content = result.get("content") or ""
    return f"{title}: {content[:350]}".strip()


def _collect_results(response: dict[str, Any], ticker: str) -> tuple[list[dict[str, Any]], int]:
    results = response.get("results") or []
    with_url = [item for item in results if item.get("url")]
    filtered = [item for item in with_url if _matches_ticker(item, ticker)]
    return filtered, len(with_url) - len(filtered)


def _dedupe_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for result in results:
        key = str(result.get("url") or result.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


def _build_sources(results: list[dict[str, Any]], query: str) -> list[SourceReference]:
    retrieved_at = datetime.now(timezone.utc)
    sources: list[SourceReference] = []
    for result in results:
        sources.append(
            SourceReference(
                source_type="web_search",
                name=result.get("title") or "Search result",
                url=result.get("url"),
                dataset_id=f"tavily:{query}",
                timestamp=result.get("published_date"),
                retrieved_at=retrieved_at,
                reliability_tier="tier_2",
            )
        )
    return sources


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)]


def _allowed(value: Any, allowed: set[str], fallback: str) -> str:
    text = str(value or "").lower()
    return text if text in allowed else fallback


def fetch_tavily_context(ticker: str, user_query: str) -> dict[str, Any]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return {
            "status": "unavailable",
            "missing_data": ["Search API key is not configured"],
            "sources": [],
            "news": None,
            "fundamentals": None,
            "metrics": {"tavily_call_count": 0, "tavily_credits": 0, "tavily_status": "missing_key"},
        }

    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    queries = [
        f"{ticker} latest earnings results guidance analyst reaction",
        f"{ticker} company news product innovation partnerships AI cloud chip software updates",
        f"{ticker} stock news sector macro sentiment after earnings",
    ]

    all_results: list[dict[str, Any]] = []
    sources: list[SourceReference] = []
    credits = 0
    rejected_count = 0
    for query in queries:
        response = client.search(
            query,
            search_depth="basic",
            topic="finance",
            time_range="week",
            max_results=5,
            include_answer="basic",
            include_usage=True,
        )
        results, rejected = _collect_results(response, ticker)
        new_results = _dedupe_results([*all_results, *results])[len(all_results):]
        all_results.extend(new_results)
        sources.extend(_build_sources(new_results, query))
        credits += int((response.get("usage") or {}).get("credits") or 0)
        rejected_count += rejected

    headlines = [_compact_result(result) for result in all_results[:6]]
    analyst_actions = [
        item
        for item in headlines
        if any(word in item.lower() for word in ["upgrade", "downgrade", "price target", "analyst"])
    ]
    sector_macro = [
        item
        for item in headlines
        if any(word in item.lower() for word in ["sector", "macro", "fed", "inflation", "semiconductor", "ai"])
    ]

    missing_data = []
    if rejected_count:
        missing_data.append(f"Excluded {rejected_count} search results that did not clearly match {ticker} or a known company alias")
    if not headlines:
        missing_data.append(f"No search results clearly matched {ticker}")

    news = {
        "headlines": headlines or [f"No recent finance search results found for {ticker}"],
        "speculation": [],
        "analyst_actions": analyst_actions,
        "sector_macro": sector_macro,
        "sentiment_score": 0.58 if headlines else 0.5,
        "hype_risk": "moderate",
        "priced_in": "possible",
        "data_source": "tavily",
        "rejected_result_count": rejected_count,
    }
    try:
        from .llm_provider import summarize_news_with_groq

        groq_news = summarize_news_with_groq(ticker, headlines, [source.name for source in sources])
        if groq_news:
            news = {
                "headlines": _as_list(groq_news.get("key_findings")) or news["headlines"],
                "speculation": _as_list(groq_news.get("speculation")),
                "analyst_actions": _as_list(groq_news.get("analyst_actions")),
                "sector_macro": _as_list(groq_news.get("sector_and_macro_context")),
                "sentiment_score": 0.6 if groq_news.get("sentiment") == "positive" else 0.5,
                "hype_risk": _allowed(groq_news.get("hype_risk"), {"low", "moderate", "high", "unknown"}, "unknown"),
                "priced_in": _allowed(groq_news.get("priced_in_assessment"), {"unlikely", "possible", "likely", "unknown"}, "unknown"),
                "data_source": "groq_news",
                "summary": groq_news.get("summary"),
                "factual_news": _as_list(groq_news.get("factual_news")) or _as_list(groq_news.get("key_findings")),
                "rejected_result_count": rejected_count,
            }
    except Exception as exc:
        missing_data.append(f"LLM news analysis unavailable; using filtered search snippets: {exc}")
    fundamentals = {
        "management": [item for item in headlines if any(word in item.lower() for word in ["guidance", "earnings", "revenue", "eps"])],
        "segments": [item for item in headlines if any(word in item.lower() for word in ["segment", "data center", "cloud", "ai"])],
        "data_source": "tavily",
        "structured_fundamentals_available": False,
    }
    return {
        "status": "available",
        "missing_data": missing_data,
        "sources": sources,
        "news": news,
        "fundamentals": fundamentals,
        "metrics": {
            "tavily_call_count": len(queries),
            "tavily_credits": credits,
            "tavily_status": "available",
            "tavily_rejected_results": rejected_count,
        },
    }
