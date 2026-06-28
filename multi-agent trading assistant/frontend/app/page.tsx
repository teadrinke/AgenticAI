"use client";

import { Activity, Search } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

type Recommendation = {
  recommendation: "Avoid / No trade" | "Wait" | "Neutral / Watchlist" | "Buy setup" | "Strong buy setup" | "Needs review / insufficient reliable data";
  confidence: number;
  confidence_label: string;
  technical_data_confidence: number;
  news_data_confidence: number;
  fundamental_data_confidence: number;
  final_trade_confidence: number;
  time_horizon: string;
  risk_level: string;
  summary: string;
  reasoning: Record<string, string>;
  entry_idea: string;
  stop_loss_idea: string;
  key_risks: string[];
  missing_data: string[];
  critic_review: {
    reliability: string;
    main_cautions: string[];
    contradictions: string[];
    checks?: string[];
    signal_score?: number;
    signal_score_scale?: string;
    trade_confidence_explanation?: string;
    risk_profile?: string;
  };
  disclaimer: string;
};

type AgentOutput = {
  agent: string;
  summary: string;
  key_findings: string[];
  risk_flags: string[];
  missing_data: string[];
  confidence: number;
};

type SourceReference = {
  source_type: string;
  name: string;
  url: string | null;
  dataset_id: string | null;
};

type AnalysisResponse = {
  id: number;
  query: string;
  ticker: string;
  status: string;
  final: Recommendation;
  market_data: AgentOutput & {
    trend: string;
    key_signals?: string[];
    support_levels: number[];
    resistance_levels: number[];
    volatility_assessment: string;
    current_price?: number | null;
    ma_20?: number | null;
    ma_50?: number | null;
    ma_200?: number | null;
    rsi?: number | null;
    macd_direction?: string;
    relative_volume?: number | null;
    atr_percent?: number | null;
    last_candle_date?: string | null;
  };
  news_sentiment: AgentOutput & {
    sentiment: string;
    hype_risk: string;
    priced_in_assessment: string;
  };
  fundamentals: AgentOutput & {
    fundamental_view: string;
    valuation_assessment: string;
  };
  critic: {
    reliability: string;
    issues: Array<{ severity: string; type: string; description: string }>;
    contradictions: string[];
  };
  sources: SourceReference[];
  metrics: Record<string, unknown>;
  created_at: string;
};

