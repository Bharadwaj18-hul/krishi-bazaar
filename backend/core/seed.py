"""Krishi Bazaar — automatic initial seeding when starting against an empty database."""
import logging
import os
import secrets
from datetime import datetime, timedelta
from decimal import Decimal

from .auth import hash_password
from .database import SessionLocal
from ..models import AuthUser, Product, Profile

logger = logging.getLogger("krishi.seed")

DEMO_PRODUCTS = [
    ("Ancient Heirloom Black Rice", "products/ancient_heirloom_black_rice.jpg", 380, 400, "kg", "Imphal, Manipur", "grains", "Antioxidant-rich forbidden rice, hand-harvested."),
    ("Coorg Arabica Coffee", "products/coorg_arabica_coffee.jpg", 720, 250, "kg", "Madikeri, Karnataka", "other", "Shade-grown single-estate arabica beans."),
    ("Dehraduni Basmati Rice", "products/dehraduni_basmati_rice.jpg", 210, 900, "kg", "Dehradun, Uttarakhand", "grains", "Long-grain, aged aromatic basmati."),
    ("Guntur Sannam Red Chillies", "products/guntur_sannam_red_chillies.jpg", 260, 500, "kg", "Guntur, Andhra Pradesh", "spices", "Sun-dried chillies with bold heat and colour."),
    ("Himachal Royal Gala Apples", "products/himachal_royal_gala_apples.jpg", 190, 600, "kg", "Shimla, Himachal Pradesh", "fruits", "Crisp orchard apples picked at peak ripeness."),
    ("Himalayan Forest Honey", "products/himalayan_forest_honey.jpg", 650, 120, "kg", "Almora, Uttarakhand", "other", "Raw wild honey, unprocessed and unheated."),
    ("Kashmiri Mongra Saffron", "products/kashmiri_mongra_saffron.jpg", 320, 5, "10 g", "Pampore, Kashmir", "spices", "Grade-A saffron threads with deep colour."),
    ("Lakadong Golden Turmeric", "products/lakadong_golden_turmeric.jpg", 340, 300, "kg", "Jaintia Hills, Meghalaya", "spices", "High-curcumin turmeric, naturally grown."),
    ("Nanjangud Rasabale Bananas", "products/nanjangud_rasabale_bananas.jpg", 85, 350, "dozen", "Nanjangud, Karnataka", "fruits", "GI-tagged sweet banana from Mysuru region."),
    ("Ratnagiri Hapus Mango", "products/ratnagiri_hapus_mango.jpg", 1100, 200, "dozen", "Ratnagiri, Maharashtra", "fruits", "Naturally ripened Alphonso mangoes."),
    ("Tellicherry Black Pepper", "products/tellicherry_black_pepper.jpg", 890, 180, "kg", "Wayanad, Kerala", "spices", "Bold, extra-large peppercorns."),
    ("Vaagai Virgin Sesame Oil", "products/vaagai_virgin_sesame_oil.jpg", 540, 150, "litre", "Erode, Tamil Nadu", "other", "Cold-pressed (chekku) sesame oil."),
    ("Wayanad Green Cardamom", "products/wayanad_green_cardamom.jpg", 2400, 60, "kg", "Wayanad, Kerala", "spices", "Fragrant bold cardamom pods."),
]


def seed_if_empty() -> None:
    """Populate demo users and 13 regional crops only if auth_user is empty."""
    db = SessionLocal()
    try:
        if db.query(AuthUser.id).first() is not None:
            return

        password = os.getenv("SEED_PASSWORD", "").strip()
        generated = False
        if not password:
            password = secrets.token_urlsafe(12)
            generated = True

        pw_hash = hash_password(password)

        admin = AuthUser(
            username="admin",
            email="admin@krishibazaar.local",
            first_name="Platform",
            last_name="Admin",
            password=pw_hash,
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )
        farmer = AuthUser(
            username="farmer1",
            email="farmer1@krishibazaar.local",
            first_name="Ramesh",
            last_name="Gowda",
            password=pw_hash,
            is_active=True,
        )
        buyer = AuthUser(
            username="buyer1",
            email="buyer1@krishibazaar.local",
            first_name="Ananya",
            last_name="Rao",
            password=pw_hash,
            is_active=True,
        )
        db.add_all([admin, farmer, buyer])
        db.flush()

        db.add_all([
            Profile(user_id=farmer.id, role="farmer", phone="9876543210", location="Mysuru, Karnataka"),
            Profile(user_id=buyer.id, role="buyer", phone="9876543211", location="Bengaluru, Karnataka"),
        ])

        harvest = datetime.utcnow() - timedelta(days=2)
        for crop_name, image, price, qty, unit, location, category, desc in DEMO_PRODUCTS:
            db.add(Product(
                farmer_id=farmer.id,
                crop_name=crop_name,
                description=desc,
                quantity=Decimal(str(qty)),
                unit=unit,
                price=Decimal(str(price)),
                location=location,
                harvest_date=harvest,
                image=image,
                category=category,
                is_active=True,
            ))

        db.commit()
        logger.info("Seeded empty database with 3 demo accounts and %d products.", len(DEMO_PRODUCTS))
        if generated:
            logger.warning("Generated demo account password (set SEED_PASSWORD to override): %s", password)
    except Exception:
        db.rollback()
        logger.exception("Failed to auto-seed empty database.")
    finally:
        db.close()
