"""
Krishi Bazaar — Buyer orders and address book web routes.
Handles order placement, buyer order history, milestone delivery tracking, product reviews,
and delivery address management (add, edit, set-default, delete).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import csrf_protect
from ..core.templating import add_flash_message, render_template
from ..models import Address, AuthUser, Order, Product, Review
from ..services import notify, orders as services
from ._helpers import address_form_context, guard, page_error, read_address_form, redirect

router = APIRouter(include_in_schema=False, dependencies=[Depends(csrf_protect)])


def _own_address(db: Session, user: AuthUser, address_id: int) -> Optional[Address]:
    return db.query(Address).filter(Address.id == address_id, Address.user_id == user.id).first()


# ==============================================================================
# Reviews
# ==============================================================================
@router.post("/product/{product_id}/review/")
def review_post(
    product_id: int,
    request: Request,
    rating: str = Form(...),
    comment: str = Form(""),
    db: Session = Depends(get_db),
):
    user, resp = guard(request, db, "buyer", f"/product/{product_id}/")
    if resp:
        return resp
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return redirect("/")
    if not services.has_received_product(db, user, product):
        add_flash_message(request, "You can review a product after your order is delivered.", "warning")
        return redirect(f"/product/{product_id}/")
    try:
        stars = services.parse_rating(rating)
    except services.BusinessError as exc:
        add_flash_message(request, str(exc), "danger")
        return redirect(f"/product/{product_id}/")
    review = db.query(Review).filter(Review.product_id == product_id, Review.user_id == user.id).first()
    if review:
        review.rating, review.comment = stars, comment.strip()[:500]
    else:
        db.add(Review(product_id=product_id, user_id=user.id, rating=stars, comment=comment.strip()[:500]))
    db.commit()
    add_flash_message(request, "Thank you! Your review was saved.", "success")
    return redirect(f"/product/{product_id}/")


# ==============================================================================
# Direct Order Placement
# ==============================================================================
@router.get("/product/{product_id}/order/")
def place_order_get(product_id: int, request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, "buyer", f"/product/{product_id}/order/")
    if resp:
        return resp
    product = db.query(Product).filter(Product.id == product_id, Product.is_active == True).first()  # noqa: E712
    if not product:
        return redirect("/")
    return render_template("market/order_form.html", {"product": product, "user": user}, request=request)


@router.post("/product/{product_id}/order/")
def place_order_post(
    product_id: int,
    request: Request,
    quantity: str = Form(...),
    db: Session = Depends(get_db),
):
    user, resp = guard(request, db, "buyer", f"/product/{product_id}/order/")
    if resp:
        return resp
    product = db.query(Product).filter(Product.id == product_id, Product.is_active == True).first()  # noqa: E712
    if not product:
        return redirect("/")

    address = (db.query(Address).filter(Address.user_id == user.id)
               .order_by(Address.is_default.desc(), Address.id.asc()).first())
    try:
        order = services.create_order(db, user, product, services.parse_amount(quantity, "Quantity"), address)
    except services.BusinessError as exc:
        return page_error("market/order_form.html", request, str(exc), {"product": product, "user": user})
    db.commit()
    notify.order_placed(order)
    add_flash_message(request, f"Order #{order.id} placed successfully with the cultivator!", "success")
    return redirect("/buyer/orders/")


# ==============================================================================
# Address Book
# ==============================================================================
@router.get("/addresses/")
def address_list_page(request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, next_url="/addresses/")
    if resp:
        return resp
    addresses = (db.query(Address).filter(Address.user_id == user.id)
                 .order_by(Address.is_default.desc(), Address.id.desc()).all())
    return render_template("market/address_list.html", {"addresses": addresses, "user": user}, request=request)


@router.get("/addresses/add/")
def address_add_page(request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, next_url="/addresses/add/")
    if resp:
        return resp
    return render_template("market/address_form.html",
                           {"user": user, "is_edit": False, "form": address_form_context(user)}, request=request)


@router.post("/addresses/add/")
def address_add_post(
    request: Request,
    full_name: str = Form(""),
    phone: str = Form(""),
    street_address: str = Form(""),
    landmark: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    pincode: str = Form(""),
    address_type: str = Form("home"),
    is_default: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    user, resp = guard(request, db, next_url="/addresses/add/")
    if resp:
        return resp
    try:
        data = read_address_form(full_name, phone, street_address, landmark, city, state, pincode, address_type)
    except services.BusinessError as exc:
        return page_error("market/address_form.html", request, str(exc), {
            "user": user, "is_edit": False,
            "form": address_form_context(user, {"full_name": full_name, "phone": phone, "street_address": street_address,
                                                "landmark": landmark, "city": city, "state": state,
                                                "pincode": pincode, "address_type": address_type}),
        })
    if is_default:
        db.query(Address).filter(Address.user_id == user.id).update({"is_default": False})
    db.add(Address(user_id=user.id, is_default=bool(is_default), **data))
    db.commit()
    add_flash_message(request, "Delivery address saved successfully.", "success")
    return redirect("/addresses/")


@router.get("/addresses/{address_id}/edit/")
def address_edit_page(address_id: int, request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, next_url=f"/addresses/{address_id}/edit/")
    if resp:
        return resp
    addr = _own_address(db, user, address_id)
    if not addr:
        add_flash_message(request, "Address not found.", "warning")
        return redirect("/addresses/")
    values = {k: getattr(addr, k) for k in ("full_name", "phone", "street_address", "landmark", "city", "state",
                                              "pincode", "address_type")}
    values["is_default"] = addr.is_default
    return render_template("market/address_form.html", {
        "user": user, "is_edit": True, "address": addr, "form": address_form_context(user, values),
    }, request=request)


@router.post("/addresses/{address_id}/edit/")
def address_edit_post(
    address_id: int,
    request: Request,
    full_name: str = Form(""),
    phone: str = Form(""),
    street_address: str = Form(""),
    landmark: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    pincode: str = Form(""),
    address_type: str = Form("home"),
    is_default: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    user, resp = guard(request, db, next_url=f"/addresses/{address_id}/edit/")
    if resp:
        return resp
    addr = _own_address(db, user, address_id)
    if not addr:
        return redirect("/addresses/")
    try:
        data = read_address_form(full_name, phone, street_address, landmark, city, state, pincode, address_type)
    except services.BusinessError as exc:
        return page_error("market/address_form.html", request, str(exc), {
            "user": user, "is_edit": True, "address": addr,
            "form": address_form_context(user, {"full_name": full_name, "phone": phone, "street_address": street_address,
                                                "landmark": landmark, "city": city, "state": state,
                                                "pincode": pincode, "address_type": address_type}),
        })
    if is_default:
        db.query(Address).filter(Address.user_id == user.id).update({"is_default": False})
    for key, value in data.items():
        setattr(addr, key, value)
    addr.is_default = bool(is_default) or addr.is_default
    db.commit()
    add_flash_message(request, "Address updated.", "success")
    return redirect("/addresses/")


@router.post("/addresses/{address_id}/set-default/")
def address_set_default(address_id: int, request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, next_url="/addresses/")
    if resp:
        return resp
    addr = _own_address(db, user, address_id)
    if addr:
        db.query(Address).filter(Address.user_id == user.id).update({"is_default": False})
        addr.is_default = True
        db.commit()
        add_flash_message(request, f"'{addr.city}' set as default address.", "success")
    return redirect("/addresses/")


@router.get("/addresses/{address_id}/delete/")
def address_delete_page(address_id: int, request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, next_url=f"/addresses/{address_id}/delete/")
    if resp:
        return resp
    addr = _own_address(db, user, address_id)
    if not addr:
        return redirect("/addresses/")
    return render_template("market/address_confirm_delete.html", {"user": user, "address": addr}, request=request)


@router.post("/addresses/{address_id}/delete/")
def address_delete_post(address_id: int, request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, next_url="/addresses/")
    if resp:
        return resp
    addr = _own_address(db, user, address_id)
    if addr:
        db.delete(addr)
        db.commit()
        add_flash_message(request, "Address removed.", "info")
    return redirect("/addresses/")


# ==============================================================================
# Orders & Tracking
# ==============================================================================
@router.get("/buyer/orders/")
def buyer_orders_page(request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, next_url="/buyer/orders/")
    if resp:
        return resp
    orders = db.query(Order).filter(Order.buyer_id == user.id).order_by(Order.id.desc()).all()
    return render_template("market/buyer_orders.html", {"orders": orders, "user": user}, request=request)


@router.get("/order/{order_id}/tracking/")
def order_tracking_page(order_id: int, request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, next_url=f"/order/{order_id}/tracking/")
    if resp:
        return resp
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or not services.can_view_order(user, order):
        add_flash_message(request, "Order not found.", "warning")
        return redirect("/")

    step = order.delivery_step
    if order.status == "pending":
        step = 1
    elif order.status == "accepted" and not order.dispatched_at:
        step = max(order.delivery_step, 2)
    elif order.status == "fulfilled" or order.dispatched_at:
        step = max(order.delivery_step, 3)
    return render_template("market/order_tracking.html", {"order": order, "step": step, "user": user},
                           request=request)
