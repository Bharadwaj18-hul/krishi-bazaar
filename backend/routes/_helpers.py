"""
Krishi Bazaar — Shared helpers and guards for web routes.
"""
import hashlib
import hmac
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..core import config
from ..core.auth import CART_SESSION_KEY, get_current_user_optional as get_session_user, has_role
from ..core.templating import ADDRESS_TYPE_CHOICES, STATE_CHOICES, add_flash_message, render_template
from ..models import AuthUser, Product
from ..services import orders as services

ROLES = ("farmer", "buyer")

ADDRESS_FIELDS = (
    "full_name", "phone", "street_address", "landmark", "city", "state", "pincode", "address_type", "is_default"
)


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def guard(request: Request, db: Session, role: Optional[str] = None, next_url: str = "/"):
    """Return (user, None) when allowed, otherwise (None, redirect-response)."""
    user = get_session_user(request, db)
    if not user:
        return None, redirect(f"/login/?next={quote(next_url)}")
    if role and not has_role(user, role):
        add_flash_message(request, f"That page is only for {role}s.", "danger")
        return None, redirect("/")
    return user, None


def page_error(template: str, request: Request, message: str, context: Optional[dict] = None, status: int = 400):
    """Re-render a form page with an error banner."""
    add_flash_message(request, message, "danger")
    return render_template(template, {"error": message, **(context or {})}, request=request, status_code=status)


def _hash_otp(code: str) -> str:
    """Return HMAC-SHA256 hash of OTP code using config.SECRET_KEY."""
    return hmac.new(config.SECRET_KEY.encode("utf-8"), code.strip().encode("utf-8"), hashlib.sha256).hexdigest()


def address_form_context(user: AuthUser, values: Optional[dict] = None) -> dict:
    """Context for the address form / checkout 'new address' form (every field always defined)."""
    base = {k: "" for k in ADDRESS_FIELDS}
    base["is_default"] = False
    base.update({
        "full_name": user.first_name or user.username,
        "phone": user.profile.phone if user.profile else "",
        "address_type": "home",
    })
    base.update(values or {})
    ctx = {k: {"value": v} for k, v in base.items()}
    ctx["fields"] = {"state": {"choices": STATE_CHOICES}, "address_type": {"choices": ADDRESS_TYPE_CHOICES}}
    return ctx


def read_address_form(full_name, phone, street_address, landmark, city, state, pincode, address_type) -> dict:
    """Validate address fields; returns clean values or raises BusinessError."""
    data = {
        "full_name": full_name.strip(),
        "phone": phone.strip(),
        "street_address": street_address.strip(),
        "landmark": landmark.strip(),
        "city": city.strip(),
        "state": state.strip(),
        "pincode": pincode.strip(),
        "address_type": address_type if address_type in dict(ADDRESS_TYPE_CHOICES) else "home",
    }
    for key, label in (
        ("full_name", "Full name"),
        ("phone", "Mobile number"),
        ("street_address", "Street address"),
        ("city", "City"),
        ("state", "State"),
    ):
        if not data[key]:
            raise services.BusinessError(f"{label} is required.")
    if not (data["pincode"].isdigit() and len(data["pincode"]) == 6):
        raise services.BusinessError("Pincode must be exactly 6 digits.")
    return data


def get_cart(request: Request) -> dict:
    return request.session.get(CART_SESSION_KEY, {})


def cart_lines(db: Session, cart: dict):
    """Resolve the session cart into (lines, total); drops unavailable products, clamps to stock."""
    lines, total = [], Decimal("0.00")
    for pid, item in cart.items():
        product = db.query(Product).filter(Product.id == int(pid), Product.is_active == True).first()  # noqa: E712
        if not product or product.quantity <= 0:
            continue
        try:
            qty = min(Decimal(str(item.get("quantity", "1"))), product.quantity)
        except Exception:
            continue
        if qty <= 0:
            continue
        price = Decimal(str(product.price))
        subtotal = qty * price
        total += subtotal
        lines.append({
            "product": product,
            "quantity": qty,
            "price": price,
            "subtotal": subtotal,
            "max_available": product.quantity,
        })
    return lines, total
