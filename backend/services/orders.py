"""
Krishi Bazaar — business rules shared by the REST API and the HTML pages.
Keeping them here means there is exactly one implementation of "place an order",
"accept an order", "dispatch an order", etc.
"""
import random
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Address, AuthUser, Order, Product

CATEGORIES = [
    ("grains", "Heritage Grains"), ("fruits", "Orchard Fruits"), ("vegetables", "Fresh Harvest"),
    ("spices", "Estate Spices"), ("other", "Other"),
]
CATEGORY_KEYS = {key for key, _ in CATEGORIES}
TWO_PLACES = Decimal("0.01")
MAX_AMOUNT = Decimal("99999999.99")

# pending -> accepted | rejected ; accepted -> fulfilled
ALLOWED_STATUS_CHANGES = {
    "pending": {"accepted", "rejected"},
    "accepted": {"fulfilled"},
}
DEFAULT_COURIER = "Krishi Express Cold-Chain"


class BusinessError(ValueError):
    """Raised when a request breaks a business rule; the message is safe to show to users."""


def parse_amount(value, label: str = "Value") -> Decimal:
    """Parse a user-typed number: finite, > 0, 2 decimal places, within column limits."""
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise BusinessError(f"{label} must be a valid number.")
    if not number.is_finite() or number <= 0:
        raise BusinessError(f"{label} must be greater than zero.")
    if number > MAX_AMOUNT:
        raise BusinessError(f"{label} is too large.")
    return number.quantize(TWO_PLACES)


def parse_date(value: str) -> Optional[datetime]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise BusinessError("Harvest date must be in YYYY-MM-DD format.")


def tracking_number_for(order: Order) -> str:
    return f"KB-DISP-{order.id:04d}-{''.join(random.choices('0123456789ABCDEF', k=4))}"


def shipping_snapshot(user: AuthUser, address: Optional[Address]) -> dict:
    """Copy delivery details onto the order so later address edits don't rewrite history."""
    if address:
        street = address.street_address + (f", Near {address.landmark}" if address.landmark else "")
        return dict(
            shipping_name=address.full_name, shipping_phone=address.phone, shipping_address=street,
            shipping_city=address.city, shipping_state=address.state, shipping_pincode=address.pincode,
        )
    profile = user.profile
    return dict(
        shipping_name=user.get_full_name,
        shipping_phone=profile.phone if profile else "",
        shipping_address=profile.location if profile else "",
        shipping_city="", shipping_state="", shipping_pincode="",
    )


def create_order(db: Session, buyer: AuthUser, product: Product, quantity: Decimal,
                 address: Optional[Address] = None) -> Order:
    """Add a pending order to the session (caller commits). Stock is deducted when the farmer accepts."""
    if not product.is_active:
        raise BusinessError("This produce is no longer available.")
    if quantity <= 0:
        raise BusinessError("Quantity must be greater than zero.")
    if quantity > product.quantity:
        raise BusinessError(f"Insufficient stock. Only {product.quantity} {product.unit} available.")
    order = Order(
        product_id=product.id,
        buyer_id=buyer.id,
        address_id=address.id if address else None,
        quantity=quantity,
        total_price=(quantity * Decimal(str(product.price))).quantize(TWO_PLACES),
        status="pending",
        delivery_step=1,
        **shipping_snapshot(buyer, address),
    )
    db.add(order)
    return order


def change_status(order: Order, new_status: str) -> None:
    """Apply a farmer's accept / reject / fulfil decision (caller commits)."""
    if new_status not in ALLOWED_STATUS_CHANGES.get(order.status, set()):
        raise BusinessError(f"A {order.status} order cannot be marked {new_status}.")
    if new_status == "accepted":
        stock = Decimal(str(order.product.quantity))
        if order.quantity > stock:
            raise BusinessError(f"Not enough stock to accept: {stock} {order.product.unit} left.")
        order.product.quantity = stock - Decimal(str(order.quantity))
        order.delivery_step = 2
    order.status = new_status


def dispatch(order: Order, courier: str = "", tracking: str = "", notes: str = "") -> str:
    """Hand an accepted order to the carrier (caller commits). Returns the tracking number."""
    if order.status != "accepted":
        raise BusinessError("Only accepted orders can be dispatched.")
    number = (tracking or "").strip() or tracking_number_for(order)
    order.status = "fulfilled"
    order.courier_partner = (courier or "").strip() or DEFAULT_COURIER
    order.tracking_number = number
    order.dispatch_notes = (notes or "").strip() or "Handed to carrier."
    order.dispatched_at = datetime.now()
    order.delivery_step = 3
    return number


def set_delivery_step(order: Order, step: int) -> None:
    if step not in (1, 2, 3, 4, 5):
        raise BusinessError("Step must be between 1 and 5.")
    if order.status not in ("accepted", "fulfilled"):
        raise BusinessError("Accept the order before updating its delivery progress.")
    order.delivery_step = step
    if step == 5:
        order.status = "fulfilled"


def can_view_order(user: AuthUser, order: Order) -> bool:
    return bool(user.is_staff or order.buyer_id == user.id or order.product.farmer_id == user.id)


def clean_category(value: str) -> str:
    return value if value in CATEGORY_KEYS else "other"


def parse_rating(value) -> int:
    try:
        rating = int(str(value).strip())
    except ValueError:
        raise BusinessError("Please choose a rating from 1 to 5 stars.")
    if not 1 <= rating <= 5:
        raise BusinessError("Please choose a rating from 1 to 5 stars.")
    return rating


def has_received_product(db: Session, user: AuthUser, product: Product) -> bool:
    """Only buyers who got this product (a fulfilled order) can review it."""
    return db.query(Order).filter(Order.buyer_id == user.id, Order.product_id == product.id,
                                  Order.status == "fulfilled").first() is not None
