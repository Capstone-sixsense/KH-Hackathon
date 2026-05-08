import spotipy

import recommend_algo
from recommend_algo import normalize_input


SPOTIFY_FALLBACK_TRACK = {
    "id": "spotify-fallback-id",
    "name": "c/2022YH",
    "artists": [{"name": "Younha"}],
}

SPOTIFY_VERIFIED_TRACK = {
    "id": "spotify-verified-id",
    "name": "Event Horizon",
    "artists": [{"name": "Younha"}],
}


class FakeSpotify:
    def __init__(self, tracks):
        self.tracks = tracks
        self.queries = []

    def search(self, q, type, limit):
        self.queries.append((q, type, limit))
        return {"tracks": {"items": self.tracks[:limit]}}


class RateLimitedSpotify(FakeSpotify):
    def __init__(self):
        super().__init__([])

    def search(self, q, type, limit):
        self.queries.append((q, type, limit))
        raise spotipy.SpotifyException(
            429,
            -1,
            "Too many requests",
            headers={"Retry-After": "120"},
        )


class FakeLastFmTrack:
    def __init__(self, similar):
        self.similar = similar

    def get_similar(self, limit=1):
        return self.similar[:limit]


class FakeLastFm:
    def __init__(self, similar_by_track):
        self.similar_by_track = similar_by_track
        self.lookups = []

    def get_track(self, artist, name):
        self.lookups.append((artist, name))
        return FakeLastFmTrack(self.similar_by_track.get((artist, name), []))


class FakeLastFmSearchTrack:
    def __init__(self, artist, title):
        self.artist = artist
        self.title = title

    def get_name(self):
        return self.title


class FakeLastFmTrackSearch:
    def __init__(self, tracks):
        self.tracks = tracks

    def get_next_page(self):
        return self.tracks


class SearchableFakeLastFm(FakeLastFm):
    def __init__(self, similar_by_track, search_tracks):
        super().__init__(similar_by_track)
        self.search_tracks = search_tracks
        self.search_queries = []

    def search_for_track(self, artist_name, track_name):
        self.search_queries.append((artist_name, track_name))
        return FakeLastFmTrackSearch(self.search_tracks)


async def test_normalize_input_falls_back_to_spotify_candidate_without_lastfm_similar():
    spotify = FakeSpotify([SPOTIFY_FALLBACK_TRACK])
    lastfm = FakeLastFm({})

    result = await normalize_input("윤하 살별", spotify, lastfm)

    assert result == ("c/2022YH", "Younha", "spotify-fallback-id")
    assert lastfm.lookups == [("Younha", "c/2022YH")]


async def test_normalize_input_prefers_lastfm_verified_candidate_over_spotify_fallback():
    spotify = FakeSpotify([SPOTIFY_FALLBACK_TRACK, SPOTIFY_VERIFIED_TRACK])
    lastfm = FakeLastFm({("Younha", "Event Horizon"): [object()]})

    result = await normalize_input("윤하 살별", spotify, lastfm)

    assert result == ("Event Horizon", "Younha", "spotify-verified-id")
    assert lastfm.lookups == [("Younha", "c/2022YH"), ("Younha", "Event Horizon")]


async def test_normalize_input_uses_lastfm_fallback_when_spotify_rate_limited():
    recommend_algo._SP_RATE_LIMIT_UNTIL = 0.0
    spotify = RateLimitedSpotify()
    lastfm = SearchableFakeLastFm(
        {},
        [
            FakeLastFmSearchTrack("[unknown]", "아이유 - 좋은날"),
            FakeLastFmSearchTrack("아이유", "좋은날"),
        ],
    )

    result = await normalize_input("아이유 좋은날", spotify, lastfm)

    assert result == ("좋은날", "아이유", None)
    assert spotify.queries == [("아이유 좋은날", "track", 5)]
    assert lastfm.search_queries == [("", "아이유 좋은날")]
