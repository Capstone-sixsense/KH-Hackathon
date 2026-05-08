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
from dataclasses import asdict

import pylast
import spotipy
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from spotipy.oauth2 import SpotifyClientCredentials

import requests
from requests.adapters import HTTPAdapter

from recommend_algo import (
    opposite_emotion,
    reverse_top100,
    similar_listening_pattern,
)

# ── 로깅 설정 ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── FastAPI 앱 초기화 ──────────────────────────────────────────
app = FastAPI(
    title="Music Discovery API",
    description="Last.fm + Spotify 기반 소수 콘텐츠 음악 추천",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 배포 시 Flutter 도메인으로 제한
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 외부 API 클라이언트 초기화 ────────────────────────────────
def _init_spotify() -> spotipy.Spotify:
    return spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=os.environ["SPOTIFY_CLIENT_ID"],
            client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
        )
    )

def _init_lastfm() -> pylast.LastFMNetwork:
    return pylast.LastFMNetwork(
        api_key=os.environ["LASTFM_API_KEY"],
        api_secret=os.environ["LASTFM_API_SECRET"],
    )

sp = _init_spotify()
lf = _init_lastfm()

# ════════════════════════════════════════════════════════════════
# 요청 / 응답 스키마
# ════════════════════════════════════════════════════════════════

class RecommendRequest(BaseModel):
    track_name: str    # 기준 트랙명
    artist:     str    # 기준 아티스트명
    top_n:      int = 10   # 알고리즘별 반환 트랙 수 (기본 10)


class RecommendResponse(BaseModel):
    track_name: str
    artist:     str
    top_n:      int
    result: dict       # 3가지 알고리즘 결과를 담는 컨테이너


# ════════════════════════════════════════════════════════════════
# 엔드포인트
# ════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    """컨테이너 헬스체크용"""
    return {"status": "ok"}


@app.post("/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest):
    """
    3가지 알고리즘을 병렬 실행해 결과를 하나의 result에 담아 반환.

    result 구조:
        {
            "similar":   [...],   # 유사 청취 패턴
            "reverse":   [...],   # Reverse Top 100
            "opposite":  [...],   # 반대 감성
        }
    각 리스트의 원소는 TrackInfo 필드를 그대로 직렬화한 dict.
    """
    logger.info(
        "추천 요청 수신 — track: '%s', artist: '%s', top_n: %d",
        req.track_name, req.artist, req.top_n,
    )

    # ── 3가지 알고리즘 병렬 실행 ─────────────────────────────────
    import asyncio

    raw_results = await asyncio.gather(
        similar_listening_pattern(req.track_name, req.artist, sp, lf, top_n=req.top_n),
        reverse_top100(req.track_name, req.artist, sp, lf, top_n=req.top_n),
        opposite_emotion(req.track_name, req.artist, sp, lf, top_n=req.top_n),
        return_exceptions=True,
    )

    # ── 예외 처리 로직 보강 ──
    processed_results = []
    for res in raw_results:
        if isinstance(res, Exception):
            # [수정 1] exc_info=True를 추가하여 에러 스택트레이스를 상세히 기록
            logger.error(f"Critical Algo Error: {res}", exc_info=True)
            processed_results.append([])
        else:
            # [수정 2] TrackInfo 객체 리스트를 dict 리스트로 변환
            processed_results.append([asdict(t) for t in res])

    result = {
        "similar":  processed_results[0],
        "reverse":  processed_results[1],
        "opposite": processed_results[2],
    }

    logger.info(
        "추천 완료 — similar: %d개, reverse: %d개, opposite: %d개",
        len(result["similar"]),
        len(result["reverse"]),
        len(result["opposite"]),
    )

    # 모든 알고리즘이 빈 결과를 낼 경우에 대한 로깅
    if not any(len(v) > 0 for v in result.values()):
        logger.warning("검색 결과가 모든 알고리즘에서 비어있습니다. (입력: %s - %s)", req.track_name, req.artist)

    return RecommendResponse(
        track_name=req.track_name,
        artist=req.artist,
        top_n=req.top_n,
        result=result,
    )


