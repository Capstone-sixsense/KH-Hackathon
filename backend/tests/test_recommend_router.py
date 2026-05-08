from app.main import app
from app.routers.recommend import RecommendRequest, RecommendResponse


def test_recommend_route_is_registered():
    paths = {route.path for route in app.routes}

    assert "/search" in paths
    assert "/recommend" in paths


def test_recommend_contract_uses_query_and_hidden_bucket():
    request = RecommendRequest(query="아이유 너랑나", top_n=3)
    response = RecommendResponse(
        track_name="너랑나",
        artist="IU",
        top_n=request.top_n,
        spotify_id="spotify-id",
        album_art_url="https://example.com/art.jpg",
        result={"similar": [], "reverse": [], "opposite": [], "hidden": []},
    )

    assert request.query == "아이유 너랑나"
    assert response.result["hidden"] == []
    assert response.spotify_id == "spotify-id"
