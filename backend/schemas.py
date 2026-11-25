"""Krishi Bazaar — Pydantic request/response schemas for the REST API."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# --- Users -----------------------------------------------------------------------
class PublicUser(BaseModel):
    """What other people may see about a user (no email / staff flags)."""
    model_config = ConfigDict(from_attributes=True)
    username: str
    first_name: Optional[str] = ""


class ProfileSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    role: str
    phone: Optional[str] = ""
    location: Optional[str] = ""


class UserResponse(PublicUser):
    """The logged-in user's own account."""
    id: int
    email: Optional[str] = ""
    last_name: Optional[str] = ""
    is_staff: bool
    is_active: bool
    profile: Optional[ProfileSchema] = None


class RegisterRequest(BaseModel):
    role: Literal["farmer", "buyer"] = "buyer"
    first_name: str = Field(min_length=1, max_length=150)
    username: str = Field(min_length=3, max_length=150, pattern=r"^\S+$")
    password: str = Field(min_length=6, max_length=128)
    email: Optional[str] = ""
    phone: Optional[str] = ""
    location: Optional[str] = ""


class LoginRequest(BaseModel):
    username: str
    password: str


# --- Products --------------------------------------------------------------------
class ProductCreate(BaseModel):
    crop_name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = ""
    quantity: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    unit: str = Field(default="kg", min_length=1, max_length=20)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    location: str = Field(min_length=1, max_length=150)
    category: Literal["grains", "fruits", "vegetables", "spices", "other"] = "other"
    harvest_date: Optional[date] = None
    is_active: bool = True


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    farmer_id: int
    crop_name: str
    description: Optional[str] = ""
    quantity: Decimal
    unit: str
    price: Decimal
    location: str
    harvest_date: Optional[datetime] = None
    image_url: Optional[str] = ""
    category: Optional[str] = "other"
    avg_rating: float = 0
    is_active: bool
    created_at: Optional[datetime] = None
    farmer: Optional[PublicUser] = None


# --- Addresses -------------------------------------------------------------------
class AddressCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=6, max_length=20)
    street_address: str = Field(min_length=1, max_length=255)
    landmark: Optional[str] = ""
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    pincode: str = Field(pattern=r"^\d{6}$")
    address_type: str = "home"
    is_default: bool = False


class AddressResponse(AddressCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    created_at: Optional[datetime] = None


# --- Orders ----------------------------------------------------------------------
class OrderCreate(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    address_id: Optional[int] = None


class OrderDispatch(BaseModel):
    courier_partner: str = Field(default="Krishi Express Cold-Chain", max_length=100)
    tracking_number: Optional[str] = Field(default=None, max_length=60)
    dispatch_notes: Optional[str] = Field(default="Handed to carrier.", max_length=255)


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    buyer_id: int
    address_id: Optional[int] = None
    quantity: Decimal
    total_price: Decimal
    status: str
    tracking_number: Optional[str] = ""
    courier_partner: Optional[str] = ""
    dispatch_notes: Optional[str] = ""
    dispatched_at: Optional[datetime] = None
    delivery_step: int
    shipping_name: Optional[str] = ""
    shipping_phone: Optional[str] = ""
    shipping_address: Optional[str] = ""
    shipping_city: Optional[str] = ""
    shipping_state: Optional[str] = ""
    shipping_pincode: Optional[str] = ""
    created_at: Optional[datetime] = None
    product: Optional[ProductResponse] = None
    buyer: Optional[PublicUser] = None


# --- Reviews ----------------------------------------------------------------------
class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = Field(default="", max_length=500)


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    rating: int
    comment: Optional[str] = ""
    created_at: Optional[datetime] = None
    user: Optional[PublicUser] = None
