from pathlib import Path

from app.routers import recommend as recommend_router
from app.routers.recommend import RecommendRequest, RecommendResponse
from main import app


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


def test_recommend_router_loads_backend_recommend_algo_file():
    loaded_path = Path(recommend_router.recommend_algo.__file__).resolve()

    assert loaded_path == recommend_router._RECOMMEND_ALGO_PATH
    assert recommend_router.reverse_top100 is recommend_router.recommend_algo.reverse_top100
    assert recommend_router.similar_listening_pattern is recommend_router.recommend_algo.similar_listening_pattern
