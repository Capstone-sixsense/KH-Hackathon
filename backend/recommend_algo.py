"""
recommend_algo.py
─────────────────────────────────────────────────────────────────
음악 추천 알고리즘 모음

호출 예시 (main.py):
    from recommend_algo import reverse_top100, similar_listening_pattern

    result = await reverse_top100(
        track_name="너랑나",
        artist="IU",
        sp=spotify_client,
        lastfm=lastfm_network,
    )
"""

import asyncio
import logging
import math
import random
import re
import time
from dataclasses import dataclass, field

import pylast
import spotipy

logger = logging.getLogger(__name__)

# 동시에 진행할 Spotify 개별 트랙 검색 수를 제한해 429 rate limit 방지
_SP_SEMAPHORE = asyncio.Semaphore(15)
_SP_RATE_LIMIT_UNTIL = 0.0

GENERIC_SCORING_TAGS = {"k-pop", "korean", "pop", "seen live", "japanese", "j-pop"}
TAG_BLACKLIST_PATTERNS = [
    r"^\d{4}s?$",
    r"best of \d{4}",
    r"^top\b",
    r"^chart",
    r"^favorite",
    r"^loved",
    r"^my ",
    r"^seen live",
]


# ════════════════════════════════════════════════════════════════
# 공통 데이터 클래스
# ════════════════════════════════════════════════════════════════

@dataclass
class TrackInfo:
    """알고리즘이 반환하는 공통 트랙 정보"""
    name:          str
    artist:        str
    spotify_id:    str  | None = None
    album_art_url: str  | None = None
    popularity:    int  | None = None   # Spotify 0~100
    match_score:   float| None = None   # Last.fm getSimilar 유사도 0~1
    tag_rank:      int  | None = None   # 태그 내 순위 (1-based)
    reverse_score: float| None = None   # Reverse Top 100 최종 점수
    algo:          str         = ""     # 알고리즘 식별자
    label:         str         = ""     # 프론트 표시용 레이블
    reason_tags:   list[str]   = field(default_factory=list)  # 추천 근거 태그
    artist_listeners: int | None = None  # Last.fm 아티스트 전체 리스너 수
    artist_spotify_popularity: int | None = None   # Spotify 아티스트 popularity 0~100
    artist_spotify_followers:  int | None = None   # Spotify 아티스트 팔로워 수


# ════════════════════════════════════════════════════════════════
# 내부 헬퍼
# ════════════════════════════════════════════════════════════════

def _get_safe_top_tags(lf_track, limit=3) -> list[str]:
    """공통 태그 수집 헬퍼 (예외 처리 강화)"""
    try:
        # 동기 호출이므로 thread에서 실행됨을 가정
        top_tag_objs = lf_track.get_top_tags()
        return [t.item.get_name() for t in top_tag_objs[:limit]]
    except Exception as e:
        logger.warning("태그 수집 실패: %s", e)
        return []


def get_scoring_tag(tags: list[str]) -> str:
    """추천 기준 태그는 일반 태그보다 구체 태그를 우선한다."""
    specific = [tag for tag in tags if tag.lower().strip() not in GENERIC_SCORING_TAGS]
    return specific[0] if specific else (tags[0] if tags else "pop")


def _specific_first_tags(tags: list[str], limit: int) -> list[str]:
    specific = [tag for tag in tags if tag.lower().strip() not in GENERIC_SCORING_TAGS]
    generic = [tag for tag in tags if tag.lower().strip() in GENERIC_SCORING_TAGS]
    return (specific + generic)[:limit]


def _is_blacklisted_tag(tag: str, artist: str) -> bool:
    normalized = tag.lower().strip()
    if artist.lower() in normalized:
        return True
    return any(re.search(pattern, normalized) for pattern in TAG_BLACKLIST_PATTERNS)


def _mark_spotify_search_rate_limited(exc: spotipy.SpotifyException) -> None:
    global _SP_RATE_LIMIT_UNTIL
    retry_after = int(getattr(exc, "headers", {}).get("Retry-After", 60))
    _SP_RATE_LIMIT_UNTIL = max(_SP_RATE_LIMIT_UNTIL, time.monotonic() + retry_after)
    logger.warning(
        "Spotify Search rate limit 감지 — %d초 동안 Spotify Search 보강 생략",
        retry_after,
    )


def _is_spotify_search_rate_limited() -> bool:
    return time.monotonic() < _SP_RATE_LIMIT_UNTIL


def _sp_search(sp: spotipy.Spotify, track_name: str, artist: str) -> dict | None:
    """Spotify에서 트랙을 검색해 첫 번째 결과를 반환."""
    if _is_spotify_search_rate_limited():
        return None

    query = f"track:{track_name} artist:{artist}"
    try:
        results = sp.search(q=query, type="track", limit=1)
        items = results["tracks"]["items"]
        return items[0] if items else None
    except spotipy.SpotifyException as e:
        if e.http_status == 429:
            _mark_spotify_search_rate_limited(e)
            logger.warning("Spotify 429 rate limit — 후보 보강 생략 (%s - %s)", track_name, artist)
        else:
            logger.warning("Spotify 검색 실패 (%s - %s): %s", track_name, artist, e)
        return None
    except Exception as e:
        logger.warning("Spotify 검색 실패 (%s - %s): %s", track_name, artist, e)
        return None

async def normalize_input(
    query: str,
    sp: spotipy.Spotify,
    lastfm: pylast.LastFMNetwork,
    search_limit: int = 5,
) -> tuple[str, str, str] | tuple[None, None, None]:
    """Last.fm 검증 후보를 우선하되, 없으면 Spotify 첫 후보를 반환한다."""
    spotify_fallback: tuple[str, str, str] | None = None
    if not _is_spotify_search_rate_limited():
        try:
            results = await asyncio.to_thread(
                sp.search, q=query, type="track", limit=search_limit
            )
            items = results["tracks"]["items"]

            for track in items:
                name = str(track.get("name") or "")
                artists = track.get("artists") or []
                artist = str(artists[0].get("name") or "") if artists else ""
                track_id = str(track.get("id") or "")

                if not name or not artist or not track_id:
                    continue

                if spotify_fallback is None:
                    spotify_fallback = (name, artist, track_id)

                # Last.fm에 getSimilar 데이터가 있는지 검증
                try:
                    lf_track = lastfm.get_track(artist, name)
                    similar  = await asyncio.to_thread(lf_track.get_similar, limit=1)

                    if similar:   # 유사 트랙이 1개라도 있으면 사용 가능
                        logger.info(
                            "[Normalize] 최종 선택: '%s - %s' (Last.fm 검증 완료)",
                            name, artist,
                        )
                        return name, artist, track_id

                    logger.info(
                        "[Normalize] Last.fm 유사 트랙 없음, Spotify 후보 보류: '%s - %s'",
                        name, artist,
                    )
                except Exception:
                    logger.info(
                        "[Normalize] Last.fm 조회 실패, Spotify 후보 보류: '%s - %s'",
                        name, artist,
                    )
                    continue

            if spotify_fallback:
                logger.info(
                    "[Normalize] Last.fm 검증 후보 없음. Spotify 첫 후보로 fallback: '%s - %s'",
                    spotify_fallback[0], spotify_fallback[1],
                )
                return spotify_fallback

        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                _mark_spotify_search_rate_limited(e)
            logger.error("[Normalize] Spotify 검색 실패: %s", e)
        except Exception as e:
            logger.error("[Normalize] Spotify 검색 실패: %s", e)

    return await _normalize_input_with_lastfm(query, lastfm)


