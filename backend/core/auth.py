"""
Krishi Bazaar — password hashing and session helpers.
Hashes use PBKDF2-SHA256 in the `pbkdf2_sha256$iterations$salt$hash` format,
so accounts created by the earlier (Django-based) version keep working.
"""
import base64
import hashlib
import hmac
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from . import config
from .database import get_db
from ..models import AuthUser

SESSION_USER_KEY = "user_id"
CART_SESSION_KEY = "krishi_cart"
PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(11)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${base64.b64encode(dk).decode('ascii')}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Constant-time check against a stored hash. Plain-text 'hashes' are never accepted."""
    try:
        algo, iters, salt, expected = (hashed_password or "").split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", plain_password.encode(), salt.encode(), int(iters))
        return hmac.compare_digest(base64.b64encode(dk).decode("ascii"), expected)
    except (ValueError, TypeError):
        return False


def safe_next_url(url: Optional[str]) -> Optional[str]:
    """Allow only same-site relative paths (blocks open redirects like //evil.com)."""
    if url and url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return None


def start_session(request: Request, user: AuthUser) -> None:
    """Log the user in with a fresh session (prevents session fixation) but keep their cart."""
    cart = request.session.get(CART_SESSION_KEY)
    request.session.clear()
    if cart:
        request.session[CART_SESSION_KEY] = cart
    request.session[SESSION_USER_KEY] = user.id


def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[AuthUser]:
    """Logged-in user from the session cookie, or None."""
    user_id = request.session.get(SESSION_USER_KEY)
    if not user_id:
        return None
    return db.query(AuthUser).filter(AuthUser.id == user_id, AuthUser.is_active == True).first()  # noqa: E712


def get_current_user(request: Request, db: Session = Depends(get_db)) -> AuthUser:
    user = get_current_user_optional(request, db)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required. Please sign in.")
    return user


def has_role(user: AuthUser, role: str) -> bool:
    return bool(user.is_staff or (user.profile and user.profile.role == role))


def require_role(role_name: str):
    """Dependency factory: 'farmer' or 'buyer' (staff users pass every check)."""
    def _checker(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if not has_role(user, role_name):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Access forbidden: requires '{role_name}' role.")
        return user
    return _checker


# ---- password reset tokens -------------------------------------------------------
RESET_MAX_AGE = 3600  # seconds
_reset_serializer = URLSafeTimedSerializer(config.SECRET_KEY, salt="krishi-password-reset")


def make_reset_token(user: AuthUser) -> str:
    """Signed, expiring token. It embeds a slice of the current password hash, so it stops
    working as soon as the password is changed (single use)."""
    return _reset_serializer.dumps({"uid": user.id, "h": user.password[-12:]})


def user_from_reset_token(token: str, db: Session) -> Optional[AuthUser]:
    try:
        data = _reset_serializer.loads(token, max_age=RESET_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    user = db.query(AuthUser).filter(AuthUser.id == data.get("uid"), AuthUser.is_active == True).first()  # noqa: E712
    return user if user and user.password[-12:] == data.get("h") else None
