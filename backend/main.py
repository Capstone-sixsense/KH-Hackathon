from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.config import get_settings
from app.routers.recommend import router as recommend_router
from app.routers.search import router as search_router
from app.services.lastfm import LastFmClient
from app.services.llm import GeminiClient
from app.services.spotify import SpotifyClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    http = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout_seconds),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )
    app.state.settings = settings
    app.state.http = http
    app.state.spotify = SpotifyClient(
        client_id=settings.spotify_client_id,
        client_secret=settings.spotify_client_secret,
        http=http,
    )
    app.state.lastfm = LastFmClient(api_key=settings.lastfm_api_key, http=http)
    app.state.llm = GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        http=http,
    )
    try:
        yield
    finally:
        await http.aclose()


app = FastAPI(title="KH-Hackathon API", lifespan=lifespan)
app.include_router(search_router)
app.include_router(recommend_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "KH-Hackathon API", "status": "ok"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return health()
