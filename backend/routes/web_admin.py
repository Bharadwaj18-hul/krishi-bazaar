"""
Krishi Bazaar — Admin console web routes (staff only).
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.auth import get_current_user_optional as get_session_user
from ..core.database import get_db
from ..core.security import csrf_protect
from ..core.templating import add_flash_message, render_template
from ..models import AuthUser, Order, Product, Profile
from ._helpers import redirect

router = APIRouter(include_in_schema=False, dependencies=[Depends(csrf_protect)])


@router.get("/admin-dashboard/")
def admin_dashboard_page(request: Request, db: Session = Depends(get_db)):
    user = get_session_user(request, db)
    if not user or not user.is_staff:
        add_flash_message(request, "Staff clearance required for the platform console.", "danger")
        return redirect("/login/?next=/admin-dashboard/")

    gross = db.query(func.coalesce(func.sum(Order.total_price), 0)).filter(
        Order.status.in_(["accepted", "fulfilled"])).scalar()
    return render_template("market/admin_dashboard.html", {
        "user": user,
        "users": db.query(AuthUser).count(),
        "farmers": db.query(Profile).filter(Profile.role == "farmer").count(),
        "buyers": db.query(Profile).filter(Profile.role == "buyer").count(),
        "products": db.query(Product).filter(Product.is_active == True).count(),  # noqa: E712
        "orders": db.query(Order).count(),
        "sales": f"{Decimal(str(gross)):,.2f}",
        "recent_orders": db.query(Order).order_by(Order.id.desc()).limit(10).all(),
    }, request=request)
