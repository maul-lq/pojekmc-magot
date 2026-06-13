from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import mysql.connector
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.auth import (
    LoginRateLimiter,
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from backend.config import settings
from backend.hardware import HardwareMQTT
from backend.model import Model
from backend.sistem import PayloadError, Sistem, serialize_row

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
model = Model()
sistem = Sistem(model)
hardware = HardwareMQTT(sistem)
rate_limiter = LoginRateLimiter()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


def ok(data: Any = None) -> dict[str, Any]:
    return {"ok": True, "data": data if data is not None else {}}


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"code": code, "message": message, "details": details or {}},
    }


def ensure_initial_admin() -> None:
    existing = model.get_user_by_username(settings.admin_username)
    if existing:
        return
    if len(settings.admin_password) < 8:
        raise RuntimeError(
            "ADMIN_PASSWORD minimal 8 karakter diperlukan untuk membuat admin awal."
        )
    model.create_user(settings.admin_username, hash_password(settings.admin_password))
    logger.info("Admin awal '%s' berhasil dibuat.", settings.admin_username)


async def retention_loop() -> None:
    while True:
        await asyncio.sleep(86_400)
        try:
            model.cleanup_expired_sessions()
            model.cleanup_old_data()
            logger.info("Pembersihan data dan session terjadwal selesai.")
        except Exception:
            logger.exception("Pembersihan data terjadwal gagal.")


@asynccontextmanager
async def lifespan(application: FastAPI):
    if not settings.session_token_pepper:
        raise RuntimeError("SESSION_TOKEN_PEPPER wajib diatur.")
    model.initialize_schema()
    ensure_initial_admin()
    model.cleanup_expired_sessions()
    model.cleanup_old_data()
    hardware.start()
    cleanup_task = asyncio.create_task(retention_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        hardware.stop()


app = FastAPI(
    title="Smart Maggot Farming API",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body("validation_error", "Data permintaan tidak valid.", exc.errors()),
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict):
        code = detail.get("code", "request_error")
        message = detail.get("message", "Permintaan tidak dapat diproses.")
    else:
        code = "request_error"
        message = str(detail)
    return JSONResponse(status_code=exc.status_code, content=error_body(code, message))


@app.exception_handler(PayloadError)
async def payload_error_handler(request: Request, exc: PayloadError) -> JSONResponse:
    return JSONResponse(status_code=422, content=error_body("invalid_payload", str(exc)))


@app.exception_handler(mysql.connector.Error)
async def database_error_handler(request: Request, exc: mysql.connector.Error) -> JSONResponse:
    logger.exception("Kesalahan MySQL saat memproses %s", request.url.path)
    return JSONResponse(
        status_code=503,
        content=error_body("database_unavailable", "Database sedang tidak dapat diakses."),
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Kesalahan tidak terduga saat memproses %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_body("internal_error", "Terjadi kesalahan pada server."),
    )


def token_hash_from_request(request: Request) -> str | None:
    token = request.cookies.get("maggot_session")
    if not token:
        return None
    return hash_session_token(token, settings.session_token_pepper)


def optional_user(request: Request) -> dict[str, Any] | None:
    token_hash = token_hash_from_request(request)
    if not token_hash:
        return None
    return model.get_user_by_session(token_hash)


def require_user(request: Request) -> dict[str, Any]:
    user = optional_user(request)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "Silakan login terlebih dahulu."},
        )
    return user


def validate_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != settings.app_origin.rstrip("/"):
        raise HTTPException(
            status_code=403,
            detail={"code": "origin_forbidden", "message": "Origin permintaan tidak diizinkan."},
        )


def protected_page(request: Request, filename: str) -> Response:
    if optional_user(request) is None:
        return RedirectResponse("/login", status_code=303)
    return FileResponse(ROOT / "view" / filename)


@app.get("/")
def home(request: Request) -> Response:
    return RedirectResponse("/dashboard" if optional_user(request) else "/login", status_code=303)


