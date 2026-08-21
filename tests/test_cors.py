"""CORS behavior for local and deployed frontend origins."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
LOCAL_ORIGIN = "http://localhost:3000"


def test_cors_development_origin() -> None:
    response = client.get("/api/health", headers={"Origin": LOCAL_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == LOCAL_ORIGIN


def test_cors_options_preflight() -> None:
    response = client.options(
        "/api/health",
        headers={
            "Origin": LOCAL_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == LOCAL_ORIGIN
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


def test_cors_headers_present() -> None:
    response = client.get("/api/health", headers={"Origin": LOCAL_ORIGIN})

    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers


def test_cors_does_not_enable_unused_browser_credentials() -> None:
    response = client.get("/api/health", headers={"Origin": LOCAL_ORIGIN})

    assert response.status_code == 200
    assert "access-control-allow-credentials" not in response.headers


def test_cors_methods() -> None:
    middleware = next(
        item for item in app.user_middleware if item.cls.__name__ == "CORSMiddleware"
    )

    assert middleware.kwargs["allow_methods"] == ["GET", "POST", "OPTIONS"]
    assert middleware.kwargs["allow_headers"] == ["Content-Type"]
    assert middleware.kwargs["allow_credentials"] is False


def test_cors_unauthorized_origin_is_not_allowed() -> None:
    response = client.get(
        "/api/health",
        headers={"Origin": "https://unauthorized.example.com"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_are_parsed_as_multiple_exact_values() -> None:
    configured = "http://localhost:3000, https://your-app.vercel.app,https://your-domain.com"
    parsed = [origin.strip() for origin in configured.split(",") if origin.strip()]

    assert parsed == [
        "http://localhost:3000",
        "https://your-app.vercel.app",
        "https://your-domain.com",
    ]
    assert "*" not in parsed
