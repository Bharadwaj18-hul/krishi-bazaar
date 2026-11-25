"""
Krishi Bazaar — SQLAlchemy models.
Table names match the original schema: auth_user, market_profile,
market_product, market_address, market_order.
"""

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Numeric,
    DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .core.database import Base

# Templates were written with Django conventions (`obj.pk`); expose it on every model.
Base.pk = property(lambda self: self.id)


class AuthUser(Base):
    """Django's built-in auth_user table."""
    __tablename__ = "auth_user"

    id = Column(Integer, primary_key=True, index=True)
    password = Column(String(128), nullable=False)
    last_login = Column(DateTime, nullable=True)
    is_superuser = Column(Boolean, default=False)
    username = Column(String(150), unique=True, nullable=False)
    first_name = Column(String(150), default="")
    last_name = Column(String(150), default="")
    email = Column(String(254), default="")
    is_staff = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    date_joined = Column(DateTime, default=func.now())

    # Relationships
    profile = relationship("Profile", back_populates="user", uselist=False)
    products = relationship("Product", back_populates="farmer")
    orders = relationship("Order", back_populates="buyer", foreign_keys="Order.buyer_id")
    addresses = relationship("Address", back_populates="user")
    reviews = relationship("Review", back_populates="user")

    is_authenticated = True

    @property
    def get_full_name(self):
        """Display name. A property (not a method) so Jinja templates print the value."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        return self.first_name or self.username


class Profile(Base):
    """market_profile — extends AuthUser with role, phone, location."""
    __tablename__ = "market_profile"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("auth_user.id"), unique=True, nullable=False)
    role = Column(String(10), nullable=False)       # 'farmer' or 'buyer'
    phone = Column(String(20), default="")
    location = Column(String(150), default="")

    user = relationship("AuthUser", back_populates="profile")


class Product(Base):
    """market_product — crop listings by farmers."""
    __tablename__ = "market_product"

    id = Column(Integer, primary_key=True, index=True)
    farmer_id = Column(Integer, ForeignKey("auth_user.id"), nullable=False)
    crop_name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    quantity = Column(Numeric(10, 2), nullable=False)
    unit = Column(String(20), default="kg")
    price = Column(Numeric(10, 2), nullable=False)
    location = Column(String(150), nullable=False)
    harvest_date = Column(DateTime, nullable=True)
    image = Column(String(100), default="")
    category = Column(String(30), default="other")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    farmer = relationship("AuthUser", back_populates="products")
    orders = relationship("Order", back_populates="product")
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan",
                           order_by="Review.id.desc()")

    @property
    def avg_rating(self):
        """Average star rating (0 when there are no reviews)."""
        if not self.reviews:
            return 0
        return round(sum(r.rating for r in self.reviews) / len(self.reviews), 1)

    @property
    def image_url(self):
        """Public URL of the product photo ('' when there is none)."""
        if not self.image:
            return ""
        if self.image.startswith(("http://", "https://", "/")):
            return self.image
        return f"/media/{self.image}"


class Address(Base):
    """market_address — buyer delivery address book."""
    __tablename__ = "market_address"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("auth_user.id"), nullable=False)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    street_address = Column(String(255), nullable=False)
    landmark = Column(String(150), default="")
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    pincode = Column(String(12), nullable=False)
    address_type = Column(String(15), default="home")
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    user = relationship("AuthUser", back_populates="addresses")
    orders = relationship("Order", back_populates="address")


class Order(Base):
    """market_order — purchase orders placed by buyers."""
    __tablename__ = "market_order"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("market_product.id"), nullable=False)
    buyer_id = Column(Integer, ForeignKey("auth_user.id"), nullable=False)
    address_id = Column(Integer, ForeignKey("market_address.id"), nullable=True)
    quantity = Column(Numeric(10, 2), nullable=False)
    total_price = Column(Numeric(12, 2), nullable=False)
    status = Column(String(12), default="pending")

    # Tracking fields
    tracking_number = Column(String(60), default="")
    courier_partner = Column(String(100), default="Krishi Express Cold-Chain")
    dispatch_notes = Column(String(255), default="")
    dispatched_at = Column(DateTime, nullable=True)
    delivery_step = Column(Integer, default=1)

    # Shipping snapshot
    shipping_name = Column(String(100), default="")
    shipping_phone = Column(String(20), default="")
    shipping_address = Column(Text, default="")
    shipping_city = Column(String(100), default="")
    shipping_state = Column(String(100), default="")
    shipping_pincode = Column(String(12), default="")

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    product = relationship("Product", back_populates="orders")
    buyer = relationship("AuthUser", back_populates="orders", foreign_keys=[buyer_id])
    address = relationship("Address", back_populates="orders")


class Review(Base):
    """market_review — one star rating + comment per buyer per product."""
    __tablename__ = "market_review"
    __table_args__ = (UniqueConstraint("product_id", "user_id", name="uq_review_product_user"),)

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("market_product.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("auth_user.id"), nullable=False)
    rating = Column(Integer, nullable=False)          # 1..5
    comment = Column(String(500), default="")
    created_at = Column(DateTime, default=func.now())

    product = relationship("Product", back_populates="reviews")
    user = relationship("AuthUser", back_populates="reviews")
