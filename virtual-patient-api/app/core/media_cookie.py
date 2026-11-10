"""HTTP-only replay authentication for native audio/video elements."""
from app.core.config import settings

MEDIA_COOKIE_NAME = "media_access_token"


def set_media_cookie(response, access_token):
    response.set_cookie(MEDIA_COOKIE_NAME, access_token, httponly=True,
                        secure=settings.environment.lower() in {"production", "prod"},
                        samesite="strict", max_age=settings.access_token_expire_minutes * 60,
                        path="/medical-interviews")


def clear_media_cookie(response):
    response.delete_cookie(MEDIA_COOKIE_NAME, path="/medical-interviews",
                          httponly=True, secure=settings.environment.lower() in {"production", "prod"},
                          samesite="strict")