async def _normalize_input_with_lastfm(
    query: str,
    lastfm: pylast.LastFMNetwork,
) -> tuple[str, str, str | None] | tuple[None, None, None]:
    """Spotify Search 장애 시 Last.fm track.search로 기준 트랙을 찾는다."""
    try:
        results = await asyncio.to_thread(
            lambda: lastfm.search_for_track("", query).get_next_page()
        )
        for track in results:
            artist = str(getattr(track, "artist", "") or "").strip()
            name = str(getattr(track, "title", "") or track.get_name() or "").strip()
            if not artist or not name or _is_unknown_lastfm_artist(artist):
                continue
            name = _clean_lastfm_title(name, artist)
            logger.info(
                "[Normalize] Spotify 장애 fallback: Last.fm 후보 사용 '%s - %s'",
                name,
                artist,
            )
            return name, artist, None
    except Exception as e:
        logger.warning("[Normalize] Last.fm fallback 실패: %s", e)

    return None, None, None


def _is_unknown_lastfm_artist(artist: str) -> bool:
    normalized = artist.strip().lower()
    return normalized in {"[unknown]", "<unknown>", "unknown", "n/a"}


def _clean_lastfm_title(title: str, artist: str) -> str:
    cleaned = title.strip()
    for separator in (" - ", " – ", " — "):
        prefix = f"{artist}{separator}"
        if cleaned.lower().startswith(prefix.lower()):
            return cleaned[len(prefix):].strip() or cleaned
    return cleaned

async def _enrich_with_spotify(
    sp: spotipy.Spotify,
    tracks: list[TrackInfo],
) -> list[TrackInfo]:
    """
    TrackInfo 리스트에 Spotify 트랙/아티스트 정보를 병렬로 보강한다.

    트랙 검색: 트랙당 1회 병렬 호출 (기존과 동일)
    아티스트 정보: 고유 아티스트 ID를 모아 50개씩 배치 호출
                  → 개별 호출 대비 API 호출 수를 대폭 감소
    """
    # ── Step A. 트랙 정보 병렬 수집 ─────────────────────────────
    artist_id_by_idx: dict[int, str] = {}

    async def _fetch(idx: int, track: TrackInfo) -> TrackInfo:
        async with _SP_SEMAPHORE:
            item = await asyncio.to_thread(_sp_search, sp, track.name, track.artist)
        if item:
            track.spotify_id = item.get("id") or f"unknown_{track.name}"
            track.popularity = item.get("popularity")

            album = item.get("album") or {}
            images = album.get("images") or []
            track.album_art_url = images[0].get("url") if images else None

            artists = item.get("artists") or []
            artist_id = artists[0].get("id") if artists else None
            if artist_id:
                artist_id_by_idx[idx] = artist_id
        else:
            track.spotify_id = f"unknown_{track.name}"
            track.popularity = None
        return track

    tracks = list(await asyncio.gather(*[_fetch(i, t) for i, t in enumerate(tracks)]))

    # ── Step B. 아티스트 정보 배치 수집 (최대 50개/호출) ────────
    unique_ids = list(set(artist_id_by_idx.values()))
    artist_info: dict[str, dict] = {}

    for i in range(0, len(unique_ids), 50):
        batch = unique_ids[i : i + 50]
        try:
            result = await asyncio.to_thread(sp.artists, batch)
            for a in (result.get("artists") or []):
                if a:
                    artist_info[a["id"]] = a
        except Exception as e:
            logger.warning("아티스트 배치 조회 실패: %s", e)

    for idx, track in enumerate(tracks):
        aid = artist_id_by_idx.get(idx)
        if aid and aid in artist_info:
            track.artist_spotify_popularity = artist_info[aid]["popularity"]
            track.artist_spotify_followers  = artist_info[aid]["followers"]["total"]

    return tracks


def _deduplicate(tracks: list[TrackInfo]) -> list[TrackInfo]:
    """(소문자 name + artist) 기준 중복 제거."""
    seen = set()
    result = []
    for t in tracks:
        key = (t.name.lower(), t.artist.lower())
        if key not in seen:
            seen.add(key)
            result.append(t)
    return result


def _diverse_top_n(
    pool: list[TrackInfo],
    top_n: int,
    *,
    score_fn=lambda t: t.reverse_score or 0,
    diversity: float = 0.0,
    candidate_mult: int = 3,
) -> list[TrackInfo]:
    """
    diversity=0.0: 결정론적 상위 top_n 반환.
    diversity>0.0: 후보 풀(top_n × candidate_mult)에서 가우시안 노이즈 기반 샘플링.
                   diversity=0.3 권장 — 점수 우위는 유지하면서 매 실행마다 다른 결과.

    점수를 0~1로 정규화 후 노이즈를 더하므로 알고리즘 간 점수 스케일 차이에 무관.
    """
    if not pool:
        return []
    sorted_pool = sorted(pool, key=score_fn, reverse=True)
    if diversity <= 0.0:
        return sorted_pool[:top_n]

    n_candidates = min(len(pool), top_n * candidate_mult)
    candidates = sorted_pool[:n_candidates]

    raw_scores = [score_fn(t) for t in candidates]
    min_s, max_s = min(raw_scores), max(raw_scores)
    score_range = (max_s - min_s) or 1.0

    scored = [
        (t, (s - min_s) / score_range + random.gauss(0, diversity * 0.3))
        for t, s in zip(candidates, raw_scores)
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in scored[:top_n]]


