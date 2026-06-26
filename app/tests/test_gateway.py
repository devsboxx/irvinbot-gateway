import pytest
import respx
import httpx
from fastapi.testclient import TestClient
from jose import jwt
from datetime import datetime, timedelta, timezone

from main import app
from app.core.config import settings

client = TestClient(app)

# Firma con el secreto efectivamente configurado (settings lee .env/env),
# para que los tokens validen sin depender del valor del .env de desarrollo.
SECRET = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM


def _make_token(user_id: str = "abc-123", role: str = "student") -> str:
    payload = {
        "sub": user_id,
        "email": "test@uni.edu",
        "role": role,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["service"] == "gateway"


def test_protected_route_without_token():
    res = client.get("/api/chat/sessions")
    assert res.status_code == 401


def test_protected_route_with_invalid_token():
    res = client.get("/api/chat/sessions", headers={"authorization": "Bearer bad-token"})
    assert res.status_code == 401


def test_public_login_route_no_token_required():
    with respx.mock:
        respx.post("http://localhost:8001/auth/login").mock(
            return_value=httpx.Response(200, json={"access_token": "t", "refresh_token": "r", "token_type": "bearer"})
        )
        res = client.post("/api/auth/login", json={"email": "a@b.com", "password": "x"})
    assert res.status_code == 200


def test_public_register_route_no_token_required():
    with respx.mock:
        respx.post("http://localhost:8001/auth/register").mock(
            return_value=httpx.Response(201, json={"id": "u1", "email": "a@b.com"})
        )
        res = client.post("/api/auth/register", json={"email": "a@b.com", "password": "x", "full_name": "A"})
    assert res.status_code == 201


def test_proxies_to_chat_with_token():
    token = _make_token()
    with respx.mock:
        respx.get("http://localhost:8002/chat/sessions").mock(
            return_value=httpx.Response(200, json=[])
        )
        res = client.get("/api/chat/sessions", headers={"authorization": f"Bearer {token}"})
    assert res.status_code == 200


def test_x_user_id_header_forwarded():
    token = _make_token(user_id="user-999")
    captured_headers = {}

    def capture(request: httpx.Request):
        captured_headers.update(dict(request.headers))
        return httpx.Response(200, json=[])

    with respx.mock:
        respx.get("http://localhost:8002/chat/sessions").mock(side_effect=capture)
        client.get("/api/chat/sessions", headers={"authorization": f"Bearer {token}"})

    assert captured_headers.get("x-user-id") == "user-999"


def test_unknown_service_returns_404():
    token = _make_token()
    res = client.get("/api/unknown/path", headers={"authorization": f"Bearer {token}"})
    assert res.status_code == 404


def test_proxies_thesis_to_chat_service():
    token = _make_token()
    with respx.mock:
        respx.post("http://localhost:8002/thesis/sections/resumen").mock(
            return_value=httpx.Response(200, json={"key": "resumen", "titulo": "Resumen", "contenido": "ok"})
        )
        res = client.post(
            "/api/thesis/sections/resumen",
            headers={"authorization": f"Bearer {token}"},
            json={"objeto_de_estudio": {}},
        )
    assert res.status_code == 200
    assert res.json()["key"] == "resumen"


def test_upstream_unavailable_returns_503():
    token = _make_token()
    with respx.mock:
        respx.get("http://localhost:8002/chat/sessions").mock(side_effect=httpx.ConnectError("down"))
        res = client.get("/api/chat/sessions", headers={"authorization": f"Bearer {token}"})
    assert res.status_code == 503
