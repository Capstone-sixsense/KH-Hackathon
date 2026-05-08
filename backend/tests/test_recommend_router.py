from app.main import app


def test_recommend_route_is_registered():
    paths = {route.path for route in app.routes}

    assert "/search" in paths
    assert "/recommend" in paths