type AnalysisSummary = {
  id: number;
  query: string;
  ticker: string;
  recommendation: "Avoid / No trade" | "Wait" | "Neutral / Watchlist" | "Buy setup" | "Strong buy setup" | "Needs review / insufficient reliable data";
  confidence: number;
  risk_level: string;
  created_at: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

function splitFinding(item: string) {
  const index = item.indexOf(":");
  if (index === -1) return { label: item, value: "" };
  return {
    label: item.slice(0, index),
    value: item.slice(index + 1).trim()
  };
}

function decisionClass(decision: string) {
  return decision.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export default function Home() {
  const [ticker, setTicker] = useState("NVDA");
  const [query, setQuery] = useState("Should I trade NVDA after earnings?");
  const [timeHorizon, setTimeHorizon] = useState("swing");
  const [riskProfile, setRiskProfile] = useState("unknown");
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [history, setHistory] = useState<AnalysisSummary[]>([]);
  const [activeTab, setActiveTab] = useState("technical");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleTickerChange(value: string) {
    const nextTicker = value.toUpperCase();
    const previousTicker = ticker;
    setTicker(nextTicker);
    setResult(null);
    setError(null);
    const expectedQuery = `Should I trade ${previousTicker} after earnings?`;
    if (query === expectedQuery || query.trim() === "") {
      setQuery(`Should I trade ${nextTicker} after earnings?`);
    }
  }

  async function loadHistory() {
    const response = await fetch(`${API_BASE}/analyses`);
    if (response.ok) {
      setHistory(await response.json());
    }
  }

  useEffect(() => {
    loadHistory().catch(() => undefined);
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker,
          query,
          time_horizon: timeHorizon,
          risk_profile: riskProfile,
          event_context: "post_earnings"
        })
      });
      if (!response.ok) {
        throw new Error(`Backend returned ${response.status}`);
      }
      const data = (await response.json()) as AnalysisResponse;
      setResult(data);
      await loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  }

  async function loadAnalysis(id: number) {
    setError(null);
    const response = await fetch(`${API_BASE}/analyses/${id}`);
    if (!response.ok) {
      setError(`Could not load analysis ${id}`);
      return;
    }
    setResult(await response.json());
  }

  const currentAgent = useMemo(() => {
    if (!result) return null;
    if (activeTab === "technical") return result.market_data;
    if (activeTab === "news") return result.news_sentiment;
    return result.fundamentals;
  }, [activeTab, result]);

  const newsSources = useMemo(() => {
    if (!result) return [];
    const seen = new Set<string>();
    return result.sources.filter((source) => {
      if (source.source_type !== "web_search" || !source.url) return false;
      const key = source.url.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [result]);

  return (
    <main className="shell">
      <aside className="sidebar">
        <h1>Trading Research Assistant</h1>
        <p>LangGraph Python agents with critic validation and LangSmith-ready tracing.</p>

        <form className="form" onSubmit={submit}>
          <div className="field">
            <label htmlFor="ticker">Ticker</label>
            <input id="ticker" value={ticker} onChange={(event) => handleTickerChange(event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="query">Question</label>
            <textarea id="query" value={query} onChange={(event) => setQuery(event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="horizon">Time horizon</label>
            <select id="horizon" value={timeHorizon} onChange={(event) => setTimeHorizon(event.target.value)}>
              <option value="intraday">Intraday</option>
              <option value="swing">Swing</option>
              <option value="multi-week">Multi-week</option>
              <option value="long-term">Long-term</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="risk">Risk profile</label>
            <select id="risk" value={riskProfile} onChange={(event) => setRiskProfile(event.target.value)}>
              <option value="unknown">Unknown</option>
              <option value="conservative">Conservative</option>
              <option value="moderate">Moderate</option>
              <option value="aggressive">Aggressive</option>
            </select>
          </div>
          <button className="button" type="submit" disabled={loading}>
            {loading ? <Activity size={18} /> : <Search size={18} />}
            {loading ? "Analyzing" : "Analyze"}
          </button>
        </form>

        <div className="history">
          <h2>History</h2>
          {history.length === 0 ? <p className="muted">No saved analyses yet.</p> : null}
          {history.map((item) => (
            <button className="history-item" key={item.id} onClick={() => loadAnalysis(item.id)}>
              <strong>{item.ticker}</strong> · {item.recommendation} · {(item.confidence * 100).toFixed(0)}%
            </button>
          ))}
        </div>
      </aside>

      <section className="main">
        <div className="result-grid">
          {error ? <div className="error">{error}</div> : null}

          {!result ? (
            <div className="panel">
              <p className="muted">Run an analysis for {ticker} to see the recommendation, agent findings, critic review, and saved metrics.</p>
            </div>
          ) : (
            <>
              <div className="panel recommendation">
                <div className="topline">
                  <div>
                    <p className="section-title">{result.ticker} · Analysis #{result.id}</p>
                    <h2>{result.final.summary}</h2>
                  </div>
                  <span className={`badge ${decisionClass(result.final.recommendation)}`}>{result.final.recommendation}</span>
                </div>

                <div className="stats">
                  <div className="stat">
                    <span>Trade confidence</span>
                    <strong>{(result.final.final_trade_confidence * 100).toFixed(0)}%</strong>
                  </div>
                  <div className="stat">
                    <span>Signal score</span>
                    <strong>{result.final.critic_review.signal_score ? `${result.final.critic_review.signal_score}/5` : "n/a"}</strong>
                  </div>
                  <div className="stat">
                    <span>Risk</span>
                    <strong>{result.final.risk_level}</strong>
                  </div>
                  <div className="stat">
                    <span>Horizon</span>
                    <strong>{result.final.time_horizon}</strong>
                  </div>
                </div>

                <p>{result.final.disclaimer}</p>
                <div className="final-structure">
                  <p><strong>Ticker:</strong> {result.ticker}</p>
                  <p><strong>Decision:</strong> {result.final.recommendation}</p>
                  <p><strong>Signal score:</strong> {result.final.recommendation === "Needs review / insufficient reliable data" ? "N/A" : `${result.final.critic_review.signal_score ?? "n/a"}/5`}</p>
                  <p><strong>Trade confidence:</strong> {(result.final.final_trade_confidence * 100).toFixed(0)}%</p>
                  <p><strong>Risk:</strong> {result.final.risk_level}</p>
                  <p><strong>Horizon:</strong> {result.final.time_horizon}</p>
                  <p><strong>Risk profile:</strong> {result.final.critic_review.risk_profile || "unknown"}</p>
                </div>
                {result.final.reasoning.decision_rule ? <p><strong>Decision rule:</strong> {result.final.reasoning.decision_rule}</p> : null}
                {result.final.reasoning.confidence ? <p><strong>Confidence note:</strong> {result.final.reasoning.confidence}</p> : null}
                <div>
                  <p className="section-title">Why</p>
                  <ul className="list">
                    <li><strong>Technicals:</strong> {result.final.reasoning.technical}</li>
                    <li><strong>News:</strong> {result.final.reasoning.news_sentiment}</li>
                    <li><strong>Fundamentals:</strong> {result.final.reasoning.fundamentals_earnings}</li>
                    <li><strong>Critic:</strong> {result.final.reasoning.critic || result.critic.reliability}</li>
                  </ul>
                </div>
              </div>

              <div className="panel">
                <p className="section-title">Trade framing</p>
                <p><strong>Entry idea:</strong> {result.final.entry_idea}</p>
                <p><strong>Stop-loss idea:</strong> {result.final.stop_loss_idea}</p>
                <p><strong>Key caution:</strong> {result.final.key_risks[0] || "No single dominant caution was identified."}</p>
              </div>

              <div className="panel">
                <div className="tabs">
                  <button className={`tab ${activeTab === "technical" ? "active" : ""}`} onClick={() => setActiveTab("technical")}>Technicals</button>
                  <button className={`tab ${activeTab === "news" ? "active" : ""}`} onClick={() => setActiveTab("news")}>News</button>
                  <button className={`tab ${activeTab === "fundamentals" ? "active" : ""}`} onClick={() => setActiveTab("fundamentals")}>Fundamentals</button>
                </div>

                {currentAgent ? (
                  <>
                    <h3>{currentAgent.agent}</h3>
                    <p>{currentAgent.summary}</p>
                    <p className="muted">Confidence: {(currentAgent.confidence * 100).toFixed(0)}%</p>
                    {activeTab === "technical" ? (
                      <>
                        <div className="mini-grid">
                          <div className="mini-stat">
                            <span>Last close</span>
                            <strong>{result.market_data.current_price ?? "n/a"}</strong>
                          </div>
                          <div className="mini-stat">
                            <span>Trend</span>
                            <strong>{result.market_data.trend}</strong>
                          </div>
                          <div className="mini-stat">
                            <span>Volatility</span>
                            <strong>{result.market_data.volatility_assessment}</strong>
                          </div>
                          <div className="mini-stat">
                            <span>RSI</span>
                            <strong>{result.market_data.rsi ?? "n/a"}</strong>
                          </div>
                          <div className="mini-stat">
                            <span>MA20 / MA50</span>
                            <strong>{result.market_data.ma_20 ?? "n/a"} / {result.market_data.ma_50 ?? "n/a"}</strong>
                          </div>
                          <div className="mini-stat">
                            <span>MACD</span>
                            <strong>{result.market_data.macd_direction || "unknown"}</strong>
                          </div>
                          <div className="mini-stat">
                            <span>Rel. volume</span>
                            <strong>{result.market_data.relative_volume ? `${result.market_data.relative_volume}x` : "n/a"}</strong>
                          </div>
                          <div className="mini-stat">
                            <span>Support</span>
                            <strong>{result.market_data.support_levels.length ? result.market_data.support_levels.join(", ") : "n/a"}</strong>
                          </div>
                          <div className="mini-stat">
                            <span>Resistance</span>
                            <strong>{result.market_data.resistance_levels.length ? result.market_data.resistance_levels.join(", ") : "n/a"}</strong>
                          </div>
                        </div>
                        <p className="section-title">Signals</p>
                        <ul className="list">{(result.market_data.key_signals || currentAgent.key_findings).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
                      </>
                    ) : null}
                    {activeTab === "fundamentals" ? (
                      <div className="metric-grid">
                        {result.fundamentals.key_findings.map((item, index) => {
                          const finding = splitFinding(item);
                          return (
                            <div className="metric" key={`${finding.label}-${index}`}>
                              <span>{finding.label}</span>
                              <strong>{finding.value || "n/a"}</strong>
                            </div>
                          );
                        })}
                      </div>
                    ) : null}
                    {activeTab === "news" ? (
                      <>
                        <p className="section-title">Stock news and developments</p>
                        <ul className="list">{currentAgent.key_findings.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
                      </>
                    ) : null}
                    <p className="section-title">Risk flags</p>
                    {currentAgent.risk_flags.length ? (
                      <ul className="list">{currentAgent.risk_flags.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
                    ) : (
                      <p className="muted">No major risk flags from this agent.</p>
                    )}
                    {activeTab === "news" && newsSources.length > 0 ? (
                      <>
                        <p className="section-title">Sources</p>
                        <div className="source-links">
                          {newsSources.slice(0, 6).map((source, index) => (
                            <a key={`${source.url}-${index}`} href={source.url || "#"} target="_blank" rel="noreferrer">
                              {source.name}
                            </a>
                          ))}
                        </div>
                      </>
                    ) : null}
                  </>
                ) : null}
              </div>

              <div className="panel">
                <p className="section-title">Critic review</p>
                <p><strong>Reliability:</strong> {result.critic.reliability}</p>
                {result.final.critic_review.signal_score_scale ? <p className="muted">Signal score scale: {result.final.critic_review.signal_score_scale}</p> : null}
                {result.final.critic_review.checks?.length ? (
                  <>
                    <p className="section-title">Validation checks</p>
                    <ul className="list">{result.final.critic_review.checks.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
                  </>
                ) : null}
                {result.final.critic_review.trade_confidence_explanation ? (
                  <p><strong>Trade confidence:</strong> {result.final.critic_review.trade_confidence_explanation}</p>
                ) : null}
                <p className="section-title">Issues</p>
                <ul className="list">{result.critic.issues.map((issue, index) => <li key={`${issue.description}-${index}`}>{issue.severity}: {issue.description}</li>)}</ul>
              </div>

              <div className="panel">
                <p className="section-title">Missing data</p>
                <ul className="list">{result.final.missing_data.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
              </div>
            </>
          )}
        </div>
      </section>
    </main>
  );
}
