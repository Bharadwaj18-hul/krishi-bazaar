"""
Krishi Bazaar routes package.
Exposes REST API and website page routers.
"""
from .api import api_router
from .web_admin import router as web_admin_router
from .web_auth import router as web_auth_router
from .web_farmer import router as web_farmer_router
from .web_market import router as web_market_router
from .web_orders import router as web_orders_router

__all__ = [
    "api_router",
    "web_admin_router",
    "web_auth_router",
    "web_farmer_router",
    "web_market_router",
    "web_orders_router",
]
