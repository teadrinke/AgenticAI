# Multi-Agent Financial Trading Assistant

## Purpose

This document defines a multi-agent financial trading assistant for a real-world earnings season workflow. The target users are retail traders and small investment teams who need structured research support when deciding whether to buy, sell, hold, or wait on a stock after earnings.

The system does not provide financial advice. It supports research, decision-making, and risk review by combining technical analysis, news and sentiment analysis, fundamental and earnings analysis, validation, and a final user-facing synthesis.

## Core Scenario

A user asks a trading question during earnings season, for example:

> Should I trade NVDA after earnings?

The assistant gathers market data, recent news, sentiment, earnings data, valuation context, and analyst commentary. Specialized agents analyze their own domain. A critic agent validates the outputs before the final response agent produces a balanced recommendation.

The final recommendation must be one of:

- Buy
- Sell
- Hold
- Wait

The system should prefer "Wait" when evidence is incomplete, contradictory, stale, or too uncertain for a confident recommendation.

## System Principles

- Evidence first: Every material claim should cite a source, tool output, dataset field, or clearly marked assumption.
- Separation of concerns: Each agent owns a specific analytical domain.
- No invented data: Agents must not fabricate prices, financial figures, estimates, news events, or analyst actions.
- Uncertainty is acceptable: Missing or conflicting data should be surfaced, not hidden.
- Risk before conviction: The system should explain downside, invalidation conditions, and missing data before presenting an aggressive trade idea.
- Critic validation is mandatory: The critic agent reviews outputs before the final answer is shown to the user.
- Research only: The final response must include a clear disclaimer that the output is not financial advice.

## High-Level Architecture

```text
User Query
   |
   v
Request Router / Orchestrator
   |
   +--> Market Data Agent
   +--> News and Sentiment Agent
   +--> Fundamental and Earnings Agent
   |
   v
Critic and Validation Agent
   |
   v
Final Response Agent
   |
   v
User-Facing Research Response
```

## Shared Inputs

Each agent should receive a normalized task object:

```json
{
  "user_query": "Should I trade NVDA after earnings?",
  "ticker": "NVDA",
  "company_name": "NVIDIA Corporation",
  "event_context": "post_earnings",
  "time_horizon": "unspecified",
  "user_risk_profile": "unknown",
  "as_of": "ISO-8601 timestamp",
  "available_sources": {
    "market_data": [],
    "news": [],
    "fundamentals": [],
    "earnings": [],
    "analyst_data": [],
    "macro_data": []
  }
}
```

## Shared Output Requirements

Every analytical agent must return:

- Agent name
- Summary
- Key findings
- Risk flags
- Missing data
- Evidence references
- Confidence score from 0.0 to 1.0
- Assumptions
- Timestamp

Confidence should reflect data quality, source freshness, agreement among signals, and reasoning strength. It should not reflect how strongly worded the agent's opinion is.

## Agent 1: Market Data Agent

### Role

The Market Data Agent analyzes technical conditions and price behavior. It should not make a full trade recommendation by itself. Its job is to determine whether the chart supports, rejects, or is neutral toward a potential trade.

### Inputs

- Current price
- Intraday and historical OHLCV data
- Volume and relative volume
- Moving averages, such as 20-day, 50-day, and 200-day
- RSI
- MACD
- Support and resistance levels
- Average true range or other volatility measure
- Recent gaps, earnings gaps, and gap fill behavior
- Market and sector benchmark data when available

### Analysis Tasks

- Identify trend direction: bullish, bearish, neutral, or mixed.
- Compare current price to key moving averages.
- Detect abnormal volume.
- Evaluate RSI for overbought, oversold, or neutral conditions.
- Evaluate MACD direction, crossovers, and momentum.
- Identify nearby support and resistance.
- Detect recent gaps and whether they were confirmed or faded.
- Estimate volatility and risk of large price movement.
- Flag technical invalidation levels.

### Output Schema

```json
{
  "agent": "Market Data Agent",
  "trend": "bullish | bearish | neutral | mixed | unknown",
  "key_signals": [
    {
      "signal": "Price above 50-day moving average",
      "direction": "bullish",
      "evidence": "market_data.ma_50"
    }
  ],
  "risk_flags": [
    "RSI indicates overbought conditions",
    "Post-earnings gap has not been retested"
  ],
  "support_levels": [],
  "resistance_levels": [],
  "volatility_assessment": "low | moderate | high | unknown",
  "recent_gaps": [],
  "confidence": 0.0,
  "missing_data": [],
  "assumptions": []
}
```

