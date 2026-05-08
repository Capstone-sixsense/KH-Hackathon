from app.services.spotify import SpotifyClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


class FakeHttp:
    def __init__(self):
        self.post_count = 0

    async def post(self, *args, **kwargs):
        self.post_count += 1
        return FakeResponse({"access_token": "token", "expires_in": 3600})

    async def get(self, *args, **kwargs):
        return FakeResponse({"tracks": {"items": []}})


async def test_spotify_token_is_cached():
    http = FakeHttp()
    client = SpotifyClient("client", "secret", http)

    await client.search_tracks("IU", limit=5)
    await client.search_tracks("Queen", limit=5)

    assert http.post_count == 1
