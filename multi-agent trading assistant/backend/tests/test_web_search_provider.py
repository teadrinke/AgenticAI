import sys
import types

from app.web_search_provider import fetch_tavily_context


def test_tavily_context_reports_missing_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    context = fetch_tavily_context("NVDA", "Should I trade NVDA after earnings?")

    assert context["status"] == "unavailable"
    assert context["metrics"]["tavily_call_count"] == 0
    assert "Search API key" in context["missing_data"][0]


def test_tavily_context_maps_sources_and_metrics(monkeypatch):
    class FakeClient:
        def __init__(self, api_key: str):
            self.api_key = api_key

        def search(self, *_args, **_kwargs):
            return {
                "results": [
                    {
                        "title": "NVDA earnings reaction",
                        "url": "https://example.com/nvda-earnings",
                        "content": "NVIDIA earnings guidance and analyst reaction remain constructive.",
                        "score": 0.9,
                    }
                ],
                "usage": {"credits": 1},
            }

    fake_tavily = types.SimpleNamespace(TavilyClient=FakeClient)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setitem(sys.modules, "tavily", fake_tavily)

    context = fetch_tavily_context("NVDA", "Should I trade NVDA after earnings?")

    assert context["status"] == "available"
    assert context["metrics"]["tavily_call_count"] == 3
    assert context["metrics"]["tavily_credits"] == 3
    assert context["sources"][0].url == "https://example.com/nvda-earnings"
    assert context["news"]["data_source"] == "tavily"


def test_tavily_context_filters_unrelated_tickers(monkeypatch):
    class FakeClient:
        def __init__(self, api_key: str):
            self.api_key = api_key

        def search(self, *_args, **_kwargs):
            return {
                "results": [
                    {
                        "title": "Why Is Grocery Outlet (GO) Up Since Earnings?",
                        "url": "https://example.com/go-earnings",
                        "content": "Grocery Outlet moved after earnings.",
                    },
                    {
                        "title": "NVIDIA earnings reaction",
                        "url": "https://example.com/nvidia-earnings",
                        "content": "NVIDIA guidance and NVDA stock reaction are in focus.",
                    },
                ],
                "usage": {"credits": 1},
            }

    fake_tavily = types.SimpleNamespace(TavilyClient=FakeClient)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setitem(sys.modules, "tavily", fake_tavily)

    context = fetch_tavily_context("NVDA", "Should I trade NVDA after earnings?")

    assert all("Grocery Outlet" not in item for item in context["news"]["headlines"])
    assert context["metrics"]["tavily_rejected_results"] == 3
    assert any("Excluded" in item for item in context["missing_data"])
    assert "Tavily" not in " ".join(context["missing_data"])