### Guardrails

- Do not infer exact support or resistance levels without price data.
- Do not claim a moving-average crossover occurred unless calculated from data.
- Do not recommend a trade based only on one indicator.
- Mark signals as mixed when momentum and trend indicators disagree.

## Agent 2: News and Sentiment Agent

### Role

The News and Sentiment Agent analyzes recent information flow around the stock, company, sector, and macro environment. It separates verified facts from speculation and flags whether news may already be priced in.

### Inputs

- Recent company news
- Earnings headlines
- Analyst upgrades, downgrades, initiations, and price target changes
- Social sentiment from supported sources
- Sector news
- Relevant macro events, such as Fed decisions, inflation data, export restrictions, or geopolitical events
- Publication timestamps and source reliability metadata

### Analysis Tasks

- Summarize factual news.
- Separate facts from speculation, rumors, and social media claims.
- Identify sentiment direction: positive, negative, neutral, mixed, or unknown.
- Evaluate whether the news is new, stale, or likely priced in.
- Identify hype risk.
- Identify analyst consensus changes.
- Identify sector or macro drivers that may affect the ticker.
- Flag source quality concerns.

### Output Schema

```json
{
  "agent": "News and Sentiment Agent",
  "sentiment": "positive | negative | neutral | mixed | unknown",
  "factual_news": [
    {
      "claim": "Company reported earnings above consensus",
      "source": "source_id",
      "timestamp": "ISO-8601 timestamp"
    }
  ],
  "speculation": [
    {
      "claim": "Social posts suggest unusually high retail interest",
      "source": "source_id",
      "confidence": "low"
    }
  ],
  "analyst_actions": [],
  "sector_and_macro_context": [],
  "hype_risk": "low | moderate | high | unknown",
  "priced_in_assessment": "unlikely | possible | likely | unknown",
  "risk_flags": [],
  "confidence": 0.0,
  "missing_data": [],
  "assumptions": []
}
```

### Guardrails

- Do not treat rumors, social posts, or unsourced commentary as facts.
- Do not claim "analysts upgraded the stock" without specific sourced actions.
- Do not assume positive news means future price appreciation.
- Flag stale news when it predates the current price move.

## Agent 3: Fundamental and Earnings Agent

### Role

The Fundamental and Earnings Agent determines whether company fundamentals, earnings results, guidance, and valuation support the trade idea. It should distinguish business quality from near-term trading setup.

### Inputs

- Revenue
- EPS
- Earnings surprise
- Revenue surprise
- Guidance
- Gross margin, operating margin, and net margin
- Free cash flow
- Debt and liquidity
- Valuation ratios, such as P/E, forward P/E, P/S, EV/EBITDA, and PEG when available
- Segment growth
- Management commentary
- Consensus estimates
- Historical growth rates
- Peer or sector valuation comparisons

### Analysis Tasks

- Evaluate whether earnings beat, missed, or matched expectations.
- Evaluate guidance quality and direction.
- Assess margin expansion or compression.
- Review cash flow quality.
- Review debt and balance sheet risk.
- Evaluate valuation against growth and peers.
- Identify whether fundamentals support a buy, sell, hold, or wait stance.
- Flag weak assumptions in the trade thesis.
- Distinguish short-term reaction from long-term business strength.

### Output Schema

```json
{
  "agent": "Fundamental and Earnings Agent",
  "fundamental_view": "supportive | unsupportive | mixed | unknown",
  "earnings_summary": {
    "revenue": null,
    "eps": null,
    "earnings_surprise": null,
    "guidance": "positive | negative | neutral | mixed | unknown"
  },
  "quality_indicators": {
    "margins": "improving | declining | stable | unknown",
    "free_cash_flow": "strong | weak | mixed | unknown",
    "debt_risk": "low | moderate | high | unknown"
  },
  "valuation_assessment": "cheap | fair | expensive | unknown",
  "segment_growth_notes": [],
  "management_commentary": [],
  "risk_flags": [
    "Valuation depends on aggressive growth assumptions"
  ],
  "confidence": 0.0,
  "missing_data": [],
  "assumptions": []
}
```

