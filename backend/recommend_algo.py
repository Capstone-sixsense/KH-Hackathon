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
from dataclasses import dataclass, field

import pylast
import spotipy

logger = logging.getLogger(__name__)


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


async def _enrich_with_spotify(
    sp: spotipy.Spotify,
    tracks: list[TrackInfo],
) -> list[TrackInfo]:
    """
    TrackInfo 리스트에 Spotify popularity / spotify_id / album_art_url 를
    병렬로 보강한다.
    spotipy는 동기 라이브러리이므로 asyncio.to_thread 로 감싼다.
    """
    async def _fetch(track: TrackInfo) -> TrackInfo:
        item = await asyncio.to_thread(_sp_search, sp, track.name, track.artist)
        if item:
            track.spotify_id = item["id"]
            track.popularity = item["popularity"]
            track.album_art_url = item["album"]["images"][0]["url"] if item["album"]["images"] else None
        else:
            # 검색 실패 시 기본값 설정 (에러 방지)
            track.spotify_id = track.spotify_id or f"temp_{track.name}"
            track.popularity = track.popularity or 0 
        return track

    return list(await asyncio.gather(*[_fetch(t) for t in tracks]))


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
    top_tags:        int   = 2,     # 사용할 상위 태그 수
    # ── 필터 파라미터 ─────────────────────────────────────────
    pop_min:         int   = 5,     # popularity 하한 (유령 트랙 제외)
    pop_max:         int   = 40,    # popularity 상한 (이미 알려진 트랙 제외)
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
        pop_max:         popularity 상한 (기본 40)
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
        tag_names  = [t.item.get_name() for t in top_tag_objs[:top_tags]]
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

    # ── Step 4. 필터 ─────────────────────────────────────────────
    before = len(pool)
    """
    pool = [
        t for t in pool
        if t.popularity is not None
        and pop_min <= t.popularity <= pop_max
        and (t.match_score or 0) >= match_threshold
    ]
    """
    pool = [
        t for t in pool
        if (t.popularity is None or pop_min <= t.popularity <= pop_max)
        and (t.match_score or 0) >= match_threshold
    ]
    logger.info("[Reverse] 필터 후: %d개 (제거 %d개)", len(pool), before - len(pool))

    if not pool:
        logger.warning("[Reverse] 필터 후 후보 없음 — pop_max를 높여보세요.")
        return []

    # ── Step 5. Reverse Score 계산 ───────────────────────────────
    pool_size = len(pool)
    for t in pool:
        p_norm = (t.popularity or 0) / 100
        r_norm = (t.tag_rank   or pool_size) / pool_size
        m      = t.match_score or 0

        t.reverse_score = (
            (1 - p_norm) * w_popularity +
            m            * w_match      +
            (1 - r_norm) * w_tag_rank
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
        tag_names = await asyncio.to_thread(_get_safe_top_tags, lf_track, 3)
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
    pool = [t for t in pool if (t.match_score or 0) >= match_threshold]
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
        if t.popularity is not None
        and pop_min <= t.popularity <= pop_max
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
        tag_names    = [t.item.get_name() for t in top_tag_objs[:top_tags]]
    except Exception as e:
        logger.warning("[OppositeEmotion] 태그 수집 실패: %s", e)
        return []

    logger.info("[OppositeEmotion] 기준 태그: %s", tag_names)

    # ── Step 2. 반대 태그 결정 ───────────────────────────────────
    mapping = _find_opposite_tag(tag_names)
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
        if t.popularity is not None
        and pop_min <= t.popularity <= pop_max
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