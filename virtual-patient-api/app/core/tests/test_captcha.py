from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import captcha
from app.routers import auth, users


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/auth/token", {"email": "test@example.org", "password": "password"}),
        ("/users", {"email": "test@example.org", "password": "password", "name": "Test"}),
    ],
)
def test_public_auth_requires_captcha_before_authentication_or_registration(monkeypatch, path, body):
    monkeypatch.setattr(captcha, "settings", SimpleNamespace(recaptcha_secret_key="synthetic"))
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(users.router)
    response = TestClient(app).post(path, json=body)
    assert response.status_code == 400
    assert response.json()["detail"] == "CAPTCHA verification required"


@pytest.mark.parametrize(("verified", "expected"), [(True, None), (False, 400)])
def test_server_checks_provider_response(monkeypatch, verified, expected):
    monkeypatch.setattr(captcha, "settings", SimpleNamespace(recaptcha_secret_key="synthetic"))

    def verify(url, *, data, timeout):
        assert data == {"secret": "synthetic", "response": "response"}
        return httpx.Response(200, request=httpx.Request("POST", url), json={"success": verified})

    monkeypatch.setattr(captcha.httpx, "post", verify)
    if expected is None:
        captcha.require_captcha("response")
    else:
        with pytest.raises(captcha.HTTPException) as failure:
            captcha.require_captcha("response")
        assert failure.value.status_code == expected