@app.get("/login")
def login_page(request: Request) -> Response:
    if optional_user(request):
        return RedirectResponse("/dashboard", status_code=303)
    return FileResponse(ROOT / "view" / "login.html")


@app.get("/dashboard")
def dashboard_page(request: Request) -> Response:
    return protected_page(request, "dashboard.html")


@app.get("/monitor")
def monitor_page(request: Request) -> Response:
    return protected_page(request, "monitor.html")


@app.get("/laporan")
def report_page(request: Request) -> Response:
    return protected_page(request, "laporan.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return FileResponse(ROOT / "favicon.ico", media_type="image/x-icon")


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    validate_origin(request)
    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{payload.username.lower()}"
    if rate_limiter.is_blocked(key):
        raise HTTPException(
            status_code=429,
            detail={"code": "login_rate_limited", "message": "Terlalu banyak percobaan login. Coba lagi nanti."},
        )

    user = model.get_user_by_username(payload.username)
    if not user or not verify_password(payload.password, user["password_hash"]):
        rate_limiter.add_failure(key)
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_credentials", "message": "Username atau password salah."},
        )

    rate_limiter.clear(key)
    token = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.session_lifetime_hours)
    model.create_session(
        user["id"], hash_session_token(token, settings.session_token_pepper), expires_at
    )
    model.update_last_login(user["id"])
    response.set_cookie(
        key="maggot_session",
        value=token,
        max_age=settings.session_lifetime_hours * 3600,
        expires=settings.session_lifetime_hours * 3600,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return ok({"id": user["id"], "username": user["username"]})


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    validate_origin(request)
    token_hash = token_hash_from_request(request)
    if token_hash:
        model.delete_session(token_hash)
    response.delete_cookie("maggot_session", path="/")
    return ok({"message": "Logout berhasil."})


@app.get("/api/auth/me")
def auth_me(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return ok(serialize_row({"id": user["id"], "username": user["username"], "last_login_at": user["last_login_at"]}))


@app.get("/api/sensors/latest")
def sensor_latest(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return ok(sistem.latest())


@app.get("/api/sensors/history")
def sensor_history(
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(120, ge=1, le=2000),
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    if start and end and end <= start:
        raise PayloadError("Waktu akhir harus setelah waktu mulai.")
    return ok(sistem.history(start=start, end=end, limit=limit))


@app.get("/api/dashboard/summary")
def dashboard_summary(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return ok(sistem.dashboard_summary())


@app.get("/api/notifications")
def notifications(
    limit: int = Query(20, ge=1, le=200),
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    return ok({"notifications": [serialize_row(row) for row in model.notifications(limit)]})


def report_range(start_date: str | None, end_date: str | None) -> tuple[datetime, datetime]:
    return sistem.parse_report_range(start_date, end_date)


@app.get("/api/reports/summary")
def report_summary(
    start_date: str | None = None,
    end_date: str | None = None,
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    start, end = report_range(start_date, end_date)
    return ok(sistem.report_summary(start, end))


@app.get("/api/reports/readings")
def report_readings(
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    start, end = report_range(start_date, end_date)
    return ok(sistem.report_readings(start, end, page, page_size))


@app.get("/api/reports/export.pdf")
def export_pdf(
    start_date: str | None = None,
    end_date: str | None = None,
    user: dict[str, Any] = Depends(require_user),
) -> StreamingResponse:
    start, end = report_range(start_date, end_date)
    return StreamingResponse(
        sistem.export_pdf(start, end),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="laporan-sensor-maggot.pdf"'},
    )


@app.get("/api/reports/export.xlsx")
def export_excel(
    start_date: str | None = None,
    end_date: str | None = None,
    user: dict[str, Any] = Depends(require_user),
) -> StreamingResponse:
    start, end = report_range(start_date, end_date)
    return StreamingResponse(
        sistem.export_excel(start, end),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="laporan-sensor-maggot.xlsx"'},
    )


app.mount("/css", StaticFiles(directory=ROOT / "css"), name="css")
app.mount("/js", StaticFiles(directory=ROOT / "js"), name="js")