def _cap_per_artist(tracks: list[TrackInfo], max_per: int = 1) -> list[TrackInfo]:
    """동일 아티스트가 max_per 곡 이상 포함되지 않도록 제한. (reverse_score 내림차순 기준)"""
    seen: dict[str, int] = {}
    result = []
    for t in tracks:
        key = t.artist.lower()
        if seen.get(key, 0) < max_per:
            seen[key] = seen.get(key, 0) + 1
            result.append(t)
    return result


async def _get_input_artist_popularity(sp: spotipy.Spotify, artist: str) -> int:
    """입력 아티스트의 Spotify popularity를 조회. 실패 시 기본값 55 반환."""
    if _is_spotify_search_rate_limited():
        return 55

    try:
        result = await asyncio.to_thread(
            sp.search, f"artist:{artist}", type="artist", limit=1
        )
        items = result["artists"]["items"]
        return items[0]["popularity"] if items else 55
    except Exception:
        return 55


def _lastfm_similar_to_trackinfo(similar_tracks) -> list[TrackInfo]:
    """pylast SimilarItem 리스트 → TrackInfo 리스트 변환."""
    result = []
    for item in similar_tracks:
        try:
            result.append(TrackInfo(
                name=item.item.get_name(),
                artist=item.item.get_artist().get_name(),
                match_score=float(item.match),
            ))
        except Exception as e:
            logger.debug("getSimilar 항목 변환 실패: %s", e)
    return result


def _lastfm_tag_tracks_to_trackinfo(tag_tracks, offset: int = 0) -> list[TrackInfo]:
    """pylast tag.getTopTracks 결과 → TrackInfo 리스트 변환."""
    result = []
    for rank, item in enumerate(tag_tracks, start=offset + 1):
        try:
            result.append(TrackInfo(
                name=item.item.get_name(),
                artist=item.item.get_artist().get_name(),
                tag_rank=rank,
            ))
        except Exception as e:
            logger.debug("tag track 변환 실패: %s", e)
    return result


# ════════════════════════════════════════════════════════════════
# Reverse Top 100 알고리즘
# ════════════════════════════════════════════════════════════════

