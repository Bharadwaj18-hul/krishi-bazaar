"""
Krishi Bazaar — Authentication web routes.
Handles registration, login, logout, Gmail OTP verification, Google OAuth, and password resets.
"""
import hmac
import json
import logging
import re
import secrets
import time
import urllib.parse
import urllib.request
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core import config
from ..core.auth import (
    SESSION_USER_KEY, get_current_user_optional as get_session_user,
    hash_password, make_reset_token, safe_next_url, start_session, user_from_reset_token,
    verify_password,
)
from ..core.database import get_db
from ..core.security import csrf_protect, enforce_limit, limiter
from ..core.templating import add_flash_message, render_template
from ..models import AuthUser, Profile
from ..services import notify
from ._helpers import ROLES, _hash_otp, page_error, redirect

router = APIRouter(include_in_schema=False, dependencies=[Depends(csrf_protect)])
logger = logging.getLogger("krishi.web.auth")


# ==============================================================================
# Registration & Login
# ==============================================================================
@router.get("/register/")
def register_get(request: Request, db: Session = Depends(get_db)):
    if get_session_user(request, db):
        return redirect("/")
    return render_template("registration/login.html", {"active_tab": "register"}, request=request)


@router.post("/register/")
def register_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(""),
    first_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    location: str = Form(""),
    role: str = Form("buyer"),
    otp: str = Form(""),
    db: Session = Depends(get_db),
):
    key = enforce_limit(request, "register", 15, 3600)
    limiter.hit(key, 3600)
    username = username.strip()
    first_name = first_name.strip()
    email_clean = email.strip().lower()
    template = "registration/login.html"
    ctx = {
        "active_tab": "register",
        "form": {
            "username": username,
            "first_name": first_name,
            "email": email_clean,
            "phone": phone.strip(),
            "location": location.strip(),
            "role": role,
        },
    }

    if role not in ROLES:
        return page_error(template, request, "Please choose Farmer or Buyer.", context=ctx)
    if not (3 <= len(username) <= 150) or any(ch.isspace() for ch in username):
        return page_error(template, request, "Username must be 3-150 characters with no spaces.", context=ctx)
    if len(password) < 6:
        return page_error(template, request, "Password must be at least 6 characters.", context=ctx)
    if confirm_password and password != confirm_password:
        return page_error(template, request, "Passwords do not match.", context=ctx)
    if db.query(AuthUser).filter(AuthUser.username == username).first():
        return page_error(template, request, "That username is already taken.", context=ctx, status=409)

    # Gmail OTP verification requirement
    if not email_clean or "@" not in email_clean or "." not in email_clean:
        return page_error(template, request, "A valid email address is required for verification.", context=ctx)

    if db.query(AuthUser).filter(func.lower(AuthUser.email) == email_clean).first():
        return page_error(template, request, "That email address is already registered. Please sign in or use another email.", context=ctx, status=409)

    stored_otp = request.session.get("_email_otp")
    otp_ok = False
    if stored_otp and stored_otp.get("email") == email_clean and stored_otp.get("purpose") == "register":
        now_ts = int(time.time())
        if stored_otp.get("verified") is True:
            otp_ok = True
        elif stored_otp.get("code_hash") and hmac.compare_digest(_hash_otp(otp), stored_otp.get("code_hash")) and now_ts <= stored_otp.get("expires_at", 0):
            otp_ok = True

    if not otp_ok:
        return page_error(
            template,
            request,
            "Please enter the 6-digit verification code sent to your Gmail. Click 'Send Code' if you have not received it.",
            context=ctx,
        )

    # Clear OTP after successful use
    request.session.pop("_email_otp", None)

    user = AuthUser(
        username=username,
        first_name=first_name,
        email=email_clean,
        password=hash_password(password),
        is_active=True,
        is_staff=False,
    )
    user.profile = Profile(role=role, phone=phone.strip(), location=location.strip())
    db.add(user)
    db.commit()

    start_session(request, user)
    add_flash_message(request, f"Welcome to Krishi Bazaar, {first_name or username}!", "success")
    return redirect("/farmer/dashboard/" if role == "farmer" else "/")


