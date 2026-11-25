"""
Krishi Bazaar — REST API (JSON) mounted under /api.
Interactive docs: /api/docs
"""
from datetime import datetime, time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..core import config
from ..core.auth import SESSION_USER_KEY, get_current_user, hash_password, require_role, start_session, verify_password
from ..core.database import get_db
from ..core.security import enforce_limit, limiter
from ..models import Address, AuthUser, Order, Product, Profile, Review
from ..schemas import (
    AddressCreate, AddressResponse, LoginRequest, OrderCreate, OrderDispatch, OrderResponse,
    ProductCreate, ProductResponse, RegisterRequest, ReviewCreate, ReviewResponse, UserResponse,
)
from ..services import notify, orders as services

api_router = APIRouter(prefix="/api")


def _bad_request(exc: services.BusinessError) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ==============================================================================
# General
# ==============================================================================
@api_router.get("/health", tags=["General"])
def health():
    return {"status": "online", "service": "Krishi Bazaar", "version": "2.0.0"}


# ==============================================================================
# Auth
# ==============================================================================
@api_router.post("/auth/register", response_model=UserResponse, status_code=201, tags=["Auth"])
def register_user(data: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    """Register a new Farmer or Buyer account."""
    if not config.DEBUG:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "API registration is disabled in production. Please register via the website.")
    key = enforce_limit(request, "api_register", 10, 3600)
    limiter.hit(key, 3600)

    if not data.email or "@" not in data.email or "." not in data.email:
        raise HTTPException(400, "A valid email address is required.")

    if db.query(AuthUser).filter(AuthUser.username == data.username).first():
        raise HTTPException(400, "Username already registered.")
    if db.query(AuthUser).filter(func.lower(AuthUser.email) == data.email.strip().lower()).first():
        raise HTTPException(400, "Email already registered.")
    if data.role not in ("farmer", "buyer"):
        raise HTTPException(400, "Role must be 'farmer' or 'buyer'.")

    user = AuthUser(
        username=data.username, first_name=data.first_name, email=data.email.strip().lower(),
        password=hash_password(data.password), is_active=True, is_staff=False,
    )
    user.profile = Profile(role=data.role, phone=data.phone or "", location=data.location or "")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@api_router.post("/auth/login", tags=["Auth"])
def login_user(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    key = enforce_limit(request, "api_login", 5, 900, data.username)
    user = db.query(AuthUser).filter(AuthUser.username == data.username).first()
    if not user or not verify_password(data.password, user.password):
        limiter.hit(key, 900)
        raise HTTPException(401, "Invalid username or password.")
    if not user.is_active:
        raise HTTPException(403, "Account is disabled.")
    limiter.reset(key)
    start_session(request, user)
    return {
        "message": "Login successful",
        "user_id": user.id,
        "username": user.username,
        "role": user.profile.role if user.profile else "admin",
    }


@api_router.post("/auth/logout", tags=["Auth"])
def logout_user(request: Request):
    request.session.pop(SESSION_USER_KEY, None)
    return {"message": "Logged out successfully."}


@api_router.get("/auth/me", response_model=UserResponse, tags=["Auth"])
def me(user: AuthUser = Depends(get_current_user)):
    return user


# ==============================================================================
# Products
# ==============================================================================
@api_router.get("/products", response_model=List[ProductResponse], tags=["Products"])
def list_products(search: Optional[str] = None, category: Optional[str] = None, db: Session = Depends(get_db)):
    """Public catalogue of in-stock listings (filter with ?search= and ?category=)."""
    query = db.query(Product).options(joinedload(Product.farmer)).filter(Product.is_active == True, Product.quantity > 0)  # noqa: E712
    if search:
        term = f"%{search}%"
        query = query.filter(
            Product.crop_name.ilike(term) | Product.location.ilike(term) | Product.description.ilike(term)
        )
    if category:
        query = query.filter(Product.category == category)
    return query.order_by(Product.id.desc()).all()


@api_router.get("/products/{product_id}", response_model=ProductResponse, tags=["Products"])
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id, Product.is_active == True).first()  # noqa: E712
    if not product:
        raise HTTPException(404, "Product not found.")
    return product


