import asyncio
import logging
from dataclasses import asdict

import pylast
import requests
import spotipy
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from requests.adapters import HTTPAdapter
from spotipy.oauth2 import SpotifyClientCredentials
from urllib3.util.retry import Retry

from recommend_algo import (
    hidden_discovery,
    normalize_input,
    opposite_emotion,
    reverse_top100,
    similar_listening_pattern,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    top_n: int = Field(default=10, ge=1, le=50)


class RecommendResponse(BaseModel):
    track_name: str
    artist: str
    top_n: int
    result: dict
    spotify_id: str | None = None
    album_art_url: str | None = None


@router.post("/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest, request: Request):
    try:
        sp, lf = _get_recommend_clients(request)
    except RuntimeError as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "service_unavailable", "detail": str(exc)},
        )

    logger.info("추천 요청 수신 - query: '%s', top_n: %d", req.query, req.top_n)

    track_name, artist, spotify_id = await normalize_input(req.query, sp, lf)
    if not track_name or not artist:
        logger.warning("추천 기준 트랙 검색 결과 없음: %s", req.query)
        return RecommendResponse(
            track_name=req.query,
            artist="Unknown",
            top_n=req.top_n,
            spotify_id=None,
            album_art_url=None,
            result={"similar": [], "reverse": [], "opposite": [], "hidden": []},
        )

    album_art_url = None
    if spotify_id:
        try:
            track_info = await asyncio.to_thread(sp.track, spotify_id)
            images = track_info["album"]["images"]
            album_art_url = images[0]["url"] if images else None
        except Exception as exc:
            logger.warning("기준 트랙 앨범 아트 조회 실패: %s", exc)

    raw_results = await asyncio.gather(
        similar_listening_pattern(track_name, artist, sp, lf, top_n=req.top_n),
        reverse_top100(track_name, artist, sp, lf, top_n=req.top_n),
        opposite_emotion(track_name, artist, sp, lf, top_n=req.top_n),
        hidden_discovery(track_name, artist, sp, lf, top_n=req.top_n),
        return_exceptions=True,
    )

    processed_results = []
    for result in raw_results:
        if isinstance(result, Exception):
            logger.error("Critical recommendation algorithm error: %s", result, exc_info=True)
            processed_results.append([])
        else:
            processed_results.append([asdict(track) for track in result])

    payload = {
        "similar": processed_results[0],
        "reverse": processed_results[1],
        "opposite": processed_results[2],
        "hidden": processed_results[3],
    }

    if not any(payload.values()):
        logger.warning(
            "추천 결과가 모든 알고리즘에서 비어있습니다. 입력: %s - %s",
            track_name,
            artist,
        )

    return RecommendResponse(
        track_name=track_name,
        artist=artist,
        top_n=req.top_n,
        spotify_id=spotify_id,
        album_art_url=album_art_url,
        result=payload,
    )


def _get_recommend_clients(request: Request) -> tuple[spotipy.Spotify, pylast.LastFMNetwork]:
    state = request.app.state
    spotify_client = getattr(state, "recommend_spotify", None)
    lastfm_client = getattr(state, "recommend_lastfm", None)
    if spotify_client and lastfm_client:
        return spotify_client, lastfm_client

    settings = state.settings
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        raise RuntimeError("Spotify credentials are not configured.")
    if not settings.lastfm_api_key or not settings.lastfm_api_secret:
        raise RuntimeError("Last.fm credentials are not configured.")

    session = requests.Session()
    adapter = HTTPAdapter(
        pool_connections=50,
        pool_maxsize=50,
        max_retries=Retry(total=3, backoff_factor=1),
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    state.recommend_spotify = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=settings.spotify_client_id,
            client_secret=settings.spotify_client_secret,
        ),
        requests_session=session,
    )
    state.recommend_lastfm = pylast.LastFMNetwork(
        api_key=settings.lastfm_api_key,
        api_secret=settings.lastfm_api_secret,
    )
    return state.recommend_spotify, state.recommend_lastfm
