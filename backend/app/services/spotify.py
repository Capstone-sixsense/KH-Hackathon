import time
from typing import Any

import httpx

from app.pipeline.errors import ServiceUnavailableError
from app.schemas.search import CandidateTrack


class SpotifyClient:
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    API_BASE = "https://api.spotify.com/v1"

    def __init__(
        self,
        client_id: str | None,
        client_secret: str | None,
        http: httpx.AsyncClient,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.http = http
        self._token: str | None = None
        self._token_expires_at = 0.0

    async def _get_token(self) -> str:
        if not self.client_id or not self.client_secret:
            raise ServiceUnavailableError("Spotify credentials are not configured.")

        now = time.monotonic()
        if self._token and now < self._token_expires_at:
            return self._token

        response = await self.http.post(
            self.TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ServiceUnavailableError(_spotify_error_detail(exc, "Spotify token request failed.")) from exc
        payload = response.json()
        token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3600))
        self._token = token
        self._token_expires_at = now + max(expires_in - 60, 60)
        return token

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        token = await self._get_token()
        response = await self.http.get(
            f"{self.API_BASE}{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ServiceUnavailableError(_spotify_error_detail(exc, "Spotify API request failed.")) from exc
        return response.json()

    async def search_tracks(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 5))
        payload = await self._get(
            "/search",
            params={"q": query, "type": "track", "limit": safe_limit},
        )
        items = payload.get("tracks", {}).get("items", [])
        return items if isinstance(items, list) else []

    async def get_track(self, spotify_id: str) -> dict[str, Any]:
        return await self._get(f"/tracks/{spotify_id}")

    async def search_track_by_artist_title(self, artist: str, title: str) -> dict[str, Any] | None:
        query = f"track:{title} artist:{artist}"
        items = await self.search_tracks(query, limit=1)
        if items:
            return items[0]

        fallback_items = await self.search_tracks(f"{title} {artist}", limit=1)
        return fallback_items[0] if fallback_items else None

    @staticmethod
    def normalize_track(track: dict[str, Any]) -> CandidateTrack | None:
        spotify_id = str(track.get("id") or "")
        title = str(track.get("name") or "")
        artists = track.get("artists") or []
        artist = str(artists[0].get("name") or "") if artists else ""
        album = track.get("album") or {}
        images = album.get("images") or []
        album_art = str(images[0].get("url") or "") if images else ""
        popularity = int(track.get("popularity") or 0)

        if not spotify_id or not title or not artist or not album_art:
            return None

        return CandidateTrack(
            spotifyId=spotify_id,
            artist=artist,
            title=title,
            albumArt=album_art,
            popularity=max(0, min(popularity, 100)),
            tags=[],
        )


def _spotify_error_detail(exc: httpx.HTTPStatusError, fallback: str) -> str:
    text = exc.response.text.strip()
    if text:
        return f"{fallback} {exc.response.status_code}: {text[:300]}"
    return f"{fallback} {exc.response.status_code}"