async def reverse_top100(
    track_name: str,
    artist: str,
    sp: spotipy.Spotify,
    lastfm: pylast.LastFMNetwork,
    *,
    # ── 풀 구성 파라미터 ──────────────────────────────────────
    similar_limit:   int   = 50,    # getSimilar 가져올 수
    tag_limit:       int   = 50,    # tag.getTopTracks 가져올 수
    tag_start:       int   = 3,     # 태그 시작 인덱스 (상위 주류 태그 스킵)
    top_tags:        int   = 5,     # 사용할 태그 수
    # ── 필터 파라미터 ─────────────────────────────────────────
    pop_min:         int   = 5,     # popularity 하한 (유령 트랙 제외)
    pop_max:         int   = 50,    # popularity 상한 (이미 알려진 트랙 제외)
    match_threshold: float = 0.2,   # 음악적 유사도 최소값
    # ── 가중치 ───────────────────────────────────────────────
    w_popularity:    float = 0.5,   # (1 - popularity_norm) 가중치
    w_match:         float = 0.3,   # match_score 가중치
    w_tag_rank:      float = 0.2,   # (1 - tag_rank_norm) 가중치
    # ── 반환 개수 ─────────────────────────────────────────────
    top_n:           int   = 10,    # 반환할 트랙 수
    # ── 다양성 ───────────────────────────────────────────────
    diversity:       float = 0.3,   # 0=결정론적, 높을수록 매 실행 결과 다양
) -> list[TrackInfo]:
    """
    Reverse Top 100 알고리즘

    기존 플랫폼이 노출을 억제한 마이너 트랙을 발굴한다.
    음악적 연관성(match_score)은 유지하면서 popularity가 낮고
    태그 내 순위도 낮은 트랙에 높은 reverse_score를 부여한다.

    점수 계산:
        reverse_score = (1 - P_norm) * 0.5
                      + match_score  * 0.3
                      + (1 - R_norm) * 0.2

    Args:
        track_name:      기준 트랙명
        artist:          기준 아티스트명
        sp:              spotipy.Spotify 인스턴스
        lastfm:          pylast.LastFMNetwork 인스턴스
        similar_limit:   getSimilar 후보 수 (기본 50)
        tag_limit:       tag.getTopTracks 후보 수 (기본 50)
        top_tags:        기준 트랙의 상위 태그 사용 수 (기본 2)
        pop_min:         popularity 하한 (기본 5)
        tag_start:       기준 트랙 태그 중 사용할 시작 인덱스 (기본 3)
        pop_max:         popularity 상한 (기본 50)
        match_threshold: 유사도 최소값 (기본 0.2)
        w_popularity:    비인기도 가중치 (기본 0.5)
        w_match:         유사도 가중치 (기본 0.3)
        w_tag_rank:      태그 순위 가중치 (기본 0.2)

    Returns:
        list[TrackInfo]  reverse_score 내림차순 상위 10개 (후보 없을 시 [])
    """

    # ── Step 0. 입력 아티스트 인기도 기반 동적 파라미터 계산 ───────
    input_artist_pop = await _get_input_artist_popularity(sp, artist)

    # pop_max: 유명 아티스트일수록 낮춰서 더 마이너한 트랙만 허용
    #   공식: base + (60 - input_pop) * 0.2  →  clamp [35, 60]
    effective_pop_max      = int(max(35, min(60, pop_max + (60 - input_artist_pop) * 0.2)))
    # artist_pop_ceiling: 입력 아티스트 인기도와 무관하게 최대 50으로 상한
    #   공식: clamp [25, 50]  — 유명 입력 아티스트라도 ceiling을 과도하게 올리지 않음
    artist_pop_ceiling     = max(25, min(50, input_artist_pop - 25))

    logger.info(
        "[Reverse] 입력 아티스트 popularity=%d → pop_max=%d, artist_pop_ceiling=%d",
        input_artist_pop, effective_pop_max, artist_pop_ceiling,
    )

    # ── Step 1. 기준 트랙 Last.fm 태그 수집 ─────────────────────
    logger.info("[Reverse] 기준 트랙 태그 수집: %s - %s", track_name, artist)
    try:
        lf_track   = lastfm.get_track(artist, track_name)
        top_tag_objs = await asyncio.to_thread(lf_track.get_top_tags)
        filtered_tags = [
            t.item.get_name()
            for t in top_tag_objs
            if not _is_blacklisted_tag(t.item.get_name(), artist)
        ]
        candidate_tags = filtered_tags[tag_start : tag_start + top_tags] or filtered_tags[:top_tags]
        tag_names = _specific_first_tags(candidate_tags, top_tags)
    except Exception as e:
        logger.warning("[Reverse] 태그 수집 실패: %s", e)
        tag_names = []

    logger.info("[Reverse] 사용 태그: %s", tag_names)

    # ── Step 2. 풀 구성 (getSimilar + tag.getTopTracks 병렬) ────
    async def fetch_similar() -> list[TrackInfo]:
        try:
            raw = await asyncio.to_thread(
                lf_track.get_similar, limit=similar_limit
            )
            return _lastfm_similar_to_trackinfo(raw)
        except Exception as e:
            logger.warning("[Reverse] getSimilar 실패: %s", e)
            return []

    async def fetch_tag_tracks(tag: str, offset: int) -> list[TrackInfo]:
        try:
            lf_tag = lastfm.get_tag(tag)
            raw    = await asyncio.to_thread(lf_tag.get_top_tracks, limit=tag_limit)
            return _lastfm_tag_tracks_to_trackinfo(raw, offset=offset)
        except Exception as e:
            logger.warning("[Reverse] tag.getTopTracks 실패 (%s): %s", tag, e)
            return []

    tasks = [fetch_similar()] + [
        fetch_tag_tracks(tag, i * tag_limit)
        for i, tag in enumerate(tag_names)
    ]
    results      = await asyncio.gather(*tasks)
    similar_pool = results[0]
    tag_pools    = results[1:]

    # match_score가 없는 태그 트랙에 기본값 부여
    for pool in tag_pools:
        for t in pool:
            if t.match_score is None:
                t.match_score = 0.2

    pool = _deduplicate(similar_pool + [t for p in tag_pools for t in p])
    logger.info("[Reverse] 풀 구성 완료: %d개", len(pool))

    # match_threshold 동적 조정: 풀이 작을수록 완화
    if len(pool) >= 30:
        effective_match_threshold = match_threshold
    elif len(pool) >= 15:
        effective_match_threshold = max(0.1, match_threshold - 0.05)
    else:
        effective_match_threshold = max(0.1, match_threshold - 0.1)

    logger.info(
        "[Reverse] match_threshold: %.2f → %.2f (풀 %d개)",
        match_threshold, effective_match_threshold, len(pool),
    )

    # ── Step 3. Spotify 인기도 보강 (병렬) ──────────────────────
    # enrichment 전 match_score 상위 후보로 제한해 불필요한 API 호출 절감
    pool.sort(key=lambda t: t.match_score or 0, reverse=True)
    pool = pool[: top_n * 5]
    logger.info("[Reverse] enrichment 전 풀 제한: %d개", len(pool))
    pool = await _enrich_with_spotify(sp, pool)

    # ── Step 4. 필터 — 점진적 완화 (Progressive Relaxation) ────────
    # 4개 조건을 동시에 AND로 거는 방식은 교집합이 지나치게 작아질 수 있다.
    # 엄격한 파라미터로 시작해 결과가 top_n 미만이면 단계적으로 완화한다.
    # artist_listeners(Last.fm) 필터는 K-pop 과소평가 문제로 제외.
    #
    # 완화 레벨별 증감: (pop_max 증가, artist_pop_ceiling 증가, match 감소)
    # artist ceiling은 트랙 popularity보다 훨씬 보수적으로 완화한다.
    # reverse 알고리즘의 핵심 목적(무명 아티스트 발굴)을 지키기 위해
    # Level 0~2는 artist ceiling을 전혀 건드리지 않고, Level 3~4도 최소한만 올린다.
    _RELAX_STEPS = [
        ( 0,  0,  0.00),   # Level 0: 원래 파라미터
        ( 5,  0, -0.02),   # Level 1: track pop만 완화
        (10,  0, -0.05),   # Level 2: track pop만 완화
        (15,  3, -0.08),   # Level 3: artist ceiling +3
        (20,  5, -0.10),   # Level 4: artist ceiling +5 (최대)
    ]

    before = len(pool)
    filtered: list[TrackInfo] = []
    applied_level = 0

    for level, (pop_delta, ceil_delta, match_delta) in enumerate(_RELAX_STEPS):
        p_max   = min(70, effective_pop_max    + pop_delta)
        ceiling = min(55, artist_pop_ceiling   + ceil_delta)  # 절대 55 초과 불가
        m_thr   = max(0.05, effective_match_threshold + match_delta)

        filtered = [
            t for t in pool
            if (t.popularity is None or pop_min <= t.popularity <= p_max)
            and (t.artist_spotify_popularity is None or t.artist_spotify_popularity < ceiling)
            and (t.match_score or 0) >= m_thr
        ]
        applied_level = level
        if len(filtered) >= top_n:
            break

    pool = filtered
    logger.info(
        "[Reverse] 필터 후: %d개 (완화 레벨 %d, 제거 %d개)",
        len(pool), applied_level, before - len(pool),
    )

    if not pool:
        logger.warning("[Reverse] 최대 완화 후에도 후보 없음.")
        return []

    # ── Step 5. Reverse Score 계산 ───────────────────────────────
    original_tag_limit = tag_limit
    for t in pool:
        p_score = 1 - ((t.popularity or 0) / 100)
        m_score = t.match_score or 0
        # artist_spotify_popularity 기반 비인지도 점수 (낮을수록 마이너)
        a_score = max(0, 1 - ((t.artist_spotify_popularity or 0) / 100))
        if t.tag_rank:
            r_score = max(0, 1 - (t.tag_rank / original_tag_limit))
        else:
            r_score = 0.5

        t.reverse_score = (
            p_score * 0.3 +
            a_score * 0.4 +
            m_score * 0.2 +
            r_score * 0.1
        )

    # ── Step 6. 최종 선정 (아티스트 다양성 보장 후 상위 top_n) ────
    sorted_pool = sorted(pool, key=lambda t: t.reverse_score or 0, reverse=True)
    capped_pool = _cap_per_artist(sorted_pool, max_per=1)
    ranked = _diverse_top_n(capped_pool, top_n, diversity=diversity)

    for t in ranked:
        t.algo        = "reverse_top100"
        t.label       = "알고리즘이 밀어낸 유사 음악"
        t.reason_tags = tag_names

    logger.info("[Reverse] 선정 %d개:", len(ranked))
    for i, t in enumerate(ranked, 1):
        logger.info(
            "  %d. %s - %s (popularity=%s, reverse_score=%.3f)",
            i, t.name, t.artist, t.popularity, t.reverse_score or 0,
        )
    return ranked