### Guardrails

- Do not invent financial figures.
- Do not compare valuation to peers unless peer data is available.
- Do not call valuation cheap or expensive without a stated benchmark.
- Do not equate an earnings beat with a buy recommendation unless valuation, guidance, and risk are also considered.

## Agent 4: Critic and Validation Agent

### Role

The Critic and Validation Agent is mainly for testing and validating outputs. It does not generate the trade thesis. It reviews all prior agent outputs and determines whether the final answer is reliable enough to show to the user.

### Inputs

- Market Data Agent output
- News and Sentiment Agent output
- Fundamental and Earnings Agent output
- Source metadata
- Tool call logs
- Intermediate reasoning summaries when available
- Draft final response, if generated before critic review

### Validation Tasks

- Check for hallucinations.
- Check unsupported claims.
- Check fake or unverifiable numbers.
- Check missing sources.
- Check contradictions between agents.
- Check weak reasoning.
- Check overconfidence.
- Check missing data that should affect the recommendation.
- Check unsafe or overly directive recommendations.
- Ensure each final claim is traceable to evidence or clearly marked as an assumption.
- Adjust or challenge confidence scores when needed.
- Decide whether the output is reliable enough to show to the user.

### Output Schema

```json
{
  "agent": "Critic and Validation Agent",
  "reliability": "pass | pass_with_cautions | fail",
  "show_to_user": true,
  "issues": [
    {
      "severity": "low | medium | high | critical",
      "type": "unsupported_claim | hallucination | contradiction | missing_data | overconfidence | unsafe_recommendation",
      "description": "The draft states exact RSI but no RSI data is present.",
      "affected_agent": "Market Data Agent",
      "required_fix": "Remove exact RSI value or add source data."
    }
  ],
  "confidence_adjustments": [
    {
      "target": "final_recommendation",
      "original_confidence": 0.72,
      "adjusted_confidence": 0.58,
      "reason": "News and fundamentals agree, but technical data is incomplete."
    }
  ],
  "contradictions": [],
  "missing_evidence": [],
  "final_notes": []
}
```

### Guardrails

- Do not create new bullish or bearish arguments unless they are validation findings.
- Do not silently repair unsupported claims; flag them and require correction.
- Do not allow exact numbers in final output unless sourced.
- Reduce confidence when critical data is missing, sources are stale, or agents disagree.
- Fail the output if it contains fabricated data or an unsafe recommendation.

## Agent 5: Final Response Agent

### Role

The Final Response Agent combines all validated agent outputs into a concise user-facing research answer. It produces the recommendation, explains the reasoning, names risks, and includes the critic review.

### Inputs

- Validated outputs from all analytical agents
- Critic and Validation Agent result
- User query
- User risk profile and time horizon, if known

### Output Requirements

The final response must include:

- Recommendation: buy, sell, hold, or wait
- Confidence score
- Time horizon
- Reasoning
- Entry idea
- Stop-loss idea
- Risk level
- Key risks
- Missing data
- Critic review
- Disclaimer

### Output Schema

```json
{
  "recommendation": "buy | sell | hold | wait",
  "confidence": 0.0,
  "time_horizon": "intraday | swing | multi-week | long-term | unspecified",
  "risk_level": "low | moderate | high | unknown",
  "summary": "",
  "reasoning": {
    "technical": "",
    "news_sentiment": "",
    "fundamentals_earnings": ""
  },
  "entry_idea": "",
  "stop_loss_idea": "",
  "key_risks": [],
  "missing_data": [],
  "critic_review": {
    "reliability": "pass | pass_with_cautions | fail",
    "main_cautions": []
  },
  "disclaimer": "This is not financial advice. It is for research and decision support only."
}
```

### Recommendation Rules

- Buy: Use only when technicals, fundamentals, and news/sentiment are broadly supportive and risks are defined.
- Sell: Use when downside evidence is strong, fundamentals or technicals have materially weakened, or the trade thesis is invalidated.
- Hold: Use when the user already owns the stock and evidence supports staying invested without adding exposure.
- Wait: Use when signals are mixed, price is extended, post-earnings volatility is high, or data is missing.

