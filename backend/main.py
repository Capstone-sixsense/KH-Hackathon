"""
main.py
─────────────────────────────────────────────────────────────────
FastAPI 엔트리포인트

엔드포인트:
    GET  /health                       상태 확인
    POST /recommend                    3가지 알고리즘 추천 결과 반환
"""

import logging
import os
import asyncio
from dataclasses import asdict

import pylast
import spotipy
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from spotipy.oauth2 import SpotifyClientCredentials
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from recommend_algo import (
    opposite_emotion,
    reverse_top100,
    similar_listening_pattern,
    hidden_discovery,
    normalize_input, # 통합된 함수 임포트
)

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Music Discovery API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def _init_spotify() -> spotipy.Spotify:
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=50, pool_maxsize=50, max_retries=Retry(total=3, backoff_factor=1))
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=os.environ["SPOTIFY_CLIENT_ID"],
            client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
        ),
        requests_session=session
    )

def _init_lastfm() -> pylast.LastFMNetwork:
    return pylast.LastFMNetwork(api_key=os.environ["LASTFM_API_KEY"], api_secret=os.environ["LASTFM_API_SECRET"])

sp = _init_spotify()
lf = _init_lastfm()

class RecommendRequest(BaseModel):
    query: str    # 단일 검색어
    top_n: int = 10

class RecommendResponse(BaseModel):
    track_name: str
    artist:     str
    top_n:      int
    result:     dict
    spotify_id:    str | None  # 추가 — 기준 트랙 Spotify ID
    album_art_url: str | None  # 추가 — 기준 트랙 앨범 아트

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest):
    logger.info(f"추천 요청 수신 — Query: '{req.query}'")

    # 1. 입력 정규화 (단일 키워드 -> 공식 정보)
    # normalize_input에 lf 인자 추가
    name, artist, spotify_id = await normalize_input(req.query, sp, lf)

    if not name or not artist:
        logger.warning(f"검색 결과 없음: {req.query}")
        return RecommendResponse(
            track_name=req.query, artist="Unknown",
            spotify_id=None, album_art_url=None,
            top_n=req.top_n,
            result={"similar": [], "reverse": [], "opposite": [], "hidden": []}
        )

    # 기준 트랙 앨범 아트 조회 (spotify_id로 직접 조회)
    album_art_url = None
    try:
        track_info = await asyncio.to_thread(sp.track, spotify_id)
        images = track_info["album"]["images"]
        album_art_url = images[0]["url"] if images else None
    except Exception as e:
        logger.warning("기준 트랙 앨범 아트 조회 실패: %s", e)

    # 2. 4가지 알고리즘 병렬 실행
    raw_results = await asyncio.gather(
        similar_listening_pattern(name, artist, sp, lf, top_n=req.top_n),
        reverse_top100(name, artist, sp, lf, top_n=req.top_n),
        opposite_emotion(name, artist, sp, lf, top_n=req.top_n),
        hidden_discovery(name, artist, sp, lf, top_n=req.top_n),
        return_exceptions=True,
    )

    processed_results = []
    for res in raw_results:
        if isinstance(res, Exception):
            logger.error(f"Algo Error: {res}", exc_info=True)
            processed_results.append([])
        else:
            processed_results.append([asdict(t) for t in res])

    result = {
        "similar":  processed_results[0],
        "reverse":  processed_results[1],
        "opposite": processed_results[2],
        "hidden":   processed_results[3],
    }

    return RecommendResponse(
        track_name=name,
        artist=artist,
        spotify_id=spotify_id,       # 추가
        album_art_url=album_art_url, # 추가
        top_n=req.top_n,
        result=result,
    )


