"""
Krishi Bazaar — FastAPI application (the single entry point).

Run locally:      python app.py
Run with reload:  uvicorn app:app --reload
Production:       uvicorn app:app --host 0.0.0.0 --port $PORT
"""
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from backend.core import config
from backend.core.database import ensure_schema
from backend.core.seed import seed_if_empty
from backend.routes import (
    api_router,
    web_admin_router,
    web_auth_router,
    web_farmer_router,
    web_market_router,
    web_orders_router,
)
from backend.core.templating import render_template

logger = logging.getLogger("krishi")


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_schema()  # create tables / add new columns on start
    seed_if_empty()  # populate demo accounts & 13 crops only when DB is empty
    yield


app = FastAPI(
    title="Krishi Bazaar API",
    description="Farmer-to-buyer agricultural marketplace: website + REST API.",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Cookie sessions (login + shopping bag)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    max_age=config.SESSION_MAX_AGE,
    same_site="lax",
    https_only=config.SESSION_HTTPS_ONLY,
)

# CORS is only needed when a *different* website calls the API from a browser.
if config.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Static assets and uploaded/product images
config.MEDIA_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
app.mount("/media", StaticFiles(directory=config.MEDIA_DIR), name="media")

# Routes: JSON API under /api, HTML website at /
app.include_router(api_router)
app.include_router(web_auth_router)
app.include_router(web_market_router)
app.include_router(web_farmer_router)
app.include_router(web_orders_router)
app.include_router(web_admin_router)


# ---- Friendly error pages (the JSON API keeps standard JSON errors) ---------------------
ERROR_TITLES = {400: "Bad request", 403: "Access denied", 404: "Page not found", 405: "Not allowed",
                422: "Please check the form", 429: "Slow down a little", 500: "Something went wrong"}


def _error_page(request: Request, status: int, message: str):
    try:
        return render_template("market/error.html", {"status": status, "title": ERROR_TITLES.get(status, "Error"),
                                                      "message": message}, request=request, status_code=status)
    except Exception:  # e.g. no session available while handling a crash
        return render_template("market/error.html", {"status": status, "title": ERROR_TITLES.get(status, "Error"),
                                                      "message": message}, status_code=status)


@app.exception_handler(StarletteHTTPException)
async def on_http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api"):
        return await http_exception_handler(request, exc)
    detail = exc.detail if isinstance(exc.detail, str) and exc.status_code != 404 else "We couldn't find that page."
    return _error_page(request, exc.status_code, detail)


@app.exception_handler(RequestValidationError)
async def on_validation_error(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/api"):
        return await request_validation_exception_handler(request, exc)
    return _error_page(request, 422, "Some required details were missing. Please go back and fill in the form.")


@app.exception_handler(Exception)
async def on_server_error(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    if request.url.path.startswith("/api"):
        return JSONResponse({"detail": "Internal server error"}, status_code=500)
    return _error_page(request, 500, "Our server hit a problem. Please try again in a moment.")


if __name__ == "__main__":
    print(f"Krishi Bazaar -> http://localhost:{config.PORT}   (API docs: /api/docs)")
    uvicorn.run("app:app", host=config.HOST, port=config.PORT, reload=config.DEBUG,
                proxy_headers=True, forwarded_allow_ips="*")
