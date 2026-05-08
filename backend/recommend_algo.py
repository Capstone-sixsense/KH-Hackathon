"""
recommend_algo.py (iTunes + Deezer Hybrid Version)
─────────────────────────────────────────────────────────────────
Normalization: iTunes API (No Key, High Speed)
Enrichment: Deezer API (No Key, High Metadata)
Algorithm: Last.fm (Key via .env)
"""

import asyncio
import logging
import math
import random
import re
from dataclasses import dataclass, field

import pylast
import httpx

logger = logging.getLogger(__name__)

# API 엔드포인트 설정
ITUNES_URL = "https://itunes.apple.com/search"
DEEZER_URL = "https://api.deezer.com"
_API_SEMAPHORE = asyncio.Semaphore(25)

@dataclass
class TrackInfo:
    name:          str
    artist:        str
    spotify_id:    str  | None = None   # Deezer/iTunes ID 저장 (호환성 유지)
    album_art_url: str  | None = None
    popularity:    int  | None = None   # Deezer Rank -> 0~100 변환
    match_score:   float| None = None   
    reverse_score: float| None = None   
    algo:          str         = ""     
    label:         str         = ""     
    reason_tags:   list[str]   = field(default_factory=list)  

# ── 헬퍼 함수: iTunes (Normalization용) ────────────────────────

async def normalize_input(query: str, http: httpx.AsyncClient, lastfm: pylast.LastFMNetwork) -> tuple[str, str, str] | tuple[None, None, None]:
    """iTunes API를 사용하여 가장 정확한 곡명과 아티스트명을 확보합니다."""
    try:
        async with _API_SEMAPHORE:
            # iTunes는 track이 아닌 term 파라미터를 사용하며 응답이 매우 빠릅니다.
            params = {"term": query, "entity": "song", "limit": 1}
            response = await http.get(ITUNES_URL, params=params, timeout=5.0)
            data = response.json()
            if data.get("resultCount", 0) > 0:
                track = data["results"][0]
                name = track["trackName"]
                artist = track["artistName"]
                track_id = str(track["trackId"])
                logger.info(f"[Normalize] iTunes 성공: {name} - {artist}")
                return name, artist, track_id
    except Exception as e:
        logger.error(f"[Normalize] iTunes 실패: {e}")
    
    # iTunes 실패 시 Last.fm으로 Fallback
    try:
        search = lastfm.search_for_track("", query)
        results = await asyncio.to_thread(search.get_next_page)
        if results:
            t = results[0]
            return t.get_name(), t.get_artist().get_name(), None
    except: pass
    return None, None, None

# ── 헬퍼 함수: Deezer (Enrichment용) ───────────────────────────

async def _dz_search(http: httpx.AsyncClient, track_name: str, artist: str) -> dict | None:
    """Deezer에서 트랙의 상세 정보(Rank, Album Art)를 가져옵니다."""
    clean_name = re.sub(r'\(.*?\)|\[.*?\]', '', track_name).strip()
    query = f'track:"{clean_name}" artist:"{artist}"'
    
    try:
        async with _API_SEMAPHORE:
            response = await http.get(f"{DEEZER_URL}/search", params={"q": query}, timeout=5.0)
            items = response.json().get("data", [])
            if not items:
                # 결과 없을 시 일반 텍스트 검색 시도
                response = await http.get(f"{DEEZER_URL}/search", params={"q": f"{clean_name} {artist}"}, timeout=5.0)
                items = response.json().get("data", [])
            return items[0] if items else None
    except Exception as e:
        logger.warning(f"[Deezer] 호출 실패: {e}")
    return None

async def _enrich_metadata(http: httpx.AsyncClient, tracks: list[TrackInfo]) -> list[TrackInfo]:
    """TrackInfo 리스트에 Deezer 메타데이터를 보강합니다."""
    async def _fetch(track: TrackInfo) -> TrackInfo:
        item = await _dz_search(http, track.name, track.artist)
        if item:
            track.spotify_id = str(item.get("id"))
            rank = item.get("rank", 0)
            # Deezer rank(약 100만 단위)를 0~100 스케일로 압축
            track.popularity = min(100, int(math.log10(rank + 1) * 10)) if rank > 0 else 0
            track.album_art_url = (item.get("album") or {}).get("cover_medium")
        return track
    return list(await asyncio.gather(*[_fetch(t) for t in tracks]))

