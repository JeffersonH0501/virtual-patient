from unittest.mock import patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.captcha import require_captcha
from app.core.database import get_db
from app.media.access import _current_media_user
from app.routers import auth, users


def test_browser_session_lifecycle_and_origin_check():
    application = FastAPI()
    application.include_router(auth.router, prefix="/api")
    application.include_router(users.router, prefix="/api")
    application.dependency_overrides[get_db] = lambda: None
    application.dependency_overrides[require_captcha] = lambda: None

    @application.get("/api/me")
    def me(user=Depends(get_current_active_user)):
        return {"id": user.id}

    @application.post("/api/protected")
    def protected(user=Depends(get_current_active_user)):
        return {"id": user.id}

    @application.get("/api/medical-interviews/1/replay")
    def replay(user=Depends(_current_media_user)):
        return {"id": user.id}

    class Account:
        id = 17
        disabled = False

    with (
        TestClient(application, base_url="https://patient.example") as client,
        patch("app.routers.auth.authenticate_user", return_value=Account()),
        patch("app.core.auth.get_user", return_value=Account()),
        patch("app.routers.users.persist_user", return_value=Account()),
    ):
        credentials = {"email": "test@example.org", "password": "synthetic"}
        origin = {"Origin": "https://patient.example"}
        response = client.post("/api/auth/token", json=credentials, headers={**origin, "X-Web-Session": "1"})
        assert response.status_code == 200
        assert "access_token" not in response.json()
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
        assert client.get("/api/me").json() == {"id": 17}
        assert client.get("/api/medical-interviews/1/replay").json() == {"id": 17}
        assert client.post("/api/protected", headers={"Origin": "https://other.example"}).status_code == 403
        assert client.post("/api/protected").status_code == 403
        assert client.post("/api/protected", headers=origin).status_code == 200
        assert client.post("/api/auth/logout", headers=origin).status_code == 200
        assert client.get("/api/me").status_code == 401

        response = client.post("/api/auth/token", json=credentials)
        assert response.status_code == 200 and response.json()["access_token"]

        registration = {"email": "new@example.org", "password": "synthetic", "name": "Test instructor", "role": "doctor"}
        response = client.post("/api/users", json=registration, headers={**origin, "X-Web-Session": "1"})
        assert response.status_code == 201 and "access_token" not in response.json()
        assert client.get("/api/me").json() == {"id": 17}