# ════════════════════════════════════════════════════════════════
# 유사 청취 패턴 알고리즘
# ════════════════════════════════════════════════════════════════

def _get_lastfm_listeners(
    lastfm: pylast.LastFMNetwork,
    track_name: str,
    artist: str,
) -> int | None:
    """Last.fm 청취자 수 조회. 실패 시 None 반환."""
    try:
        lf_track = lastfm.get_track(artist, track_name)
        return int(lf_track.get_listener_count())
    except Exception:
        return None


async def similar_listening_pattern(
    track_name: str,
    artist: str,
    sp: spotipy.Spotify,
    lastfm: pylast.LastFMNetwork,
    *,
    # ── 풀 구성 파라미터 ──────────────────────────────────────
    similar_limit:   int   = 50,    # getSimilar 가져올 수
    # ── 필터 파라미터 ─────────────────────────────────────────
    pop_min:         int   = 20,    # 너무 마이너한 트랙 제외
    pop_max:         int   = 75,    # 메가 히트곡 제외
    match_threshold: float = 0.3,   # 청취 패턴 최소 유사도
    # ── 가중치 ───────────────────────────────────────────────
    w_match:         float = 0.6,   # Last.fm match_score (청취 패턴 유사도)
    w_listeners:     float = 0.4,   # Last.fm 청취자 수 (커뮤니티 검증)
    # ── 반환 개수 ─────────────────────────────────────────────
    top_n:           int   = 10,    # 반환할 트랙 수
    # ── 다양성 ───────────────────────────────────────────────
    diversity:       float = 0.3,   # 0=결정론적, 높을수록 매 실행 결과 다양
) -> list[TrackInfo]:
    """
    유사 청취 패턴 알고리즘

    Last.fm의 collaborative filtering 기반 getSimilar 를 핵심으로 사용한다.
    match_score 는 '같은 트랙을 들은 사람들이 얼마나 겹치는가'를 반영하므로
    단순 장르/태그 유사도가 아닌 실제 청취 행동 패턴의 유사도를 나타낸다.

    여기에 Last.fm 청취자 수를 보조 지표로 결합해
    '많은 사람들이 실제로 듣고 있는 유사 트랙'을 선정한다.

    Reverse Top 100과의 차이:
        - Reverse: popularity 낮을수록 우대 (마이너 발굴)
        - 유사 청취 패턴: match_score 높을수록 우대 (패턴 일치 극대화)
          popularity 범위도 20~75로 어느 정도 검증된 트랙 허용

    점수 계산:
        listen_score = match_score          * 0.6
                     + listeners_norm       * 0.4

    Args:
        track_name:      기준 트랙명
        artist:          기준 아티스트명
        sp:              spotipy.Spotify 인스턴스
        lastfm:          pylast.LastFMNetwork 인스턴스
        similar_limit:   getSimilar 후보 수 (기본 50)
        pop_min:         popularity 하한 (기본 20)
        pop_max:         popularity 상한 (기본 75)
        match_threshold: 청취 패턴 유사도 최소값 (기본 0.3)
        w_match:         match_score 가중치 (기본 0.6)
        w_listeners:     청취자 수 가중치 (기본 0.4)

    Returns:
        list[TrackInfo]  listen_score 내림차순 상위 10개 (후보 없을 시 [])
    """

    # ── Step 1. 기준 트랙 태그 수집 (레이블용) ─────────────────
    logger.info("[SimilarListening] 기준 트랙: %s - %s", track_name, artist)
    try:
        lf_track     = lastfm.get_track(artist, track_name)
        raw_tag_names = await asyncio.to_thread(_get_safe_top_tags, lf_track, 3)
        tag_names = _specific_first_tags(raw_tag_names, 3)
        top_tag_objs = await asyncio.to_thread(lf_track.get_top_tags)
        #tag_names    = [t.item.get_name() for t in top_tag_objs[:3]]
    except Exception as e:
        logger.warning("[SimilarListening] 태그 수집 실패: %s", e)
        lf_track  = lastfm.get_track(artist, track_name)
        tag_names = []

    # ── Step 2. getSimilar 로 풀 구성 ────────────────────────────
    # Last.fm getSimilar 는 청취자 overlap 기반 collaborative filtering.
    # match_score 가 높을수록 '같이 듣는 사람'이 많다는 의미.
    try:
        raw_similar = await asyncio.to_thread(
            lf_track.get_similar, limit=similar_limit
        )
        pool = _lastfm_similar_to_trackinfo(raw_similar)
    except Exception as e:
        logger.warning("[SimilarListening] getSimilar 실패: %s", e)
        return []

    logger.info("[SimilarListening] getSimilar 풀: %d개", len(pool))

    # ── Step 3. match_threshold 사전 필터 (Spotify 호출 전 절감) ─
    pool = [
        t for t in pool
        if (t.popularity is None or pop_min <= t.popularity <= pop_max)
    ]
    logger.info("[SimilarListening] match 필터 후: %d개", len(pool))

    if not pool:
        logger.warning("[SimilarListening] match_threshold 를 낮춰보세요.")
        return []

    # ── Step 4. Spotify 인기도 보강 (병렬) ──────────────────────
    pool = list(await _enrich_with_spotify(sp, pool))

    # ── Step 5. popularity 필터 ──────────────────────────────────
    before = len(pool)
    pool = [
        t for t in pool
        if (t.popularity is None or pop_min <= t.popularity <= pop_max)
    ]
    logger.info(
        "[SimilarListening] popularity 필터 후: %d개 (제거 %d개)",
        len(pool), before - len(pool),
    )

    if not pool:
        logger.warning("[SimilarListening] popularity 범위를 조정해보세요.")
        return []

    # ── Step 6. Last.fm 청취자 수 보강 (병렬) ────────────────────
    # 청취자 수는 '실제로 이 트랙을 찾아서 듣는 사람'의 규모를 나타냄.
    # Spotify popularity(최근 스트림 편향)와 달리 장기 누적 청취 행동을 반영.
    async def fetch_listeners(track: TrackInfo) -> TrackInfo:
        count = await asyncio.to_thread(
            _get_lastfm_listeners, lastfm, track.name, track.artist
        )
        track.tag_rank = count   # tag_rank 필드를 listeners 임시 저장소로 재활용
        return track

    pool = list(await asyncio.gather(*[fetch_listeners(t) for t in pool]))

    # ── Step 7. listen_score 계산 ────────────────────────────────
    # listeners 정규화: 풀 내 최댓값 기준
    max_listeners = max((t.tag_rank or 0) for t in pool) or 1

    for t in pool:
        listeners_norm = (t.tag_rank or 0) / max_listeners
        match          = t.match_score or 0

        t.reverse_score = (     # 공통 필드 재활용 (listen_score 저장)
            match          * w_match     +
            listeners_norm * w_listeners
        )

    # ── Step 8. 최종 선정 (아티스트 다양성 보장 후 상위 top_n) ────
    sorted_pool = sorted(pool, key=lambda t: t.reverse_score or 0, reverse=True)
    capped_pool = _cap_per_artist(sorted_pool, max_per=1)
    ranked      = _diverse_top_n(capped_pool, top_n, diversity=diversity)

    for t in ranked:
        t.algo        = "similar_listening_pattern"
        t.label       = "비슷한 취향의 사람들이 들어요"
        t.reason_tags = tag_names

    logger.info("[SimilarListening] 선정 %d개:", len(ranked))
    for i, t in enumerate(ranked, 1):
        logger.info(
            "  %d. %s - %s (match=%.3f, popularity=%s, listen_score=%.3f)",
            i, t.name, t.artist,
            t.match_score or 0, t.popularity, t.reverse_score or 0,
        )
    return ranked