@api_router.post("/products", response_model=ProductResponse, status_code=201, tags=["Products"])
def create_product(data: ProductCreate, user: AuthUser = Depends(require_role("farmer")),
                   db: Session = Depends(get_db)):
    """Create a listing (farmers only)."""
    product = Product(
        farmer_id=user.id, crop_name=data.crop_name.strip(), description=data.description or "",
        quantity=data.quantity, unit=data.unit.strip(), price=data.price, location=data.location.strip(),
        category=data.category,
        harvest_date=datetime.combine(data.harvest_date, time.min) if data.harvest_date else None,
        is_active=data.is_active,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


# ---- reviews ---------------------------------------------------------------------
@api_router.get("/products/{product_id}/reviews", response_model=List[ReviewResponse], tags=["Reviews"])
def list_reviews(product_id: int, db: Session = Depends(get_db)):
    return db.query(Review).filter(Review.product_id == product_id).order_by(Review.id.desc()).all()


@api_router.post("/products/{product_id}/reviews", response_model=ReviewResponse, status_code=201, tags=["Reviews"])
def add_review(product_id: int, data: ReviewCreate, user: AuthUser = Depends(require_role("buyer")),
               db: Session = Depends(get_db)):
    """Rate a product (buyers whose order for it was delivered). Posting again updates your review."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(404, "Product not found.")
    if not services.has_received_product(db, user, product):
        raise HTTPException(403, "You can review a product after your order is delivered.")
    review = db.query(Review).filter(Review.product_id == product_id, Review.user_id == user.id).first()
    if review:
        review.rating, review.comment = data.rating, data.comment or ""
    else:
        review = Review(product_id=product_id, user_id=user.id, rating=data.rating, comment=data.comment or "")
        db.add(review)
    db.commit()
    db.refresh(review)
    return review


# ==============================================================================
# Address book
# ==============================================================================
@api_router.get("/addresses", response_model=List[AddressResponse], tags=["Addresses"])
def list_addresses(user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return (db.query(Address).filter(Address.user_id == user.id)
            .order_by(Address.is_default.desc(), Address.id.desc()).all())


@api_router.post("/addresses", response_model=AddressResponse, status_code=201, tags=["Addresses"])
def create_address(data: AddressCreate, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.is_default:
        db.query(Address).filter(Address.user_id == user.id).update({"is_default": False})
    address = Address(user_id=user.id, **{**data.model_dump(), "landmark": data.landmark or ""})
    db.add(address)
    db.commit()
    db.refresh(address)
    return address


def _own_address(db: Session, user: AuthUser, address_id: int) -> Address:
    address = db.query(Address).filter(Address.id == address_id, Address.user_id == user.id).first()
    if not address:
        raise HTTPException(404, "Address not found.")
    return address


@api_router.put("/addresses/{address_id}/set-default", tags=["Addresses"])
def set_default_address(address_id: int, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    address = _own_address(db, user, address_id)
    db.query(Address).filter(Address.user_id == user.id).update({"is_default": False})
    address.is_default = True
    db.commit()
    return {"message": f"Address at {address.city} marked as default."}


@api_router.delete("/addresses/{address_id}", tags=["Addresses"])
def delete_address(address_id: int, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_own_address(db, user, address_id))
    db.commit()
    return {"message": "Address removed successfully."}


# ==============================================================================
# Orders
# ==============================================================================
def _owned_order(db: Session, order_id: int, farmer: AuthUser) -> Order:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.product.farmer_id != farmer.id:
        raise HTTPException(404, "Order not found.")
    return order


@api_router.post("/orders", response_model=OrderResponse, status_code=201, tags=["Orders"])
def place_order(data: OrderCreate, user: AuthUser = Depends(require_role("buyer")), db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == data.product_id, Product.is_active == True).first()  # noqa: E712
    if not product:
        raise HTTPException(404, "Product not available.")
    address = None
    if data.address_id:
        address = db.query(Address).filter(Address.id == data.address_id, Address.user_id == user.id).first()
        if not address:
            raise HTTPException(404, "Address not found.")
    try:
        order = services.create_order(db, user, product, data.quantity, address)
    except services.BusinessError as exc:
        raise _bad_request(exc)
    db.commit()
    db.refresh(order)
    notify.order_placed(order)
    return order


@api_router.get("/orders/buyer", response_model=List[OrderResponse], tags=["Orders"])
def buyer_orders(user: AuthUser = Depends(require_role("buyer")), db: Session = Depends(get_db)):
    return db.query(Order).filter(Order.buyer_id == user.id).order_by(Order.id.desc()).all()


@api_router.get("/orders/farmer", response_model=List[OrderResponse], tags=["Orders"])
def farmer_orders(user: AuthUser = Depends(require_role("farmer")), db: Session = Depends(get_db)):
    return db.query(Order).join(Product).filter(Product.farmer_id == user.id).order_by(Order.id.desc()).all()


@api_router.get("/orders/{order_id}/tracking", tags=["Orders"])
def order_tracking(order_id: int, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found.")
    if not services.can_view_order(user, order):
        raise HTTPException(403, "You are not allowed to view this order.")
    farmer = order.product.farmer
    show_contact = order.status in ("accepted", "fulfilled") and farmer.profile
    return {
        "order_id": order.id,
        "commodity": order.product.crop_name,
        "quantity": float(order.quantity),
        "unit": order.product.unit,
        "status": order.status,
        "delivery_step": order.delivery_step,
        "tracking_number": order.tracking_number,
        "courier_partner": order.courier_partner,
        "dispatch_notes": order.dispatch_notes,
        "dispatched_at": order.dispatched_at,
        "origin_estate": order.product.location,
        "destination_address": f"{order.shipping_address}, {order.shipping_city}, "
                               f"{order.shipping_state} - {order.shipping_pincode}",
        "farmer_contact": farmer.profile.phone if show_contact else "Locked until accepted",
    }


@api_router.post("/orders/{order_id}/accept", tags=["Orders"])
def accept_order(order_id: int, user: AuthUser = Depends(require_role("farmer")), db: Session = Depends(get_db)):
    order = _owned_order(db, order_id, user)
    try:
        services.change_status(order, "accepted")
    except services.BusinessError as exc:
        raise _bad_request(exc)
    db.commit()
    notify.order_status_changed(order)
    return {"order_id": order.id, "status": order.status, "stock_left": float(order.product.quantity)}


@api_router.post("/orders/{order_id}/reject", tags=["Orders"])
def reject_order(order_id: int, user: AuthUser = Depends(require_role("farmer")), db: Session = Depends(get_db)):
    order = _owned_order(db, order_id, user)
    try:
        services.change_status(order, "rejected")
    except services.BusinessError as exc:
        raise _bad_request(exc)
    db.commit()
    notify.order_status_changed(order)
    return {"order_id": order.id, "status": order.status}


@api_router.post("/orders/{order_id}/dispatch", tags=["Orders"])
def dispatch_order(order_id: int, data: OrderDispatch, user: AuthUser = Depends(require_role("farmer")),
                   db: Session = Depends(get_db)):
    order = _owned_order(db, order_id, user)
    try:
        number = services.dispatch(order, data.courier_partner, data.tracking_number or "", data.dispatch_notes or "")
    except services.BusinessError as exc:
        raise _bad_request(exc)
    db.commit()
    notify.order_dispatched(order)
    return {
        "message": "Consignment dispatched and parcel handed over to carrier.",
        "tracking_number": number,
        "courier_partner": order.courier_partner,
        "delivery_step": order.delivery_step,
    }


@api_router.put("/orders/{order_id}/delivery-step/{step}", tags=["Orders"])
def advance_delivery_step(order_id: int, step: int, user: AuthUser = Depends(require_role("farmer")),
                          db: Session = Depends(get_db)):
    order = _owned_order(db, order_id, user)
    try:
        services.set_delivery_step(order, step)
    except services.BusinessError as exc:
        raise _bad_request(exc)
    db.commit()
    return {"order_id": order.id, "delivery_step": order.delivery_step, "status": order.status}