If user position status is unknown, avoid assuming they already own the stock. Prefer "Wait" or a conditional answer when ownership matters.

## Orchestration Workflow

1. Parse the user query for ticker, event context, time horizon, and requested action.
2. Collect market, news, sentiment, fundamentals, earnings, analyst, sector, and macro data.
3. Send normalized inputs to the Market Data Agent.
4. Send normalized inputs to the News and Sentiment Agent.
5. Send normalized inputs to the Fundamental and Earnings Agent.
6. Collect and normalize all agent outputs.
7. Run the Critic and Validation Agent.
8. If critic result is "fail", return a cautious answer that explains why the system cannot make a reliable recommendation.
9. If critic result is "pass" or "pass_with_cautions", generate the final response.
10. Log metrics for evaluation, debugging, cost tracking, and model improvement.

## Real-Life Workflow Example: NVDA After Earnings

### User Query

> Should I trade NVDA after earnings?

### Step 1: Market Data Agent

The Market Data Agent analyzes:

- Post-earnings price reaction
- Gap up or gap down behavior
- Volume compared with average volume
- Price relative to 20-day, 50-day, and 200-day moving averages
- RSI and MACD momentum
- Support and resistance near the current price
- Volatility and average true range

Example output pattern:

```json
{
  "trend": "mixed",
  "key_signals": [
    "Price trend remains above major moving averages",
    "Post-earnings move appears extended relative to recent volatility"
  ],
  "risk_flags": [
    "High volatility after earnings",
    "Possible gap-fill risk"
  ],
  "confidence": 0.64
}
```

### Step 2: News and Sentiment Agent

The News and Sentiment Agent analyzes:

- Earnings headlines
- Analyst reactions
- AI chip demand commentary
- Sector reaction in semiconductors
- Social sentiment intensity
- Macro risks affecting growth or technology stocks

Example output pattern:

```json
{
  "sentiment": "positive",
  "factual_news": [
    "Earnings headlines are broadly positive based on available sources"
  ],
  "speculation": [
    "Social discussion may include momentum-driven hype"
  ],
  "hype_risk": "high",
  "priced_in_assessment": "possible",
  "confidence": 0.61
}
```

### Step 3: Fundamental and Earnings Agent

The Fundamental and Earnings Agent analyzes:

- Revenue growth
- EPS result and surprise
- Guidance
- Margins
- Free cash flow
- Segment growth, such as data center revenue
- Valuation versus growth expectations
- Management commentary

Example output pattern:

```json
{
  "fundamental_view": "supportive",
  "earnings_summary": {
    "guidance": "positive"
  },
  "valuation_assessment": "expensive",
  "risk_flags": [
    "Valuation may already reflect strong growth expectations"
  ],
  "confidence": 0.68
}
```

### Step 4: Critic and Validation Agent

The Critic and Validation Agent checks:

- Are all financial figures sourced?
- Are technical indicators calculated from actual price data?
- Are analyst actions backed by sources?
- Are social sentiment claims labeled as lower-confidence?
- Do fundamentals support the same direction as technicals?
- Is the recommendation too confident?
- Is the final output clear that it is not financial advice?

Example output pattern:

```json
{
  "reliability": "pass_with_cautions",
  "show_to_user": true,
  "issues": [
    {
      "severity": "medium",
      "type": "overconfidence",
      "description": "The setup has positive fundamentals but elevated post-earnings volatility and valuation risk.",
      "required_fix": "Lower final confidence and avoid an aggressive buy recommendation."
    }
  ],
  "confidence_adjustments": [
    {
      "target": "final_recommendation",
      "original_confidence": 0.70,
      "adjusted_confidence": 0.58,
      "reason": "Strong fundamentals are offset by valuation and volatility risk."
    }
  ]
}
```

### Step 5: Final Response Agent

The Final Response Agent produces a balanced answer.

Example final output pattern:

