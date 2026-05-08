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
import re
from dataclasses import dataclass, field

import pylast
import spotipy

logger = logging.getLogger(__name__)


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

def _sp_search(sp: spotipy.Spotify, track_name: str, artist: str) -> dict | None:
    """Spotify에서 트랙을 검색해 첫 번째 결과를 반환."""
    query = f"track:{track_name} artist:{artist}"
    try:
        results = sp.search(q=query, type="track", limit=1)
        items = results["tracks"]["items"]
        return items[0] if items else None
    except Exception as e:
        logger.warning("Spotify 검색 실패 (%s - %s): %s", track_name, artist, e)
        return None

async def normalize_input(
    query: str,
    sp: spotipy.Spotify,
    lastfm: pylast.LastFMNetwork,
    search_limit: int = 5,
) -> tuple[str, str, str] | tuple[None, None, None]:
    """Spotify 후보 중 Last.fm 유사 트랙 데이터가 있는 첫 번째 트랙을 반환한다."""
    try:
        results = await asyncio.to_thread(
            sp.search, q=query, type="track", limit=search_limit
        )
        items = results["tracks"]["items"]

        for track in items:
            name     = track["name"]
            artist   = track["artists"][0]["name"]
            track_id = track["id"]

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
                    "[Normalize] Last.fm 데이터 없음, 다음 후보로: '%s - %s'",
                    name, artist,
                )
            except Exception:
                logger.info(
                    "[Normalize] Last.fm 조회 실패, 다음 후보로: '%s - %s'",
                    name, artist,
                )
                continue

    except Exception as e:
        logger.error("[Normalize] Spotify 검색 실패: %s", e)

    return None, None, None

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
        item = await asyncio.to_thread(_sp_search, sp, track.name, track.artist)
        if item:
            track.spotify_id    = item["id"]
            track.popularity    = item["popularity"]
            track.album_art_url = (
                item["album"]["images"][0]["url"]
                if item["album"]["images"] else None
            )
            artist_id_by_idx[idx] = item["artists"][0]["id"]
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
    top_tags:        int   = 2,     # 사용할 태그 수
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

    # ── Step 3. Spotify 인기도 보강 (병렬) ──────────────────────
    pool = await _enrich_with_spotify(sp, pool)

    # ── Step 3.5. 아티스트 리스너 수 보강 ───────────────────────
    async def fetch_artist_listeners(track: TrackInfo) -> TrackInfo:
        try:
            artist_obj = lastfm.get_artist(track.artist)
            listeners = await asyncio.to_thread(artist_obj.get_listener_count)
            track.artist_listeners = int(listeners)
        except Exception:
            track.artist_listeners = 0
        return track

    pool = list(await asyncio.gather(*[fetch_artist_listeners(t) for t in pool]))

    # ── Step 4. 필터 ─────────────────────────────────────────────
    before = len(pool)
    pool = [
        t for t in pool
        if (t.popularity is None or pop_min <= t.popularity <= pop_max)
        and (t.artist_listeners is None or t.artist_listeners < 500000)
        and (t.artist_spotify_popularity is None or t.artist_spotify_popularity < 55)  # ← 추가
        and (t.artist_spotify_followers  is None or t.artist_spotify_followers  < 200000)  # ← 추가
        and (t.match_score or 0) >= match_threshold
    ]

    logger.info("[Reverse] 필터 후: %d개 (제거 %d개)", len(pool), before - len(pool))

    if not pool:
        logger.warning("[Reverse] 필터 후 후보 없음 — pop_max를 높여보세요.")
        return []

    # ── Step 5. Reverse Score 계산 ───────────────────────────────
    pool_size = len(pool)
    original_tag_limit = tag_limit
    for t in pool:
        p_score = 1 - ((t.popularity or 0) / 100)
        m_score = t.match_score or 0
        a_score = max(0, 1 - ((t.artist_listeners or 0) / 100000))
        if t.tag_rank:
            r_score = max(0, 1 - (t.tag_rank / original_tag_limit))
        else:
            r_score = 0.5

        t.reverse_score = (
            p_score * 0.4 +
            a_score * 0.3 +
            m_score * 0.2 +
            r_score * 0.1
        )

    # ── Step 6. 최종 선정 (상위 10개 리스트) ───────────────────────
    ranked = sorted(pool, key=lambda t: t.reverse_score or 0, reverse=True)[:top_n]

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

    # ── Step 8. 최종 선정 (상위 10개 리스트) ───────────────────────
    ranked = sorted(pool, key=lambda t: t.reverse_score or 0, reverse=True)[:top_n]

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
    """
    기준 트랙의 태그 리스트에서 매핑 가능한 첫 번째 반대 태그를 반환.

    Returns:
        (원본_태그, 반대_태그) 튜플 또는 None
    """
    for tag in tags:
        normalized = tag.lower().strip()
        if normalized in OPPOSITE_TAG_MAP:
            return normalized, OPPOSITE_TAG_MAP[normalized]
    return None


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

    # ── Step 2. 반대 태그 결정 ───────────────────────────────────
    mapping = _find_opposite_tag(_specific_first_tags(tag_names, len(tag_names)))
    if not mapping:
        logger.warning(
            "[OppositeEmotion] 매핑 가능한 반대 태그 없음. "
            "OPPOSITE_TAG_MAP 에 태그를 추가해주세요. (기준 태그: %s)", tag_names
        )
        return []

    origin_tag, opposite_tag = mapping
    logger.info(
        "[OppositeEmotion] 태그 매핑: '%s' → '%s'", origin_tag, opposite_tag
    )

    # ── Step 3. 반대 태그 풀 수집 ────────────────────────────────
    try:
        lf_tag    = lastfm.get_tag(opposite_tag)
        raw_tracks = await asyncio.to_thread(
            lf_tag.get_top_tracks, limit=tag_pool_limit
        )
        pool = _lastfm_tag_tracks_to_trackinfo(raw_tracks)
    except Exception as e:
        logger.warning(
            "[OppositeEmotion] tag.getTopTracks 실패 (%s): %s", opposite_tag, e
        )
        return []

    logger.info("[OppositeEmotion] 반대 태그 풀: %d개", len(pool))

    # ── Step 4. Spotify 인기도 보강 (병렬) ──────────────────────
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
    # tag_rank: 반대 태그 내 순위 (1위에 가까울수록 감성 순도 높음)
    pool_size     = len(pool)
    max_pop       = max((t.popularity or 0) for t in pool) or 1

    for t in pool:
        rank_norm = (t.tag_rank or pool_size) / pool_size
        pop_norm  = (t.popularity or 0) / max_pop

        t.reverse_score = (
            (1 - rank_norm) * w_tag_rank   +
            pop_norm        * w_popularity
        )

    # ── Step 7. 최종 선정 (상위 top_n 리스트) ───────────────────
    ranked = sorted(pool, key=lambda t: t.reverse_score or 0, reverse=True)[:top_n]

    for t in ranked:
        t.algo        = "opposite_emotion"
        t.label       = f"#{origin_tag} 반대: #{opposite_tag} 추천"
        t.reason_tags = [origin_tag, opposite_tag]

    logger.info("[OppositeEmotion] 선정 %d개 ('%s' → '%s'):",
                len(ranked), origin_tag, opposite_tag)
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
    artist_limit: int = 10,
    tracks_per_art: int = 5,
    pop_min: int = 5,
    pop_max: int = 35,
    top_n: int = 10,
) -> list[TrackInfo]:
    """
    유사 아티스트의 곡 중 아티스트 규모 대비 반복 청취율이 높은 곡을 찾는다.
    """
    logger.info("[HiddenDiscovery] 알고리즘 시작: %s - %s", track_name, artist)

    try:
        lf_artist = lastfm.get_artist(artist)
        similar_artists = await asyncio.to_thread(
            lf_artist.get_similar, limit=artist_limit
        )

        tasks = [
            asyncio.to_thread(sa.item.get_top_tracks, limit=tracks_per_art)
            for sa in similar_artists
        ]
        raw_track_results = await asyncio.gather(*tasks)

        pool = []
        for track_list in raw_track_results:
            for item in track_list:
                pool.append(
                    TrackInfo(
                        name=item.item.get_name(),
                        artist=item.item.get_artist().get_name(),
                        match_score=0.5,
                    )
                )

        pool = _deduplicate(pool)
        logger.info("[HiddenDiscovery] 후보 풀 구성 완료: %d개", len(pool))

        pool = await _enrich_with_spotify(sp, pool)
        pool = [
            t for t in pool
            if t.popularity is not None and pop_min <= t.popularity <= pop_max
        ]

        async def fetch_metrics(track: TrackInfo) -> TrackInfo | None:
            try:
                track_obj = lastfm.get_track(track.artist, track.name)
                artist_obj = lastfm.get_artist(track.artist)

                listeners, playcount, artist_listeners = await asyncio.gather(
                    asyncio.to_thread(track_obj.get_listener_count),
                    asyncio.to_thread(track_obj.get_playcount),
                    asyncio.to_thread(artist_obj.get_listener_count),
                )

                rarity = 1 / math.log10(max(int(artist_listeners), 10))
                loyalty = int(playcount) / max(int(listeners), 1)
                track.reverse_score = rarity * loyalty * (track.match_score or 1)
                return track
            except Exception:
                return None

        metric_results = await asyncio.gather(*[fetch_metrics(t) for t in pool])
        pool = [t for t in metric_results if t is not None]
        ranked = sorted(pool, key=lambda t: t.reverse_score or 0, reverse=True)[:top_n]

        for t in ranked:
            t.algo = "hidden_discovery"
            t.label = "인지도 대비 높은 충성도의 명곡"

        logger.info("[HiddenDiscovery] 최종 선정 %d개 완료", len(ranked))
        return ranked
    except Exception as e:
        logger.error("[HiddenDiscovery] 알고리즘 실행 실패: %s", e, exc_info=True)
        return []