# ════════════════════════════════════════════════════════════════
# 반대 감성 알고리즘
# ════════════════════════════════════════════════════════════════

# ── 반대 태그 매핑 테이블 ────────────────────────────────────────
# Last.fm 태그 기준으로 감성/분위기/장르의 대척점을 정의.
# 키: 원본 태그 (소문자), 값: 반대 태그 (Last.fm 검색용)
OPPOSITE_TAG_MAP: dict[str, str] = {
    # 감정·분위기
    "sad":          "happy",
    "happy":        "melancholic",
    "melancholic":  "upbeat",
    "upbeat":       "sad",
    "angry":        "calm",
    "calm":         "energetic",
    "energetic":    "calm",
    "dark":         "feel-good",
    "feel-good":    "dark",
    "romantic":     "aggressive",
    "aggressive":   "romantic",
    "lonely":       "euphoric",
    "euphoric":     "melancholic",
    "nostalgic":    "futuristic",
    "hopeful":      "hopeless",
    "dreamy":       "intense",
    "intense":      "dreamy",
    "peaceful":     "chaotic",
    "chaotic":      "peaceful",
    "emotional":    "chill",
    "chill":        "intense",

    # 템포·에너지
    "slow":         "fast",
    "fast":         "slow",
    "acoustic":     "electronic",
    "electronic":   "acoustic",
    "lo-fi":        "hi-fi",
    "mellow":       "energetic",

    # 장르 대척점
    "k-pop":        "indie-folk",
    "indie":        "mainstream",
    "mainstream":   "indie",
    "classical":    "hip-hop",
    "hip-hop":      "classical",
    "jazz":         "metal",
    "metal":        "jazz",
    "pop":          "ambient",
    "ambient":      "pop",
    "r-n-b":        "punk",
    "punk":         "r-n-b",
    "folk":         "electronic",
    "dance":        "acoustic",
    "soul":         "edm",
    "edm":          "soul",
    "rock":         "classical",
    "indie rock":   "k-pop",
    "ballad":       "dance",
    "korean":       "electronic",

    # 시간대·상황
    "late-night":   "morning",
    "morning":      "late-night",
    "rainy day":    "sunny",
    "sunny":        "rainy day",
    "summer":       "winter",
    "winter":       "summer",
    "party":        "meditation",
    "meditation":   "party",
    "workout":      "sleep",
    "sleep":        "workout",
}


def _find_opposite_tag(tags: list[str]) -> tuple[str, str] | None:
    """기준 트랙의 태그 리스트에서 매핑 가능한 첫 번째 반대 태그를 반환."""
    for tag in tags:
        normalized = tag.lower().strip()
        if normalized in OPPOSITE_TAG_MAP:
            return normalized, OPPOSITE_TAG_MAP[normalized]
    return None


def _find_all_opposite_tags(tags: list[str]) -> list[tuple[str, str]]:
    """기준 트랙의 태그 리스트에서 매핑 가능한 모든 (원본, 반대) 쌍을 반환.
    반대 태그 중복은 제거한다 (서로 다른 원본이 같은 반대 태그를 가리킬 수 있음).
    """
    seen_opposites: set[str] = set()
    result: list[tuple[str, str]] = []
    for tag in tags:
        normalized = tag.lower().strip()
        if normalized in OPPOSITE_TAG_MAP:
            opp = OPPOSITE_TAG_MAP[normalized]
            if opp not in seen_opposites:
                seen_opposites.add(opp)
                result.append((normalized, opp))
    return result