# ── 추천 알고리즘 엔진 ──────────────────────────────────────────

def _cap_per_artist(tracks: list[TrackInfo], max_per: int = 1) -> list[TrackInfo]:
    seen = {}
    result = []
    for t in tracks:
        key = t.artist.lower()
        if seen.get(key, 0) < max_per:
            seen[key] = seen.get(key, 0) + 1
            result.append(t)
    return result

async def reverse_top100(track_name, artist, http, lastfm, top_n=10) -> list[TrackInfo]:
    """인기도가 낮은(비주류) 유사 음악 발굴"""
    try:
        lf_track = lastfm.get_track(artist, track_name)
        raw_similar = await asyncio.to_thread(lf_track.get_similar, limit=40)
        pool = [TrackInfo(name=i.item.get_name(), artist=i.item.get_artist().get_name(), match_score=float(i.match)) for i in raw_similar]
        pool = await _enrich_metadata(http, pool)
        
        # 인기도 65 미만의 곡들 중 마이너 점수가 높은 순
        pool = [t for t in pool if (t.popularity or 0) < 65]
        for t in pool:
            t.reverse_score = ((1 - (t.popularity or 0)/100) * 0.7) + ((t.match_score or 0) * 0.3)
            
        ranked = sorted(pool, key=lambda x: x.reverse_score or 0, reverse=True)[:top_n]
        for t in ranked: t.algo, t.label = "reverse_top100", "알고리즘이 밀어낸 유사 음악"
        return ranked
    except: return []

async def similar_listening_pattern(track_name, artist, http, lastfm, top_n=10) -> list[TrackInfo]:
    """가장 대중적인 유사 청취 패턴 기반 추천"""
    try:
        lf_track = lastfm.get_track(artist, track_name)
        raw_similar = await asyncio.to_thread(lf_track.get_similar, limit=40)
        pool = [TrackInfo(name=i.item.get_name(), artist=i.item.get_artist().get_name(), match_score=float(i.match)) for i in raw_similar]
        pool = await _enrich_metadata(http, pool)
        
        for t in pool: t.reverse_score = t.match_score or 0
        ranked = sorted(pool, key=lambda x: x.reverse_score or 0, reverse=True)[:top_n]
        for t in ranked: t.algo, t.label = "similar_listening_pattern", "비슷한 취향의 사람들이 들어요"
        return ranked
    except: return []

async def opposite_emotion(track_name, artist, http, lastfm, top_n=10) -> list[TrackInfo]:
    """곡의 메인 태그를 활용한 무드 기반 추천"""
    try:
        lf_track = lastfm.get_track(artist, track_name)
        tags = await asyncio.to_thread(lf_track.get_top_tags)
        if not tags: return []
        
        tag_name = tags[0].item.get_name()
        raw = await asyncio.to_thread(lastfm.get_tag(tag_name).get_top_tracks, limit=top_n*2)
        pool = [TrackInfo(name=i.item.get_name(), artist=i.item.get_artist().get_name()) for i in raw]
        pool = await _enrich_metadata(http, pool)
        
        ranked = _cap_per_artist(pool)[:top_n]
        for t in ranked: t.algo, t.label = "opposite_emotion", f"#{tag_name} 무드 추천"
        return ranked
    except: return []

async def hidden_discovery(track_name, artist, http, lastfm, top_n=10) -> list[TrackInfo]:
    """동일 아티스트의 곡 중 인기도가 낮은 숨은 명곡 발굴"""
    try:
        lf_artist = lastfm.get_artist(artist)
        raw = await asyncio.to_thread(lf_artist.get_top_tracks, limit=top_n*3)
        pool = [TrackInfo(name=i.item.get_name(), artist=i.item.get_artist().get_name()) for i in raw]
        pool = await _enrich_metadata(http, pool)
        
        # 인기도가 낮을수록 점수 높음
        pool = [t for t in pool if (t.popularity or 0) < 45]
        ranked = sorted(pool, key=lambda x: x.popularity or 100)[:top_n]
        for t in ranked: t.algo, t.label = "hidden_discovery", "나만 알고 싶은 숨겨진 명곡"
        return ranked
    except: return []