```text
Recommendation: Wait
Confidence: 0.58
Time horizon: Swing to multi-week
Risk level: High

NVDA may have strong fundamental support after earnings, but the setup is not automatically a buy. Technicals show momentum, while post-earnings volatility and possible gap-fill risk make chasing the move risky. News and sentiment appear positive, but hype risk is elevated and some of the good news may already be priced in.

Entry idea: Consider waiting for a pullback toward confirmed support or a consolidation breakout with strong volume.
Stop-loss idea: Use a predefined invalidation level below support or based on average true range.
Key risks: valuation compression, post-earnings reversal, crowded sentiment, sector weakness, macro risk.
Missing data: current price data, exact earnings figures, guidance details, analyst actions, and user's position/risk profile.
Critic review: Passed with cautions. Confidence was reduced because the evidence is constructive but not one-sided.

This is not financial advice. It is for research and decision support only.
```

## Evidence and Source Handling

Each data item should include:

- Source name
- Source URL or dataset identifier
- Timestamp
- Retrieval time
- Data field name
- Reliability tier

Recommended source tiers:

- Tier 1: Exchange data, company filings, company press releases, earnings call transcripts, official financial statements
- Tier 2: Major financial data vendors, established financial news outlets, analyst aggregators
- Tier 3: Social media, forums, blogs, unsourced commentary

The final answer may use Tier 3 data only when clearly labeled as sentiment or speculation.

## Confidence Scoring Guidance

Suggested confidence bands:

- 0.00 to 0.39: Low confidence
- 0.40 to 0.69: Moderate confidence
- 0.70 to 0.84: High confidence
- 0.85 to 1.00: Very high confidence, allowed only when evidence is strong, current, sourced, and aligned

Confidence should be reduced when:

- Data is missing
- Sources are stale
- Agent outputs contradict each other
- The stock is highly volatile
- Recommendation depends on assumptions
- News may already be priced in
- Valuation is stretched
- User's time horizon or risk profile is unknown

## Safety and Compliance Requirements

- Always state that the output is not financial advice.
- Avoid guarantees, promises, or claims of certain profit.
- Do not instruct the user to place a trade immediately.
- Present trade ideas conditionally, with risks and invalidation levels.
- Ask for missing user context when needed, such as current position, time horizon, and risk tolerance.
- Avoid personalized suitability claims unless the system is designed and authorized to handle them.
- Log missing data and uncertainty.

## Performance Metrics

### Correctness Metrics

| Metric | Definition | Target Direction |
| --- | --- | --- |
| Data Accuracy Rate | Percentage of numeric and factual claims that match source data. | Higher is better |
| Unsupported Claim Rate | Percentage of claims without evidence, citation, or assumption label. | Lower is better |
| Hallucination Rate | Percentage of outputs containing fabricated facts, numbers, sources, or events. | Lower is better |
| Contradiction Rate | Percentage of outputs with unresolved contradictions between agents or within the final answer. | Lower is better |
| Recommendation Validity Score | Human or automated score measuring whether the recommendation follows from the evidence and stated rules. | Higher is better |

### Trading Analysis Quality Metrics

| Metric | Definition | Target Direction |
| --- | --- | --- |
| Signal Agreement Score | Degree of alignment among technical, sentiment, and fundamental signals. | Higher indicates cleaner setup |
| Risk Coverage Score | Percentage of material risks identified, including volatility, valuation, event, sector, and macro risks. | Higher is better |
| Confidence Calibration Score | Measures whether confidence scores match evidence quality and later review outcomes. | Higher is better |
| Actionability Score | Measures whether the answer includes usable entry, stop-loss, time horizon, and invalidation context. | Higher is better |
| Explainability Score | Measures clarity of reasoning and traceability from evidence to conclusion. | Higher is better |

### Speed and Efficiency Metrics

| Metric | Definition | Target Direction |
| --- | --- | --- |
| Total Latency | End-to-end time from user query to final response. | Lower is better |
| Agent Latency | Runtime per individual agent. | Lower is better |
| Critic Review Latency | Time required for critic validation. | Lower is better |
| Tool Call Count | Number of external data, calculation, or retrieval calls per query. | Lower is better when quality is preserved |
| Token Usage | Total model tokens used across agents. | Lower is better when quality is preserved |
| Cost per Query | Total estimated cost of model calls, tools, and data access per user query. | Lower is better when quality is preserved |

### Reliability Metrics