async def opposite_emotion(
    track_name: str,
    artist: str,
    sp: spotipy.Spotify,
    lastfm: pylast.LastFMNetwork,
    *,
    # ── 풀 구성 파라미터 ──────────────────────────────────────
    tag_pool_limit:  int   = 100,   # 반대 태그에서 가져올 후보 수
    top_tags:        int   = 5,     # 매핑 시도할 기준 트랙 상위 태그 수
    # ── 필터 파라미터 ─────────────────────────────────────────
    pop_min:         int   = 10,    # popularity 하한
    pop_max:         int   = 90,    # 감성 대비가 목적이므로 범위 넓게
    # ── 가중치 ───────────────────────────────────────────────
    w_tag_rank:      float = 0.7,   # 반대 태그 내 순위 (감성 순도)
    w_popularity:    float = 0.3,   # popularity (어느 정도 검증된 트랙)
    # ── 반환 개수 ─────────────────────────────────────────────
    top_n:           int   = 10,    # 반환할 트랙 수
    # ── 다양성 ───────────────────────────────────────────────
    diversity:       float = 0.3,   # 0=결정론적, 높을수록 매 실행 결과 다양
) -> list[TrackInfo]:
    """
    반대 감성 알고리즘

    기준 트랙의 감성 태그를 분석해 정반대 감성의 트랙을 추천한다.
    OPPOSITE_TAG_MAP 으로 반대 태그를 결정하고,
    Last.fm tag.getTopTracks 로 해당 태그의 상위 트랙을 수집한다.

    다른 알고리즘과의 차이:
        - Reverse / SimilarListening: 기준 트랙과 '유사한' 풀에서 선정
        - OppositeEmotion: 기준 트랙과 '반대' 태그 풀에서 선정
          → match_score 없음, popularity 억압 없음 (감성 대비가 핵심)

    점수 계산:
        opposite_score = (1 - tag_rank_norm) * 0.7   # 반대 태그 내 높은 순위
                       + popularity_norm     * 0.3   # 어느 정도 검증된 트랙

    Args:
        track_name:     기준 트랙명
        artist:         기준 아티스트명
        sp:             spotipy.Spotify 인스턴스
        lastfm:         pylast.LastFMNetwork 인스턴스
        tag_pool_limit: 반대 태그에서 가져올 후보 수 (기본 100)
        top_tags:       매핑 시도할 기준 트랙 상위 태그 수 (기본 5)
        pop_min:        popularity 하한 (기본 10)
        pop_max:        popularity 상한 (기본 90)
        w_tag_rank:     태그 내 순위 가중치 (기본 0.7)
        w_popularity:   popularity 가중치 (기본 0.3)
        top_n:          반환할 트랙 수 (기본 10)

    Returns:
        list[TrackInfo]  opposite_score 내림차순 상위 top_n개 (실패 시 [])
    """

        # ── Step 1. 기준 트랙 태그 수집 ──────────────────────────────
    logger.info("[OppositeEmotion] 기준 트랙: %s - %s", track_name, artist)
    try:
        lf_track     = lastfm.get_track(artist, track_name)
        top_tag_objs = await asyncio.to_thread(lf_track.get_top_tags)
        raw_tag_names = [t.item.get_name() for t in top_tag_objs[:top_tags]]
        tag_names = _specific_first_tags(raw_tag_names, top_tags)
    except Exception as e:
        logger.warning("[OppositeEmotion] 태그 수집 실패: %s", e)
        return []

    # ▼ 추가: 트랙 태그 없으면 아티스트 태그로 폴백
    if not tag_names:
        logger.warning(
            "[OppositeEmotion] 트랙 태그 없음 — 아티스트 태그로 폴백: %s", artist
        )
        try:
            lf_artist    = lastfm.get_artist(artist)
            artist_tags  = await asyncio.to_thread(lf_artist.get_top_tags)
            raw_tag_names = [t.item.get_name() for t in artist_tags[:top_tags]]
            tag_names = _specific_first_tags(raw_tag_names, top_tags)
        except Exception as e:
            logger.warning("[OppositeEmotion] 아티스트 태그 수집도 실패: %s", e)
            return []

    logger.info("[OppositeEmotion] 기준 태그: %s", tag_names)

    # ── Step 2. 반대 태그 결정 (매핑 가능한 전체 쌍) ─────────────
    # 단일 반대 태그만 사용하면 그 태그를 독점하는 아티스트에 의해
    # 결과가 오염될 수 있다. 매핑 가능한 모든 반대 태그를 병렬로 수집한다.
    mappings = _find_all_opposite_tags(_specific_first_tags(tag_names, len(tag_names)))
    if not mappings:
        logger.warning(
            "[OppositeEmotion] 매핑 가능한 반대 태그 없음. "
            "OPPOSITE_TAG_MAP 에 태그를 추가해주세요. (기준 태그: %s)", tag_names
        )
        return []

    origin_tags   = [m[0] for m in mappings]
    opposite_tags = [m[1] for m in mappings]
    logger.info("[OppositeEmotion] 태그 매핑: %s", mappings)

    # ── Step 3. 반대 태그별 풀 병렬 수집 후 병합 ─────────────────
    async def fetch_tag_pool(opp_tag: str) -> list[TrackInfo]:
        try:
            lf_tag = lastfm.get_tag(opp_tag)
            raw    = await asyncio.to_thread(lf_tag.get_top_tracks, limit=tag_pool_limit)
            return _lastfm_tag_tracks_to_trackinfo(raw)
        except Exception as e:
            logger.warning("[OppositeEmotion] tag.getTopTracks 실패 (%s): %s", opp_tag, e)
            return []

    tag_results = await asyncio.gather(*[fetch_tag_pool(opp) for opp in opposite_tags])
    pool = _deduplicate([t for tracks in tag_results for t in tracks])

    logger.info(
        "[OppositeEmotion] 반대 태그 풀: %d개 (%d개 태그 병합)",
        len(pool), len(opposite_tags),
    )

    # ── Step 4. Spotify 인기도 보강 (병렬) ──────────────────────
    # enrichment 전 tag_rank 상위 후보로 제한해 불필요한 API 호출 절감
    pool.sort(key=lambda t: t.tag_rank or tag_pool_limit)
    pool = pool[: top_n * 5]
    logger.info("[OppositeEmotion] enrichment 전 풀 제한: %d개", len(pool))
    pool = list(await _enrich_with_spotify(sp, pool))

    # ── Step 5. popularity 필터 ──────────────────────────────────
    before = len(pool)
    pool = [
        t for t in pool
        if (t.popularity is None or pop_min <= t.popularity <= pop_max)
    ]
    logger.info(
        "[OppositeEmotion] popularity 필터 후: %d개 (제거 %d개)",
        len(pool), before - len(pool),
    )

    if not pool:
        logger.warning("[OppositeEmotion] 필터 후 후보 없음.")
        return []

    # ── Step 6. opposite_score 계산 ──────────────────────────────
    # tag_rank를 pool_size로 나누면 병합 후 크기에 따라 값이 달라진다.
    # tag_pool_limit 기준으로 정규화해야 태그 수에 무관하게 일관된 순위 반영.
    max_pop = max((t.popularity or 0) for t in pool) or 1

    for t in pool:
        rank_norm = (t.tag_rank or tag_pool_limit) / tag_pool_limit
        pop_norm  = (t.popularity or 0) / max_pop

        t.reverse_score = (
            (1 - rank_norm) * w_tag_rank   +
            pop_norm        * w_popularity
        )

    # ── Step 7. 최종 선정 (아티스트 다양성 보장 후 상위 top_n) ────
    sorted_pool = sorted(pool, key=lambda t: t.reverse_score or 0, reverse=True)
    capped_pool = _cap_per_artist(sorted_pool, max_per=1)
    ranked      = _diverse_top_n(capped_pool, top_n, diversity=diversity)

    primary_origin   = origin_tags[0]
    primary_opposite = opposite_tags[0]
    for t in ranked:
        t.algo        = "opposite_emotion"
        t.label       = f"#{primary_origin} 반대: #{primary_opposite} 추천"
        t.reason_tags = list(dict.fromkeys(origin_tags + opposite_tags))[:4]

    logger.info(
        "[OppositeEmotion] 선정 %d개 (태그 매핑: %s):", len(ranked), mappings
    )
    for i, t in enumerate(ranked, 1):
        logger.info(
            "  %d. %s - %s (popularity=%s, opposite_score=%.3f)",
            i, t.name, t.artist, t.popularity, t.reverse_score or 0,
        )
    return ranked


