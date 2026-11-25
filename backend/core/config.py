"""
Krishi Bazaar — central configuration.
All settings come from environment variables (optionally loaded from a .env file).
"""
import logging
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger("krishi")


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


DEBUG = _flag("DEBUG")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# --- Database -----------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
if DATABASE_URL.startswith("postgres://"):  # Render/Heroku style URL
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

# --- Sessions / security -------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(48)
    logger.warning(
        "SECRET_KEY is not set - using a temporary random key. "
        "Logins will reset on every restart. Set SECRET_KEY in your environment/.env."
    )
SESSION_HTTPS_ONLY = _flag("SESSION_HTTPS_ONLY")  # set true when served over HTTPS
SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE", str(14 * 24 * 3600)))

# Comma separated list of origins allowed to call the REST API from a browser.
# Empty (default) = same-origin only, which is what the bundled website needs.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

# --- Paths ---------------------------------------------------------------------
FRONTEND_DIR = BASE_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"
MEDIA_DIR = BASE_DIR / "media"

# --- Public URL (used in e-mail links). Leave empty to derive it from the request.
APP_URL = os.getenv("APP_URL", "").rstrip("/")

# --- E-mail notifications (optional). Without SMTP_HOST, messages are written to the log only.
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
if not SMTP_HOST and SMTP_USER and SMTP_PASSWORD and "@gmail" in SMTP_USER.lower():
    SMTP_HOST = "smtp.gmail.com"
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER or "no-reply@krishibazaar.local"

# --- Google OAuth (optional)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()

# --- Uploads
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "3")) * 1024 * 1024
