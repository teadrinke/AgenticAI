import types

from app.llm_provider import groq_is_configured, refine_final_with_groq
from app.models import ConfidenceLabel, FinalRecommendation, Recommendation


def baseline_final() -> FinalRecommendation:
    return FinalRecommendation(
        recommendation=Recommendation.wait,
        confidence=0.58,
        confidence_label=ConfidenceLabel.moderate,
        technical_data_confidence=0.7,
        news_data_confidence=0.68,
        fundamental_data_confidence=0.62,
        final_trade_confidence=0.58,
        time_horizon="swing",
        risk_level="high",
        summary="Baseline summary.",
        reasoning={
            "technical": "Technical summary.",
            "news_sentiment": "News summary.",
            "fundamentals_earnings": "Fundamental summary.",
        },
        entry_idea="Wait for confirmation.",
        stop_loss_idea="Use a defined invalidation level.",
        key_risks=["High volatility"],
        missing_data=["Structured fundamentals"],
        critic_review={"reliability": "pass_with_cautions", "main_cautions": []},
    )


def test_groq_disabled_without_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    baseline = baseline_final()
    refined = refine_final_with_groq(baseline, {}, {}, {}, {})

    assert groq_is_configured() is False
    assert refined == baseline


def test_groq_refines_json_response(monkeypatch):
    baseline = baseline_final()
    payload = baseline.model_dump(mode="json")
    payload["summary"] = "Groq-refined but still conservative summary."
    payload["confidence"] = 0.99

    class FakeCompletions:
        def create(self, **_kwargs):
            message = types.SimpleNamespace(content=str(payload).replace("'", '"'))
            choice = types.SimpleNamespace(message=message)
            return types.SimpleNamespace(choices=[choice])

    class FakeChat:
        completions = FakeCompletions()

    class FakeGroq:
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.chat = FakeChat()

    fake_module = types.SimpleNamespace(Groq=FakeGroq)
    import sys

    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setitem(sys.modules, "groq", fake_module)

    refined = refine_final_with_groq(baseline, {}, {}, {}, {})

    assert refined.summary == "Groq-refined but still conservative summary."
    assert refined.confidence == baseline.confidence
    assert refined.disclaimer == baseline.disclaimer