# ════════════════════════════════════════════════════════════════
# Hidden Discovery 알고리즘
# ════════════════════════════════════════════════════════════════

async def hidden_discovery(
    track_name: str,
    artist: str,
    sp: spotipy.Spotify,
    lastfm: pylast.LastFMNetwork,
    *,
    artist_limit:   int   = 10,
    tracks_per_art: int   = 10,
    pop_min:        int   = 5,
    pop_max:        int   = 40,
    top_n:          int   = 10,
    diversity:      float = 0.3,
) -> list[TrackInfo]:
    """
    아티스트 인기도 대비 잘 알려지지 않은 숨겨진 명곡을 발굴한다.
    유명 아티스트의 B-side도 발굴 대상에 포함한다.

    점수 계산:
        hidden_score = hidden_ratio  * 0.5   # 아티스트 대비 트랙 비인지도
                     + loyalty_norm  * 0.3   # 충성도 log1p 정규화
                     + artist_pop_norm * 0.2  # 유명 아티스트 보너스
    """
    logger.info("[HiddenDiscovery] 알고리즘 시작: %s - %s", track_name, artist)
    input_key = (track_name.lower(), artist.lower())

    try:
        lf_artist = lastfm.get_artist(artist)
        similar_artists = await asyncio.to_thread(
            lf_artist.get_similar, limit=artist_limit
        )

        # 입력 아티스트 자신 + 유사 아티스트 모두 탐색
        artist_sources = [lf_artist] + [sa.item for sa in similar_artists]
        tasks = [
            asyncio.to_thread(src.get_top_tracks, limit=tracks_per_art)
            for src in artist_sources
        ]
        # return_exceptions=True: 한 아티스트 실패가 전체 풀 구성을 중단시키지 않음
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        pool = []
        for result in raw_results:
            if isinstance(result, Exception):
                logger.warning("[HiddenDiscovery] 아티스트 트랙 수집 실패: %s", result)
                continue
            for item in result:
                try:
                    pool.append(TrackInfo(
                        name=item.item.get_name(),
                        artist=item.item.get_artist().get_name(),
                    ))
                except Exception as e:
                    logger.debug("[HiddenDiscovery] 트랙 변환 실패: %s", e)

        pool = _deduplicate(pool)
        # 입력 트랙 자체는 결과에서 제외
        pool = [t for t in pool if (t.name.lower(), t.artist.lower()) != input_key]
        logger.info("[HiddenDiscovery] 후보 풀: %d개 (%d 아티스트 소스)",
                    len(pool), len(artist_sources))

        pool = await _enrich_with_spotify(sp, pool)

        # popularity 필터 — top_n 미만이면 pop_max를 단계적으로 완화
        _POP_RELAX = (0, 10, 20)
        filtered: list[TrackInfo] = []
        effective_pop_max = pop_max
        for extra in _POP_RELAX:
            effective_pop_max = pop_max + extra
            filtered = [
                t for t in pool
                if t.popularity is not None and pop_min <= t.popularity <= effective_pop_max
            ]
            if len(filtered) >= top_n:
                break

        pool = filtered
        logger.info("[HiddenDiscovery] popularity 필터 후: %d개 (pop_max=%d)",
                    len(pool), effective_pop_max)

        if not pool:
            logger.warning("[HiddenDiscovery] 필터 후 후보 없음.")
            return []

        # Last.fm 청취 지표 수집
        async def fetch_metrics(track: TrackInfo) -> TrackInfo | None:
            try:
                track_obj = lastfm.get_track(track.artist, track.name)
                listeners, playcount = await asyncio.gather(
                    asyncio.to_thread(track_obj.get_listener_count),
                    asyncio.to_thread(track_obj.get_playcount),
                )
                # 충성도 raw값 임시 저장 — 아래에서 log1p 정규화
                track.match_score = int(playcount) / max(int(listeners), 1)
                return track
            except Exception as e:
                logger.debug("[HiddenDiscovery] 메트릭 수집 실패 (%s - %s): %s",
                             track.artist, track.name, e)
                return None

        metric_results = await asyncio.gather(*[fetch_metrics(t) for t in pool])
        pool = [t for t in metric_results if t is not None]

        if not pool:
            logger.warning("[HiddenDiscovery] 메트릭 수집 후 후보 없음.")
            return []

        # 충성도 log1p 정규화 — 극단적 이상치(playcount 폭발) 완화
        log_loyalties = [math.log1p(t.match_score or 0) for t in pool]
        max_log = max(log_loyalties) or 1.0

        for t, log_loyalty in zip(pool, log_loyalties):
            loyalty_norm = log_loyalty / max_log
            track_pop    = t.popularity or 0
            # artist_pop이 None이면 언더그라운드 중간값(30)으로 대체
            # → or 0 사용 시 track_pop≥10이면 hidden_ratio=0이 되는 왜곡 방지
            artist_pop   = t.artist_spotify_popularity if t.artist_spotify_popularity is not None else 30

            # 아티스트 인기도 대비 트랙 비인지도 — 유명 아티스트의 B-side일수록 높음
            hidden_ratio = max(0.0, 1.0 - track_pop / max(artist_pop, 10))
            artist_norm  = artist_pop / 100

            t.reverse_score = (
                hidden_ratio * 0.5
                + loyalty_norm  * 0.3
                + artist_norm   * 0.2
            )

        # 아티스트당 최대 2곡 (유명 아티스트 허용하되 독점 방지)
        sorted_pool = sorted(pool, key=lambda t: t.reverse_score or 0, reverse=True)
        capped_pool = _cap_per_artist(sorted_pool, max_per=2)
        ranked      = _diverse_top_n(capped_pool, top_n, diversity=diversity)

        for t in ranked:
            t.algo  = "hidden_discovery"
            t.label = "숨겨진 명곡"

        logger.info("[HiddenDiscovery] 최종 선정 %d개 완료", len(ranked))
        for i, t in enumerate(ranked, 1):
            logger.info(
                "  %d. %s - %s (track_pop=%s, artist_pop=%s, hidden_score=%.3f)",
                i, t.name, t.artist,
                t.popularity, t.artist_spotify_popularity, t.reverse_score or 0,
            )
        return ranked
    except Exception as e:
        logger.error("[HiddenDiscovery] 알고리즘 실행 실패: %s", e, exc_info=True)
        return []
