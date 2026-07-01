from __future__ import annotations

import hmac
import os

from dotenv import load_dotenv
from fastapi import Cookie, HTTPException, Request, Response


ADMIN_COOKIE_NAME = "balatro_cn_admin"


def admin_auth_enabled() -> bool:
    load_dotenv()
    return bool(os.environ.get("ADMIN_SECRET_KEY"))


def admin_path_suffix() -> str:
    load_dotenv()
    return os.environ.get("ADMIN_PATH_SUFFIX", "").strip("/")


def admin_route_path() -> str:
    suffix = admin_path_suffix()
    return f"/{suffix}" if suffix else "/admin"


def validate_admin_secret(value: str | None) -> None:
    load_dotenv()
    secret = os.environ.get("ADMIN_SECRET_KEY") or ""
    if not secret:
        return
    if not value or not hmac.compare_digest(value, secret):
        raise HTTPException(status_code=401, detail="admin authorization required")


def set_admin_cookie(response: Response) -> None:
    load_dotenv()
    secret = os.environ.get("ADMIN_SECRET_KEY") or ""
    if not secret:
        return
    response.set_cookie(
        ADMIN_COOKIE_NAME,
        secret,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def require_admin(
    request: Request,
    balatro_cn_admin: str | None = Cookie(default=None),
) -> None:
    cookie_value = balatro_cn_admin or request.cookies.get(ADMIN_COOKIE_NAME)
    validate_admin_secret(cookie_value)
