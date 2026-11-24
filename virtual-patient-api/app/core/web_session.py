"""Same-origin browser sessions and CSRF checks for cookie authentication."""

from fastapi import HTTPException, Request, Response

from app.core.config import settings


SESSION_COOKIE = "vp_web_session"
PRODUCTION = settings.environment.lower() in {"production", "prod"}


def require_session_origin(request: Request) -> None:
    host = request.headers.get("host", "")
    origin = request.headers.get("origin")
    if host and (origin == f"https://{host}" or (not PRODUCTION and origin == f"http://{host}")):
        return
    raise HTTPException(status_code=403, detail="Invalid session origin")


def is_web_session_request(request: Request) -> bool:
    if request.headers.get("x-web-session") != "1":
        return False
    require_session_origin(request)
    return True


def read_session_token(request: Request, *media_cookies: str | None) -> str | None:
    token = request.cookies.get(SESSION_COOKIE) or next((cookie for cookie in media_cookies if cookie), None)
    if token and request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_session_origin(request)
    return token


def set_web_session(request: Request, response: Response, token: str, expires_in: int) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(SESSION_COOKIE, token, max_age=expires_in, path="/api", httponly=True,
                        secure=PRODUCTION or request.headers.get("origin", "").startswith("https://"), samesite="strict")


def clear_web_session(request: Request, response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/api", httponly=True,
                           secure=PRODUCTION or request.headers.get("origin", "").startswith("https://"), samesite="strict")
