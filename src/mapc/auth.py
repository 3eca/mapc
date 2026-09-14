"""Single-process administrator sessions. No credentials are stored in cookies."""

import asyncio
import secrets
import time
from collections import deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, SecretStr
from starlette.concurrency import run_in_threadpool

from mapc.settings import AppSettings

COOKIE = "mapc_session"
router = APIRouter(prefix="/auth", tags=["Authorization"])


class AuthStore:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.sessions: dict[str, float] = {}
        self.attempts: deque[float] = deque()
        self.lock = asyncio.Lock()
        self.hasher = PasswordHasher()

    def valid(self, token: str | None) -> bool:
        now = time.monotonic()
        self.sessions = {
            key: expiry for key, expiry in self.sessions.items() if expiry > now
        }
        return token is not None and token in self.sessions

    def issue(self) -> str:
        self.valid(None)
        if len(self.sessions) >= 100:
            del self.sessions[next(iter(self.sessions))]
        token = secrets.token_urlsafe(32)
        self.sessions[token] = time.monotonic() + self.settings.session_ttl
        return token

    def verify(self, username: str, password: str) -> bool:
        try:
            valid = self.hasher.verify(
                self.settings.admin_password.get_secret_value(), password
            )
        except (VerificationError, InvalidHashError):
            valid = False
        return valid and secrets.compare_digest(
            username.encode(), self.settings.admin_user.encode()
        )


class Login(BaseModel):
    username: str = Field(min_length=5, max_length=128)
    password: SecretStr = Field(min_length=5, max_length=1024)


async def guard(request: Request, call_next):
    """Deny by default, including documentation and subsequently added routes."""
    public = (request.method, request.url.path) in {
        ("GET", "/login"),
        ("GET", "/health"),
        ("POST", "/auth/login"),
    }
    public = public or (
        request.method in {"GET", "HEAD"} and request.url.path.startswith("/ui/")
    )
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        # Require the browser's Origin; API clients must provide it as well.
        expected = str(request.base_url).rstrip("/")
        if request.headers.get("origin") != expected:
            return JSONResponse({"detail": "Invalid request origin"}, status_code=403)
    if not public and not request.app.state.auth.valid(request.cookies.get(COOKIE)):
        if request.method == "GET" and request.url.path in {"/", "/docs", "/redoc"}:
            return RedirectResponse("/login", status_code=303)
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@router.post("/login")
async def login(data: Login, request: Request):
    store = request.app.state.auth
    now = time.monotonic()
    while store.attempts and store.attempts[0] <= now - 60:
        store.attempts.popleft()
    if len(store.attempts) >= 10:
        raise HTTPException(
            429,
            "Too many attempts. Please wait a minute.",
            headers={"Retry-After": "60"},
        )
    store.attempts.append(now)
    async with store.lock:
        valid = await run_in_threadpool(
            store.verify, data.username, data.password.get_secret_value()
        )
    if not valid:
        raise HTTPException(401, "Invalid username or password")
    store.sessions.pop(request.cookies.get(COOKIE), None)
    token = store.issue()
    response = JSONResponse({"username": store.settings.admin_user})
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=store.settings.cookie_secure,
        samesite="strict",
        max_age=store.settings.session_ttl,
        path="/",
    )
    return response


@router.post("/logout")
async def logout(request: Request):
    request.app.state.auth.sessions.pop(request.cookies.get(COOKIE), None)
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE, path="/")
    return response


@router.get("/me")
async def me(request: Request):
    return {"username": request.app.state.auth.settings.admin_user}
