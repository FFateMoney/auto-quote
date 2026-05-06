from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from backend.common.config import as_bool, load_config, nested


DEFAULT_COOKIE_NAME = "auto_quote_session"
DEFAULT_SESSION_TTL_SECONDS = 8 * 60 * 60


@dataclass(slots=True)
class AuthSettings:
    enabled: bool
    password: str
    session_secret: str
    session_ttl_seconds: int
    cookie_name: str
    secure_cookie: bool


def get_auth_settings() -> AuthSettings:
    cfg = load_config()

    def _value(env_key: str, config_key: str, default: object = None) -> object:
        value = os.environ.get(env_key)
        if value is not None:
            return value
        return nested(cfg, "auth", config_key, default=default)

    return AuthSettings(
        enabled=as_bool(_value("AUTO_QUOTE_AUTH_ENABLED", "enabled"), default=False),
        password=str(_value("AUTO_QUOTE_AUTH_PASSWORD", "password", default="") or ""),
        session_secret=str(_value("AUTO_QUOTE_AUTH_SESSION_SECRET", "session_secret", default="") or ""),
        session_ttl_seconds=max(
            60,
            int(_value("AUTO_QUOTE_AUTH_SESSION_TTL_SECONDS", "session_ttl_seconds", default=DEFAULT_SESSION_TTL_SECONDS)),
        ),
        cookie_name=str(_value("AUTO_QUOTE_AUTH_COOKIE_NAME", "cookie_name", default=DEFAULT_COOKIE_NAME) or DEFAULT_COOKIE_NAME),
        secure_cookie=as_bool(_value("AUTO_QUOTE_AUTH_SECURE_COOKIE", "secure_cookie"), default=False),
    )


def is_auth_configured(settings: AuthSettings | None = None) -> bool:
    current = settings or get_auth_settings()
    return bool(current.password and current.session_secret)


def verify_password(password: str, settings: AuthSettings | None = None) -> bool:
    current = settings or get_auth_settings()
    if not is_auth_configured(current):
        return False
    return hmac.compare_digest(password, current.password)


def create_session_token(settings: AuthSettings | None = None) -> str:
    current = settings or get_auth_settings()
    expires_at = int(time.time()) + current.session_ttl_seconds
    payload = {"sub": "default", "exp": expires_at}
    payload_bytes = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(payload_bytes, current.session_secret)
    return f"{payload_bytes}.{signature}"


def validate_session_token(token: str, settings: AuthSettings | None = None) -> bool:
    current = settings or get_auth_settings()
    if not token or not is_auth_configured(current) or "." not in token:
        return False
    payload_bytes, signature = token.rsplit(".", 1)
    expected = _sign(payload_bytes, current.session_secret)
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        payload = json.loads(_b64decode(payload_bytes).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    expires_at = _as_int(payload.get("exp"))
    return expires_at is not None and expires_at > int(time.time())


def set_session_cookie(response: Response, settings: AuthSettings | None = None) -> None:
    current = settings or get_auth_settings()
    response.set_cookie(
        current.cookie_name,
        create_session_token(current),
        max_age=current.session_ttl_seconds,
        httponly=True,
        secure=current.secure_cookie,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: AuthSettings | None = None) -> None:
    current = settings or get_auth_settings()
    response.delete_cookie(current.cookie_name, path="/", samesite="lax")


class SinglePasswordAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, exempt_paths: set[str] | None = None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.exempt_paths = exempt_paths or set()

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        settings = get_auth_settings()
        if not settings.enabled or request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path.rstrip("/") or "/"
        if path in self.exempt_paths:
            return await call_next(request)
        token = request.cookies.get(settings.cookie_name, "")
        if validate_session_token(token, settings):
            return await call_next(request)
        return JSONResponse({"detail": "not_authenticated"}, status_code=401)


def _sign(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