| Metric | Definition | Target Direction |
| --- | --- | --- |
| Completion Rate | Percentage of requests that return a final usable response. | Higher is better |
| Failure Rate | Percentage of requests that fail due to tool errors, missing data, parsing errors, or validation failure. | Lower is better |
| Fallback Rate | Percentage of requests requiring fallback sources, fallback models, or degraded-mode responses. | Lower is better, but not zero at the expense of honesty |
| Reproducibility Score | Similarity of outputs when the same query and same data snapshot are used. | Higher is better |
| Missing Data Detection Rate | Percentage of known missing inputs correctly identified by agents or critic. | Higher is better |

### Critic Agent Metrics

| Metric | Definition | Target Direction |
| --- | --- | --- |
| Hallucination Detection Rate | Percentage of hallucinations correctly flagged by the critic. | Higher is better |
| False Alarm Rate | Percentage of critic flags that are not actual issues. | Lower is better |
| Contradiction Detection Rate | Percentage of cross-agent contradictions correctly identified. | Higher is better |
| Confidence Adjustment Accuracy | Measures whether critic-adjusted confidence better matches evidence quality and review outcomes. | Higher is better |
| Output Improvement Score | Measures how much critic feedback improves final answer correctness, safety, and clarity. | Higher is better |

## Evaluation Process

1. Build a test set of historical earnings-season questions across different sectors and market conditions.
2. Freeze source data snapshots for reproducible testing.
3. Run all agents and store raw outputs.
4. Run critic validation and store issues.
5. Generate final responses.
6. Have human reviewers score correctness, trading analysis quality, safety, and clarity.
7. Compare recommendations against predefined evidence-based rubrics, not only future price movement.
8. Track metrics over time by ticker, sector, market regime, and data availability.

## Failure Modes and Fallbacks

### Missing Market Data

Fallback behavior:

- Do not provide exact technical levels.
- State that technical confidence is limited.
- Prefer "Wait" unless fundamentals and news are unusually clear.

### Missing Earnings Data

Fallback behavior:

- Do not claim earnings beat, miss, or guidance direction.
- Ask for or retrieve the earnings release.
- Reduce final confidence.

### Conflicting Agent Outputs

Fallback behavior:

- Surface the conflict clearly.
- Prefer "Hold" or "Wait" unless one domain has much stronger evidence.
- Require critic confidence adjustment.

### Critic Failure

Fallback behavior:

- Do not show an unvalidated high-conviction recommendation.
- Return a limited response explaining that validation failed.
- Include what data or checks are needed before a recommendation can be trusted.

## Implementation Notes

- The orchestrator should run the three analytical agents in parallel when data is available.
- The critic should run after analytical agents complete.
- The final response should be generated only after critic validation.
- Store structured intermediate outputs for auditability.
- Use deterministic calculation code for indicators where possible.
- Use source-aware retrieval for news and earnings data.
- Keep model temperature low for validation and final recommendation generation.
- Use stricter schemas for production responses than for exploratory research.
- Include a replay mode that reruns the same query against the same data snapshot for reproducibility testing.

## Minimum Viable Version

The first production prototype should support:

- Ticker extraction
- Current and historical market data retrieval
- Basic technical indicators: moving averages, RSI, MACD, volume, support, resistance
- Recent news retrieval
- Earnings summary retrieval
- Structured outputs from all agents
- Critic validation
- Final recommendation with disclaimer
- Metric logging for latency, tool calls, token usage, missing data, and critic issues

## Recommended Final Response Template

```text
Recommendation: [Buy | Sell | Hold | Wait]
Confidence: [0.00-1.00] ([Low | Moderate | High])
Time horizon: [Intraday | Swing | Multi-week | Long-term | Unspecified]
Risk level: [Low | Moderate | High | Unknown]

Summary:
[Short conclusion.]

Why:
- Technicals: [Key validated technical finding.]
- News and sentiment: [Key validated news/sentiment finding.]
- Fundamentals and earnings: [Key validated fundamental finding.]

Entry idea:
[Conditional entry idea, not an instruction.]

Stop-loss idea:
[Risk-based invalidation idea.]

Key risks:
- [Risk 1]
- [Risk 2]
- [Risk 3]

Missing data:
- [Missing input 1]
- [Missing input 2]

Critic review:
[Pass, pass with cautions, or fail. Include main cautions.]

Disclaimer:
This is not financial advice. It is for research and decision support only.
```
