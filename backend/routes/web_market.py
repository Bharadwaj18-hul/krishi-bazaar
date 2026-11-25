"""
Krishi Bazaar — Marketplace public web routes.
Handles home page catalog, search & filtering, static pages, crop health AI diagnostics,
services & equipment rental, and shopping cart / checkout.
"""
import logging
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from ..core import config
from ..core.auth import CART_SESSION_KEY, get_current_user_optional as get_session_user
from ..core.database import get_db
from ..core.security import csrf_protect
from ..core.templating import add_flash_message, render_template
from ..models import Address, Product
from ..services import notify, orders as services
from ..services.catalog import EQUIPMENT_CATALOG
from ..services.pathology import PATHOLOGY_DATABASE, PLANT_TREE_CATALOG, diagnose_specimen
from ._helpers import (
    address_form_context, cart_lines, get_cart, guard, read_address_form, redirect,
)

router = APIRouter(include_in_schema=False, dependencies=[Depends(csrf_protect)])
logger = logging.getLogger("krishi.web.market")


# ==============================================================================
# Home & static pages
# ==============================================================================
@router.get("/")
def home_page(request: Request, db: Session = Depends(get_db)):
    user = get_session_user(request, db)
    params = request.query_params
    q = params.get("q", "").strip()
    location = params.get("location", "").strip()
    category = params.get("category", "").strip()
    sort = params.get("sort", "newest")

    query = db.query(Product).filter(Product.is_active == True)  # noqa: E712
    if category in services.CATEGORY_KEYS:
        query = query.filter(Product.category == category)
    if q:
        term = f"%{q}%"
        query = query.filter(Product.crop_name.ilike(term) | Product.location.ilike(term)
                             | Product.description.ilike(term))
    if location:
        query = query.filter(Product.location.ilike(f"%{location}%"))
    for key, op in (("min_price", "ge"), ("max_price", "le")):
        raw = params.get(key, "").strip()
        if raw:
            try:
                value = Decimal(raw)
                if value.is_finite():
                    query = query.filter(getattr(Product.price, f"__{op}__")(value))
            except Exception:
                pass  # ignore a malformed price filter instead of failing the page

    order_by = {"price_asc": Product.price.asc(), "price_desc": Product.price.desc(),
                "name": Product.crop_name.asc()}.get(sort, Product.id.desc())
    products = query.options(joinedload(Product.farmer), joinedload(Product.reviews)).order_by(order_by).all()
    return render_template("market/home.html", {
        "products": products, "query": q, "user": user, "categories": services.CATEGORIES,
        "selected_category": category, "sort": sort,
    }, request=request)


@router.get("/services/")
def services_page(request: Request, db: Session = Depends(get_db)):
    return render_template("market/services.html", {"user": get_session_user(request, db)}, request=request)


@router.get("/equipment-rental/")
def equipment_rental_page(request: Request, db: Session = Depends(get_db)):
    return render_template("market/equipment_rental.html", {
        "user": get_session_user(request, db), "equipment_catalog": EQUIPMENT_CATALOG,
    }, request=request)


@router.get("/crop-health/")
def crop_health_page(request: Request, db: Session = Depends(get_db)):
    return render_template("market/crop_health.html", {
        "user": get_session_user(request, db),
        "plant_catalog": PLANT_TREE_CATALOG,
        "pathology_db": PATHOLOGY_DATABASE,
    }, request=request)


@router.post("/crop-health/")
async def crop_health_consultation(
    request: Request,
    farmer_name: str = Form(...),
    farmer_phone: str = Form(...),
    crop_type: str = Form("Arecanut"),
    symptoms: str = Form(""),
    db: Session = Depends(get_db),
):
    logger.info("Agronomist consultation booked by %s (%s) for crop: %s, symptoms: %s",
                farmer_name, farmer_phone, crop_type, symptoms)
    if config.SMTP_USER:
        notify.send_email(
            config.SMTP_USER,
            f"🌾 Plant Health Consultation Request: {farmer_name} ({crop_type})",
            f"Farmer: {farmer_name}\nPhone: {farmer_phone}\nCrop Specie: {crop_type}\nSymptoms / Notes: {symptoms}\n\n- Krishi Bazaar Pathology Desk"
        )
    add_flash_message(
        request,
        f"Consultation scheduled! An ICAR-certified plant pathologist will contact {farmer_name} at {farmer_phone} within 4 hours.",
        "success"
    )
    return redirect("/crop-health/#consultationSection")


@router.post("/api/crop-health/diagnose/")
async def crop_health_diagnose(
    request: Request,
    image: Optional[UploadFile] = File(None),
    plant_type: str = Form("auto"),
    part_type: str = Form("all"),
    symptoms: str = Form(""),
    preset_key: str = Form(""),
):
    image_bytes = None
    filename = ""
    if image and image.filename:
        filename = image.filename
        try:
            image_bytes = await image.read()
        except Exception:
            pass

    result = diagnose_specimen(
        image_bytes=image_bytes,
        filename=filename,
        crop_hint=plant_type,
        part_hint=part_type,
        symptoms_text=symptoms,
        preset_key=preset_key,
    )
    return JSONResponse(result)


@router.get("/contact/")
def contact_page(request: Request, db: Session = Depends(get_db)):
    return render_template("market/contact.html", {"user": get_session_user(request, db)}, request=request)


