"""
Krishi Bazaar — Farmer web routes.
Handles farmer dashboard, crop harvest management (add, edit, delete listings),
order acceptance/rejection, dispatch, and delivery step progression.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from ..core import uploads
from ..core.database import get_db
from ..core.security import csrf_protect
from ..core.templating import add_flash_message, render_template
from ..models import AuthUser, Order, Product
from ..services import notify, orders as services
from ._helpers import guard, page_error, redirect

router = APIRouter(include_in_schema=False, dependencies=[Depends(csrf_protect)])


def _farmer_order(db: Session, user: AuthUser, order_id: int) -> Optional[Order]:
    order = db.query(Order).filter(Order.id == order_id).first()
    return order if order and order.product.farmer_id == user.id else None


def _own_product(db: Session, user: AuthUser, product_id: int) -> Optional[Product]:
    return db.query(Product).filter(Product.id == product_id, Product.farmer_id == user.id).first()


def _product_values(prod: Optional[Product], user: AuthUser) -> dict:
    if prod is None:
        return {
            "crop_name": "", "category": "other", "description": "", "quantity": "", "unit": "kg", "price": "",
            "location": user.profile.location if user.profile else "", "harvest_date": "",
        }
    return {
        "crop_name": prod.crop_name, "category": prod.category or "other", "description": prod.description or "",
        "quantity": str(prod.quantity), "unit": prod.unit, "price": str(prod.price), "location": prod.location,
        "harvest_date": prod.harvest_date.strftime("%Y-%m-%d") if prod.harvest_date else "",
    }


def _read_product_form(crop_name, category, description, quantity, unit, price, location, harvest_date) -> dict:
    if not crop_name.strip():
        raise services.BusinessError("Crop name is required.")
    if not location.strip():
        raise services.BusinessError("Location is required.")
    return {
        "crop_name": crop_name.strip()[:100],
        "category": services.clean_category(category),
        "description": description.strip(),
        "quantity": services.parse_amount(quantity, "Quantity"),
        "unit": (unit.strip() or "kg")[:20],
        "price": services.parse_amount(price, "Price"),
        "location": location.strip()[:150],
        "harvest_date": services.parse_date(harvest_date),
    }


# ==============================================================================
# Dashboard & Orders
# ==============================================================================
@router.get("/farmer/dashboard/")
def farmer_dashboard_page(request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, "farmer", "/farmer/dashboard/")
    if resp:
        return resp
    products = db.query(Product).filter(Product.farmer_id == user.id).order_by(Product.id.desc()).all()
    orders = db.query(Order).join(Product).filter(Product.farmer_id == user.id).order_by(Order.id.desc()).all()
    return render_template(
        "market/farmer_dashboard.html",
        {"products": products, "orders": orders, "user": user},
        request=request,
    )


@router.post("/farmer/order/{order_id}/delivery-step/{step}/")
def farmer_delivery_step(order_id: int, step: int, request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, "farmer", f"/order/{order_id}/tracking/")
    if resp:
        return resp
    order = db.query(Order).filter(Order.id == order_id).first()
    if order and (user.is_staff or order.product.farmer_id == user.id):
        try:
            services.set_delivery_step(order, step)
            db.commit()
            add_flash_message(request, f"Milestone updated to Phase {step}.", "success")
        except services.BusinessError as exc:
            add_flash_message(request, str(exc), "warning")
    return redirect(f"/order/{order_id}/tracking/")


@router.post("/farmer/order/{order_id}/dispatch/")
def farmer_dispatch(
    order_id: int,
    request: Request,
    courier_partner: str = Form(""),
    tracking_number: str = Form(""),
    dispatch_notes: str = Form(""),
    db: Session = Depends(get_db),
):
    user, resp = guard(request, db, "farmer", "/farmer/dashboard/")
    if resp:
        return resp
    order = _farmer_order(db, user, order_id)
    if order:
        try:
            number = services.dispatch(order, courier_partner, tracking_number, dispatch_notes)
            db.commit()
            notify.order_dispatched(order)
            add_flash_message(request, f"Parcel Handed Over! Tracking Docket #{number} generated.", "success")
        except services.BusinessError as exc:
            add_flash_message(request, str(exc), "warning")
    return redirect("/farmer/dashboard/")


@router.post("/farmer/order/{order_id}/{new_status}/")
def farmer_update_order(order_id: int, new_status: str, request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, "farmer", "/farmer/dashboard/")
    if resp:
        return resp
    order = _farmer_order(db, user, order_id)
    if order:
        try:
            services.change_status(order, new_status)
            db.commit()
            notify.order_status_changed(order)
            add_flash_message(request, f"Order #{order.id} marked as {new_status.capitalize()}.", "success")
        except services.BusinessError as exc:
            db.rollback()
            add_flash_message(request, str(exc), "warning")
    return redirect("/farmer/dashboard/")


# ==============================================================================
# Produce Allotment CRUD
# ==============================================================================
@router.get("/farmer/product/add/")
def product_add_get(request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, "farmer", "/farmer/product/add/")
    if resp:
        return resp
    return render_template("market/product_form.html", {
        "user": user,
        "title": "Register Harvest Allotment",
        "form": {k: {"value": v} for k, v in _product_values(None, user).items()},
    }, request=request)


@router.post("/farmer/product/add/")
def product_add_post(
    request: Request,
    crop_name: str = Form(...),
    category: str = Form("other"),
    description: str = Form(""),
    quantity: str = Form(...),
    unit: str = Form("kg"),
    price: str = Form(...),
    location: str = Form(""),
    harvest_date: str = Form(""),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    user, resp = guard(request, db, "farmer", "/farmer/product/add/")
    if resp:
        return resp
    raw = dict(
        crop_name=crop_name, category=category, description=description, quantity=quantity,
        unit=unit, price=price, location=location, harvest_date=harvest_date,
    )
    try:
        data = _read_product_form(**raw)
        image_path = uploads.save_product_image(image)
    except services.BusinessError as exc:
        return page_error("market/product_form.html", request, str(exc), {
            "user": user, "title": "Register Harvest Allotment", "form": {k: {"value": v} for k, v in raw.items()},
        })
    db.add(Product(farmer_id=user.id, is_active=True, image=image_path or "", **data))
    db.commit()
    add_flash_message(request, f"Harvest allotment for '{data['crop_name']}' published successfully!", "success")
    return redirect("/farmer/dashboard/")


@router.get("/farmer/product/{product_id}/edit/")
def product_edit_get(product_id: int, request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, "farmer", f"/farmer/product/{product_id}/edit/")
    if resp:
        return resp
    prod = _own_product(db, user, product_id)
    if not prod:
        add_flash_message(request, "Harvest record not found.", "danger")
        return redirect("/farmer/dashboard/")
    return render_template("market/product_form.html", {
        "user": user,
        "title": f"Modify Harvest #{prod.id} — {prod.crop_name}",
        "product": prod,
        "form": {k: {"value": v} for k, v in _product_values(prod, user).items()},
    }, request=request)


@router.post("/farmer/product/{product_id}/edit/")
def product_edit_post(
    product_id: int,
    request: Request,
    crop_name: str = Form(...),
    category: str = Form("other"),
    description: str = Form(""),
    quantity: str = Form(...),
    unit: str = Form("kg"),
    price: str = Form(...),
    location: str = Form(""),
    harvest_date: str = Form(""),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    user, resp = guard(request, db, "farmer", f"/farmer/product/{product_id}/edit/")
    if resp:
        return resp
    prod = _own_product(db, user, product_id)
    if not prod:
        add_flash_message(request, "Harvest record not found.", "danger")
        return redirect("/farmer/dashboard/")
    raw = dict(
        crop_name=crop_name, category=category, description=description, quantity=quantity,
        unit=unit, price=price, location=location, harvest_date=harvest_date,
    )
    try:
        data = _read_product_form(**raw)
        image_path = uploads.save_product_image(image)
    except services.BusinessError as exc:
        return page_error("market/product_form.html", request, str(exc), {
            "user": user, "title": f"Modify Harvest #{prod.id} — {prod.crop_name}", "product": prod,
            "form": {k: {"value": v} for k, v in raw.items()},
        })
    for key, value in data.items():
        setattr(prod, key, value)
    if image_path:
        uploads.delete_uploaded_image(prod.image)
        prod.image = image_path
    db.commit()
    add_flash_message(request, f"Listing for '{prod.crop_name}' updated successfully.", "success")
    return redirect("/farmer/dashboard/")


@router.get("/farmer/product/{product_id}/delete/")
def product_delete_get(product_id: int, request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, "farmer", f"/farmer/product/{product_id}/delete/")
    if resp:
        return resp
    prod = _own_product(db, user, product_id)
    if not prod:
        return redirect("/farmer/dashboard/")
    return render_template("market/confirm_delete.html", {"user": user, "object": prod}, request=request)


@router.post("/farmer/product/{product_id}/delete/")
def product_delete_post(product_id: int, request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, "farmer", "/farmer/dashboard/")
    if resp:
        return resp
    prod = _own_product(db, user, product_id)
    if prod:
        prod.is_active = False
        db.commit()
        add_flash_message(request, f"'{prod.crop_name}' de-listed from the public exchange.", "info")
    return redirect("/farmer/dashboard/")
