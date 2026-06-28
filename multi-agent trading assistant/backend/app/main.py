from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from .database import get_analysis, init_db, list_analyses, save_analysis
from .graph import run_analysis_graph
from .models import AnalysisResponse, AnalysisSummary, AnalyzeRequest


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Financial Trading Assistant API", version="0.1.0", lifespan=lifespan)

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin, "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalysisResponse)
def analyze(request: AnalyzeRequest) -> AnalysisResponse:
    state = run_analysis_graph(request)
    analysis_id = save_analysis(
        request=request,
        final=state["final"],
        market=state["market_data"],
        news=state["news_sentiment"],
        fundamentals=state["fundamentals"],
        critic=state["critic"],
        sources=state.get("sources", []),
        metrics=state.get("metrics", {}),
        candles=state.get("candles", []),
    )
    response = get_analysis(analysis_id)
    if response is None:
        raise HTTPException(status_code=500, detail="Analysis was saved but could not be loaded.")
    return response


@app.get("/analyses", response_model=list[AnalysisSummary])
def analyses() -> list[AnalysisSummary]:
    return list_analyses()


@app.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
def analysis_detail(analysis_id: int) -> AnalysisResponse:
    response = get_analysis(analysis_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return response
