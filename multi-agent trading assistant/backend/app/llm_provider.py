from __future__ import annotations

import json
import os
from typing import Any

from langsmith import traceable

from .models import FinalRecommendation


DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


def groq_is_configured() -> bool:
    return bool(os.getenv("GROQ_API_KEY"))


def groq_model_name() -> str:
    return os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)


def _safe_json_from_text(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Groq response did not contain a JSON object")
    return json.loads(text[start : end + 1])


def _build_prompt(
    baseline: FinalRecommendation,
    market: dict[str, Any],
    news: dict[str, Any],
    fundamentals: dict[str, Any],
    critic: dict[str, Any],
) -> str:
    return f"""
You are the reasoning layer for a financial research assistant.

Rules:
- This is not financial advice.
- Do not invent prices, indicators, analyst actions, earnings numbers, or sources.
- Use only the evidence in the JSON below.
- If data is missing, stale, or mixed, prefer Wait.
- Keep the same JSON shape as the baseline.
- Preserve critic_review.signal_score, signal_score_scale, checks, and trade_confidence_explanation.
- Final confidence is trade confidence, not average agent confidence.
- Every summary claim must be traceable to one of the agent outputs.
- Do not expose internal provider/tool names in user-facing wording.
- Return only valid JSON. No markdown.

Baseline final recommendation:
{baseline.model_dump_json()}

Market agent output:
{json.dumps(market, default=str)}

News and sentiment agent output:
{json.dumps(news, default=str)}

Fundamental and earnings agent output:
{json.dumps(fundamentals, default=str)}

Critic output:
{json.dumps(critic, default=str)}
""".strip()


@traceable(name="groq_news_reasoning")
def summarize_news_with_groq(ticker: str, headlines: list[str], source_names: list[str]) -> dict[str, Any] | None:
    if not groq_is_configured() or not headlines:
        return None

    from groq import Groq

    prompt = f"""
You are the news analyst for a trading research assistant.

Rules:
- Analyze only the provided source snippets.
- Do not invent facts, numbers, analyst actions, or events.
- If the snippets are weak, say the news picture is mixed or unknown.
- Return only valid JSON with these keys:
  summary, key_findings, factual_news, speculation, analyst_actions,
  sector_and_macro_context, sentiment, hype_risk, priced_in_assessment.
- sentiment must be one of: positive, negative, neutral, mixed, unknown.
- hype_risk must be one of: low, moderate, high, unknown.
- priced_in_assessment must be one of: unlikely, possible, likely, unknown.

Ticker: {ticker}
Source names: {json.dumps(source_names)}
Snippets: {json.dumps(headlines)}
""".strip()
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    completion = client.chat.completions.create(
        model=groq_model_name(),
        temperature=0.1,
        max_tokens=900,
        messages=[
            {"role": "system", "content": "You produce cautious, evidence-bound news analysis as strict JSON."},
            {"role": "user", "content": prompt},
        ],
    )
    content = completion.choices[0].message.content or ""
    return _safe_json_from_text(content)


@traceable(name="groq_final_reasoning")
def refine_final_with_groq(
    baseline: FinalRecommendation,
    market: dict[str, Any],
    news: dict[str, Any],
    fundamentals: dict[str, Any],
    critic: dict[str, Any],
) -> FinalRecommendation:
    if not groq_is_configured():
        return baseline

    from groq import Groq

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    completion = client.chat.completions.create(
        model=groq_model_name(),
        temperature=0.2,
        max_tokens=1200,
        messages=[
            {
                "role": "system",
                "content": "You produce conservative, evidence-bound financial research summaries as strict JSON.",
            },
            {
                "role": "user",
                "content": _build_prompt(
                    baseline=baseline,
                    market=market,
                    news=news,
                    fundamentals=fundamentals,
                    critic=critic,
                ),
            },
        ],
    )
    content = completion.choices[0].message.content or ""
    refined = FinalRecommendation.model_validate(_safe_json_from_text(content))
    refined.disclaimer = baseline.disclaimer
    refined.confidence = min(refined.confidence, baseline.confidence)
    return refined
