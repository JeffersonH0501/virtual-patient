from typing import Annotated

import httpx
from fastapi import Header, HTTPException

from app.core.config import settings


def require_captcha(token: Annotated[str | None, Header(alias="X-Recaptcha-Token", max_length=4096)] = None) -> None:
    if not settings.recaptcha_secret_key:
        return  # Local development may run without a provider secret.
    if not token:
        raise HTTPException(400, "CAPTCHA verification required")
    try:
        response = httpx.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": settings.recaptcha_secret_key, "response": token},
            timeout=5.0,
        )
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise HTTPException(503, "CAPTCHA verification unavailable") from error
    if not isinstance(result, dict) or result.get("success") is not True:
        raise HTTPException(400, "CAPTCHA verification failed")