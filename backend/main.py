"""
main.py
─────────────────────────────────────────────────────────────────
FastAPI Entrypoint (iTunes + Deezer Hybrid)
"""

import os
import logging
import asyncio
from dataclasses import asdict
from contextlib import asynccontextmanager

import httpx
import pylast
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# 알고리즘 모듈 임포트 (파일 이름이 recommend_algo.py여야 함)
from recommend_algo import (
    opposite_emotion,
    reverse_top100,
    similar_listening_pattern,
    hidden_discovery,
    normalize_input,
)

# .env 파일 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

class RecommendRequest(BaseModel):
    query: str
    top_n: int = 10

class RecommendResponse(BaseModel):
    track_name: str
    artist: str
    top_n: int
    result: dict

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 환경 변수에서 Last.fm API 키 로드
    lastfm_key = os.getenv("LASTFM_API_KEY")
    if not lastfm_key:
        logger.warning("LASTFM_API_KEY가 .env에 없습니다. Last.fm 로직이 실패할 수 있습니다.")
    
    # 2. 비동기 HTTP 클라이언트 (iTunes, Deezer 통신용)
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(10.0),
        limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
    )
    
    app.state.http = http_client
    app.state.lastfm = pylast.LastFMNetwork(api_key=lastfm_key)
    
    logger.info("Lifespan: API Clients initialized (iTunes/Deezer Hybrid Mode)")
    try:
        yield
    finally:
        await http_client.aclose()

app = FastAPI(title="Music Discovery Hybrid API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok", "mode": "hybrid_itunes_deezer"}

@app.post("/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest):
    logger.info(f"Request: '{req.query}'")
    
    http = app.state.http
    lf = app.state.lastfm

    # 1. 정규화 (iTunes API 사용 - 매우 빠름)
    name, artist, _ = await normalize_input(req.query, http, lf)

    if not name or not artist:
        logger.warning(f"No results found for query: {req.query}")
        return RecommendResponse(
            track_name=req.query, artist="Unknown", top_n=req.top_n,
            result={"similar":[], "reverse":[], "opposite":[], "hidden":[]}
        )

    # 2. 4가지 알고리즘 병렬 실행
    raw_results = await asyncio.gather(
        similar_listening_pattern(name, artist, http, lf, top_n=req.top_n),
        reverse_top100(name, artist, http, lf, top_n=req.top_n),
        opposite_emotion(name, artist, http, lf, top_n=req.top_n),
        hidden_discovery(name, artist, http, lf, top_n=req.top_n),
        return_exceptions=True,
    )

    processed_results = []
    for res in raw_results:
        if isinstance(res, Exception):
            logger.error(f"Algorithm Failure: {res}", exc_info=True)
            processed_results.append([])
        else:
            processed_results.append([asdict(t) for t in res])

    return RecommendResponse(
        track_name=name,
        artist=artist,
        top_n=req.top_n,
        result={
            "similar":  processed_results[0],
            "reverse":  processed_results[1],
            "opposite": processed_results[2],
            "hidden":   processed_results[3],
        }
    )