# ==============================================================================
# Produce detail
# ==============================================================================
@router.get("/product/{product_id}/")
def product_detail(product_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_session_user(request, db)
    product = db.query(Product).filter(Product.id == product_id, Product.is_active == True).first()  # noqa: E712
    if not product:
        add_flash_message(request, "Produce not found.", "warning")
        return redirect("/")
    role = user.profile.role if (user and user.profile) else None
    my_review = next((r for r in product.reviews if user and r.user_id == user.id), None)
    return render_template("market/product_detail.html", {
        "product": product, "user": user, "role": role, "reviews": product.reviews,
        "my_review": my_review,
        "can_review": bool(user and role == "buyer" and services.has_received_product(db, user, product)),
    }, request=request)


# ==============================================================================
# Cart & Checkout
# ==============================================================================
@router.get("/cart/")
def cart_detail(request: Request, db: Session = Depends(get_db)):
    user = get_session_user(request, db)
    lines, total = cart_lines(db, get_cart(request))
    return render_template("market/cart_detail.html", {
        "cart": lines, "cart_total": total, "cart_count": len(lines), "user": user,
    }, request=request)


@router.post("/cart/add/{product_id}/")
def cart_add(product_id: int, request: Request, quantity: str = Form("1"), db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id, Product.is_active == True).first()  # noqa: E712
    if not product:
        return redirect("/")
    try:
        qty = services.parse_amount(quantity, "Quantity")
    except services.BusinessError as exc:
        add_flash_message(request, str(exc), "danger")
        return redirect(f"/product/{product_id}/")

    cart = get_cart(request)
    current = Decimal(str(cart.get(str(product_id), {}).get("quantity", "0")))
    new_qty = min(current + qty, product.quantity)
    cart[str(product_id)] = {"quantity": str(new_qty)}
    request.session[CART_SESSION_KEY] = cart
    add_flash_message(request, f"Added {new_qty} {product.unit} of {product.crop_name} to your Bag.", "success")
    return redirect("/cart/")


@router.post("/cart/update/{product_id}/")
def cart_update(product_id: int, request: Request, quantity: str = Form("1"), db: Session = Depends(get_db)):
    cart = get_cart(request)
    pid = str(product_id)
    try:
        qty = Decimal(quantity.strip())
        if not qty.is_finite():
            raise ValueError
    except Exception:
        add_flash_message(request, "Please enter a valid quantity.", "danger")
        return redirect("/cart/")

    if qty <= 0:
        cart.pop(pid, None)
        add_flash_message(request, "Removed item from Bag.", "info")
    elif pid in cart:
        product = db.query(Product).filter(Product.id == product_id).first()
        if product:
            qty = min(qty, product.quantity)
        cart[pid] = {"quantity": str(qty.quantize(services.TWO_PLACES))}
        add_flash_message(request, f"Updated quantity to {qty}.", "success")
    request.session[CART_SESSION_KEY] = cart
    return redirect("/cart/")


@router.post("/cart/remove/{product_id}/")
def cart_remove(product_id: int, request: Request):
    cart = get_cart(request)
    cart.pop(str(product_id), None)
    request.session[CART_SESSION_KEY] = cart
    add_flash_message(request, "Item removed from Bag.", "info")
    return redirect("/cart/")


@router.post("/cart/clear/")
def cart_clear(request: Request):
    request.session[CART_SESSION_KEY] = {}
    add_flash_message(request, "Your Acquisition Bag has been cleared.", "info")
    return redirect("/cart/")


@router.get("/checkout/")
def checkout_get(request: Request, db: Session = Depends(get_db)):
    user, resp = guard(request, db, "buyer", "/checkout/")
    if resp:
        return resp
    lines, total = cart_lines(db, get_cart(request))
    if not lines:
        add_flash_message(request, "Your Acquisition Bag is empty.", "warning")
        return redirect("/")

    addresses = (db.query(Address).filter(Address.user_id == user.id)
                 .order_by(Address.is_default.desc(), Address.id.desc()).all())
    return render_template("market/checkout.html", {
        "cart_items": lines,
        "cart_total": total,
        "addresses": addresses,
        "default_address": addresses[0] if addresses else None,
        "user": user,
        "addr_form": address_form_context(user),
        "show_new_form": not addresses,
    }, request=request)


@router.post("/checkout/")
def checkout_post(
    request: Request,
    address_id: str = Form(...),
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
    user, resp = guard(request, db, "buyer", "/checkout/")
    if resp:
        return resp
    lines, _ = cart_lines(db, get_cart(request))
    if not lines:
        add_flash_message(request, "Your Acquisition Bag is empty.", "warning")
        return redirect("/cart/")

    try:
        if address_id == "new":
            data = read_address_form(full_name, phone, street_address, landmark, city, state, pincode, address_type)
            if is_default:
                db.query(Address).filter(Address.user_id == user.id).update({"is_default": False})
            address = Address(user_id=user.id, is_default=bool(is_default), **data)
            db.add(address)
            db.flush()
        else:
            address = (db.query(Address).filter(Address.id == int(address_id), Address.user_id == user.id).first()
                       if address_id.isdigit() else None)
            if not address:
                raise services.BusinessError("Please choose a delivery address.")

        placed = [services.create_order(db, user, line["product"], line["quantity"], address) for line in lines]
    except services.BusinessError as exc:
        db.rollback()
        add_flash_message(request, str(exc), "danger")
        return redirect("/checkout/")

    db.commit()
    for order in placed:
        notify.order_placed(order)
    request.session[CART_SESSION_KEY] = {}
    add_flash_message(request, f"Order placed! {len(lines)} allotment(s) registered with cultivators.", "success")
    return redirect("/buyer/orders/")
