# LangGraph Trading Research Assistant

A multi-agent stock research assistant for earnings-season trade analysis. It combines market technicals, news/sentiment, fundamentals, critic validation, and deterministic scoring to produce a structured research output.

This project is for research and decision support only. It is not financial advice and it does not execute trades.

## Architecture

```text
User
 |
 v
Supervisor / Orchestrator
 |
 +--> Market Data Agent
 |
 +--> News & Sentiment Agent
 |
 +--> Fundamental & Earnings Agent
 |
 v
Critic / Validation Agent
 |
 v
Final Response Agent
 |
 v
User-facing trade research output
```

There are 6 total nodes/agents when counting the supervisor:

1. Supervisor / Orchestrator
2. Market Data Agent
3. News & Sentiment Agent
4. Fundamental & Earnings Agent
5. Critic / Validation Agent
6. Final Response Agent

Core principle:

```text
Agents analyze.
Scoring engine decides.
Critic validates.
Final Response Agent explains.
```

## Features

- LangGraph Python workflow for agent orchestration.
- FastAPI backend with SQLite persistence.
- Minimal Next.js frontend.
- LangSmith-ready tracing.
- yfinance candles for technical analysis.
- Tavily-based web/news retrieval when configured.
- Groq-based optional reasoning/news summarization.
- Deterministic weighted scoring by time horizon and risk profile.
- Critic validation for mismatches, unsupported claims, source issues, and unsafe output.
- Separate agent data confidence from final trade confidence.

## Decision Scale

The final decision is deterministic and must match the signal score:

| Signal score | Decision |
| --- | --- |
| 1/5 | Avoid / No trade |
| 2/5 | Wait |
| 3/5 | Neutral / Watchlist |
| 4/5 | Buy setup |
| 5/5 | Strong buy setup |

If critic validation fails, the output becomes:

```text
Needs review / insufficient reliable data
```

## Horizon Weights

The scoring engine weights agents differently by time horizon:

| Horizon | Technicals | News | Fundamentals |
| --- | ---: | ---: | ---: |
| intraday | 60% | 30% | 10% |
| swing | 50% | 20% | 30% |
| multi-week | 35% | 25% | 40% |
| long-term | 20% | 20% | 60% |

Risk profile also adjusts the score:

- `unknown`: treated like moderate, but blocks overly strong conclusions without clean evidence.
- `conservative`: penalizes conflicts, valuation risk, missing technical confirmation, and critic cautions.
- `moderate`: uses the base score unless critic penalties apply.
- `aggressive`: can allow a small upgrade only when evidence is aligned and critic passes.

## Project Structure

```text
.
+-- agents.md
+-- README.md
+-- run-backend.ps1
+-- run-frontend.ps1
+-- backend/
|   +-- app/
|   |   +-- agents.py
|   |   +-- database.py
|   |   +-- fundamentals_provider.py
|   |   +-- graph.py
|   |   +-- llm_provider.py
|   |   +-- main.py
|   |   +-- market_data_provider.py
|   |   +-- models.py
|   |   +-- sample_data.py
|   |   +-- technical_indicators.py
|   |   +-- web_search_provider.py
|   +-- tests/
|   +-- requirements.txt
|   +-- .env.example
+-- frontend/
    +-- app/
    |   +-- page.tsx
    |   +-- styles.css
    +-- package.json
    +-- package-lock.json
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- PowerShell on Windows

Optional API keys:

- Tavily API key for web/news search
- Groq API key for LLM-assisted news/final wording
- LangSmith API key for tracing

The app can run without paid APIs by using fixture/fallback behavior, but live analysis quality is better with keys configured.

## Backend Setup

```powershell
cd "C:\Users\acer\OneDrive - Society for Computer Technology & Research's\Documents\financial assistant\backend"
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
```

Edit `backend/.env`:

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_langsmith_key_here
LANGSMITH_PROJECT=financial-trading-assistant

TAVILY_API_KEY=your_tavily_key_here

GROQ_API_KEY=your_groq_key_here
GROQ_MODEL=llama-3.3-70b-versatile

DATABASE_URL=sqlite:///./financial_assistant.db
```

## Frontend Setup

```powershell
cd "C:\Users\acer\OneDrive - Society for Computer Technology & Research's\Documents\financial assistant\frontend"
npm install
```

If this machine's global `npm` is unavailable, use the bundled Node command already used in this project:

```powershell
& "C:\Users\acer\OneDrive - Society for Computer Technology & Research's\Desktop\NodeJS\node.exe" .\node_modules\next\dist\bin\next dev -H 127.0.0.1 -p 3000
```

## Run The App

Open two PowerShell terminals.

Terminal 1:

```powershell
cd "C:\Users\acer\OneDrive - Society for Computer Technology & Research's\Documents\financial assistant"
.\run-backend.ps1
```

Backend:

```text
http://127.0.0.1:8000
```

Health check:

```text
http://127.0.0.1:8000/health
```

API docs:

```text
http://127.0.0.1:8000/docs
```

Terminal 2:

```powershell
cd "C:\Users\acer\OneDrive - Society for Computer Technology & Research's\Documents\financial assistant"
.\run-frontend.ps1
```

Frontend:

```text
http://127.0.0.1:3000
```

Note: `http://127.0.0.1:8000/` may show `{"detail":"Not Found"}`. That is normal because port `8000` is the API, not the frontend.

## API

Analyze a ticker:

```http
POST /analyze
```

Example body:

```json
{
  "query": "Should I trade NVDA after earnings?",
  "ticker": "NVDA",
  "event_context": "post_earnings",
  "time_horizon": "swing",
  "risk_profile": "moderate"
}
```

Other endpoints:

```text
GET /health
GET /analyses
GET /analyses/{id}
```

## Data Sources

- Market candles: yfinance
- Technical indicators: pandas, numpy, ta
- Web/news search: Tavily, when configured
- Fundamentals: yfinance snapshot fields
- LLM reasoning layer: Groq, when configured
- Observability: LangSmith, when configured

The final user-facing output avoids exposing internal provider names.

## Fundamentals Shown

The frontend intentionally shows only these five metrics:

- EPS
- P/E ratio
- D/E ratio
- Free cash flow
- ROE

## Testing

Backend:

```powershell
cd "C:\Users\acer\OneDrive - Society for Computer Technology & Research's\Documents\financial assistant\backend"
.\.venv\Scripts\python.exe -m pytest -q
```

Frontend build:

```powershell
cd "C:\Users\acer\OneDrive - Society for Computer Technology & Research's\Documents\financial assistant\frontend"
& "C:\Users\acer\OneDrive - Society for Computer Technology & Research's\Desktop\NodeJS\node.exe" .\node_modules\next\dist\bin\next build
```

Current verified state:

```text
Backend tests: 22 passed
Frontend build: successful
```

## GitHub Safety

Do not commit:

- `backend/.env`
- local SQLite database files
- `.venv`
- `node_modules`
- `.next`

These are already covered by `.gitignore`.

## Disclaimer

This is not financial advice. It is for research and decision support only. The app does not place trades, manage brokerage accounts, or provide personalized investment advice.
