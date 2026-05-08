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