@router.get("/login/")
def login_get(request: Request, tab: Optional[str] = None, db: Session = Depends(get_db)):
    if get_session_user(request, db):
        return redirect("/")
    return render_template("registration/login.html", {"active_tab": tab or "login"}, request=request)


@router.post("/login/")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    key = enforce_limit(request, "login", 5, 900, username.strip())   # 5 failures / 15 min per IP + username
    user = db.query(AuthUser).filter(AuthUser.username == username.strip()).first()
    if not user or not verify_password(password, user.password):
        limiter.hit(key, 900)
        return page_error("registration/login.html", request, "Invalid username or password.", status=401)
    if not user.is_active:
        return page_error("registration/login.html", request, "This account is disabled.", status=403)

    limiter.reset(key)
    start_session(request, user)
    add_flash_message(request, f"Welcome back, {user.first_name or user.username}!", "success")
    target = safe_next_url(next)
    if target:
        return redirect(target)
    return redirect("/farmer/dashboard/" if user.profile and user.profile.role == "farmer" else "/")


@router.post("/logout/")
def logout_action(request: Request):
    request.session.pop(SESSION_USER_KEY, None)
    add_flash_message(request, "Signed out successfully.", "info")
    return redirect("/")


# --- OTP Handlers (Gmail verification & passwordless login) -------------------
@router.post("/auth/otp/send/")
async def otp_send(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    purpose = str(form.get("purpose", "register")).strip().lower()

    if not email or "@" not in email or "." not in email:
        return JSONResponse({"ok": False, "error": "Please enter a valid email address."}, status_code=400)

    key = enforce_limit(request, "otp_send", 8, 600, email)
    limiter.hit(key, 600)

    if purpose == "login":
        existing = db.query(AuthUser).filter(func.lower(AuthUser.email) == email).first()
        if not existing:
            return JSONResponse({"ok": False, "error": "Invalid email or account not found."}, status_code=400)
        if not existing.is_active:
            return JSONResponse({"ok": False, "error": "This account is disabled."}, status_code=403)

    otp_code = f"{secrets.randbelow(900000) + 100000}"
    request.session["_email_otp"] = {
        "email": email,
        "code_hash": _hash_otp(otp_code),
        "expires_at": int(time.time()) + 600,
        "verified": False,
        "purpose": purpose,
    }

    purpose_label = "Registration" if purpose == "register" else "Account Sign-In"
    email_delivered, delivery_err = notify.send_otp_email(email, otp_code, purpose=purpose_label)

    if email_delivered:
        resp_data = {
            "ok": True,
            "delivery": "smtp",
            "message": f"Verification code sent to your Gmail inbox ({email})! Please check your Inbox and Spam folder.",
            "email": email,
        }
        if config.DEBUG:
            resp_data["dev_otp"] = otp_code
        return JSONResponse(resp_data)
    elif delivery_err == "SMTP_NOT_CONFIGURED":
        if config.DEBUG:
            return JSONResponse({
                "ok": True,
                "delivery": "console",
                "message": f"Gmail SMTP is not configured in .env yet. Code: {otp_code} (Add your Gmail & App Password in .env to receive real emails).",
                "dev_otp": otp_code,
                "email": email,
            })
        return JSONResponse({
            "ok": False,
            "delivery": "failed",
            "error": "Email delivery service is currently unavailable.",
        }, status_code=503)
    else:
        if config.DEBUG:
            return JSONResponse({
                "ok": True,
                "delivery": "failed",
                "message": f"Could not deliver email: {delivery_err}. (Development Code: {otp_code})",
                "dev_otp": otp_code,
                "error_detail": delivery_err,
                "email": email,
            })
        return JSONResponse({
            "ok": False,
            "delivery": "failed",
            "error": "Could not deliver verification email. Please try again later.",
        }, status_code=500)


@router.post("/auth/otp/verify/")
async def otp_verify(request: Request):
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    otp = str(form.get("otp", "")).strip()

    stored = request.session.get("_email_otp")
    if not stored or stored.get("email") != email:
        return JSONResponse({"ok": False, "error": "No verification code was requested for this email. Click 'Send Code' first."}, status_code=400)
    if time.time() > stored.get("expires_at", 0):
        return JSONResponse({"ok": False, "error": "This verification code has expired. Please request a new one."}, status_code=400)
    stored_hash = stored.get("code_hash", "")
    if not stored_hash or not hmac.compare_digest(_hash_otp(otp), stored_hash):
        return JSONResponse({"ok": False, "error": "Invalid verification code. Please check your Gmail."}, status_code=400)

    stored["verified"] = True
    request.session["_email_otp"] = stored
    return JSONResponse({"ok": True, "message": "Email verified successfully!"})


@router.post("/auth/otp/login/")
async def otp_login(
    request: Request,
    email: str = Form(...),
    otp: str = Form(...),
    next: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    email_clean = email.strip().lower()
    otp_code = otp.strip()
    key = enforce_limit(request, "otp_login", 5, 900, email_clean)

    stored = request.session.get("_email_otp")
    if not stored or stored.get("email") != email_clean or stored.get("purpose") != "login":
        limiter.hit(key, 900)
        return page_error("registration/login.html", request, "Invalid credentials.", status=400)
    if time.time() > stored.get("expires_at", 0):
        limiter.hit(key, 900)
        return page_error("registration/login.html", request, "Verification code has expired. Please request a new one.", status=400)
    stored_hash = stored.get("code_hash", "")
    if not stored_hash or not hmac.compare_digest(_hash_otp(otp_code), stored_hash):
        limiter.hit(key, 900)
        return page_error("registration/login.html", request, "Invalid credentials.", status=401)

    user = db.query(AuthUser).filter(func.lower(AuthUser.email) == email_clean).first()
    if not user:
        limiter.hit(key, 900)
        return page_error("registration/login.html", request, "Invalid credentials.", status=400)
    if not user.is_active:
        return page_error("registration/login.html", request, "This account is disabled.", status=403)

    limiter.reset(key)
    request.session.pop("_email_otp", None)
    start_session(request, user)
    add_flash_message(request, f"Welcome back, {user.first_name or user.username}!", "success")
    target = safe_next_url(next)
    if target:
        return redirect(target)
    return redirect("/farmer/dashboard/" if user.profile and user.profile.role == "farmer" else "/")


# --- Google OAuth -------------------------------------------------------------
@router.get("/auth/google/login/")
def google_login(request: Request):
    if not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:
        return render_template("registration/google_setup.html", {}, request=request)

    state = secrets.token_urlsafe(24)
    request.session["google_oauth_state"] = state
    base_url = config.APP_URL or str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/auth/google/callback/"
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return redirect(auth_url)


@router.get("/auth/google/callback/")
def google_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if error:
        add_flash_message(request, f"Google authentication was cancelled: {error}", "error")
        return redirect("/login/")

    expected_state = request.session.pop("google_oauth_state", None)
    if not expected_state or expected_state != state:
        add_flash_message(request, "Google authentication state mismatch. Please try again.", "error")
        return redirect("/login/")

    if not code:
        add_flash_message(request, "Authorization code missing from Google.", "error")
        return redirect("/login/")

    base_url = config.APP_URL or str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/auth/google/callback/"

    # Exchange authorization code for tokens
    token_url = "https://oauth2.googleapis.com/token"
    token_data = urllib.parse.urlencode({
        "code": code,
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode("utf-8")

    req = urllib.request.Request(
        token_url,
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            token_json = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.exception("Google token exchange failed: %s", e)
        add_flash_message(request, "Failed to authenticate with Google. Please try again.", "error")
        return redirect("/login/")

    access_token = token_json.get("access_token")
    if not access_token:
        add_flash_message(request, "Did not receive access token from Google.", "error")
        return redirect("/login/")

    # Fetch user info with access token
    userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    req = urllib.request.Request(userinfo_url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            info = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.exception("Google userinfo fetch failed: %s", e)
        add_flash_message(request, "Failed to fetch profile details from Google.", "error")
        return redirect("/login/")

    email = info.get("email", "").strip().lower()
    name = info.get("name", "").strip()
    if not email:
        add_flash_message(request, "Google account does not provide an email address.", "error")
        return redirect("/login/")

    user = db.query(AuthUser).filter(func.lower(AuthUser.email) == email).first()
    if not user:
        base_username = re.sub(r"[^a-zA-Z0-9_]", "", email.split("@")[0]) or "google_user"
        username = base_username
        idx = 1
        while db.query(AuthUser).filter(AuthUser.username == username).first():
            username = f"{base_username}_{idx}"
            idx += 1

        user = AuthUser(
            username=username,
            first_name=name or username,
            email=email,
            password=hash_password(secrets.token_urlsafe(24)),
            is_active=True,
            is_staff=False,
        )
        user.profile = Profile(role="buyer", phone="", location="")
        db.add(user)
        db.commit()
        add_flash_message(request, f"Welcome to Krishi Bazaar, {user.first_name}!", "success")
    else:
        if not user.is_active:
            add_flash_message(request, "This account is disabled.", "error")
            return redirect("/login/")
        add_flash_message(request, f"Welcome back, {user.first_name or user.username}!", "success")

    start_session(request, user)
    return redirect("/farmer/dashboard/" if user.profile and user.profile.role == "farmer" else "/")


@router.post("/auth/google/mock/")
def google_mock_login(
    request: Request,
    email: str = Form("demo.google.buyer@krishibazaar.local"),
    name: str = Form("Google Demo Patron"),
    role: str = Form("buyer"),
    db: Session = Depends(get_db),
):
    email_clean = email.strip().lower()
    user = db.query(AuthUser).filter(func.lower(AuthUser.email) == email_clean).first()
    if not user:
        base_username = re.sub(r"[^a-zA-Z0-9_]", "", email_clean.split("@")[0]) or "google_demo"
        username = base_username
        idx = 1
        while db.query(AuthUser).filter(AuthUser.username == username).first():
            username = f"{base_username}_{idx}"
            idx += 1

        user = AuthUser(
            username=username,
            first_name=name,
            email=email_clean,
            password=hash_password(secrets.token_urlsafe(24)),
            is_active=True,
            is_staff=False,
        )
        user.profile = Profile(role=role if role in ROLES else "buyer", phone="9876543210", location="Bengaluru")
        db.add(user)
        db.commit()
    elif not user.is_active:
        add_flash_message(request, "This account is disabled.", "error")
        return redirect("/login/")

    start_session(request, user)
    add_flash_message(request, f"Authenticated via Google as {user.first_name}!", "success")
    return redirect("/farmer/dashboard/" if user.profile and user.profile.role == "farmer" else "/")


# ==============================================================================
# Password reset
# ==============================================================================
@router.get("/forgot-password/")
def forgot_get(request: Request):
    return render_template("registration/forgot_password.html", {}, request=request)


@router.post("/forgot-password/")
def forgot_post(request: Request, username: str = Form(""), db: Session = Depends(get_db)):
    key = enforce_limit(request, "forgot", 5, 3600)
    limiter.hit(key, 3600)
    user = db.query(AuthUser).filter(AuthUser.username == username.strip(), AuthUser.is_active == True).first()  # noqa: E712
    if user and user.email:
        base_url = config.APP_URL or str(request.base_url).rstrip("/")
        notify.password_reset(user, f"{base_url}/reset-password/{make_reset_token(user)}/")
    # Same answer whether or not the account exists (no username probing).
    return render_template("registration/forgot_password.html", {"sent": True}, request=request)


@router.get("/reset-password/{token}/")
def reset_get(token: str, request: Request, db: Session = Depends(get_db)):
    if not user_from_reset_token(token, db):
        add_flash_message(request, "That reset link is invalid or has expired.", "danger")
        return redirect("/forgot-password/")
    return render_template("registration/reset_password.html", {"token": token}, request=request)


@router.post("/reset-password/{token}/")
def reset_post(token: str, request: Request, password: str = Form(...), confirm_password: str = Form(""),
               db: Session = Depends(get_db)):
    user = user_from_reset_token(token, db)
    if not user:
        add_flash_message(request, "That reset link is invalid or has expired.", "danger")
        return redirect("/forgot-password/")
    if len(password) < 6:
        return page_error("registration/reset_password.html", request, "Password must be at least 6 characters.",
                          {"token": token})
    if password != confirm_password:
        return page_error("registration/reset_password.html", request, "Passwords do not match.", {"token": token})
    user.password = hash_password(password)
    db.commit()
    add_flash_message(request, "Password changed. Please sign in with your new password.", "success")
    return redirect("/login/")
