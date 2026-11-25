# 🌾 Krishi Bazaar — Sovereign Agricultural Exchange Platform

A high-performance farmer-to-buyer agricultural marketplace built with **FastAPI**, **SQLAlchemy**, and **Jinja2**. It serves a responsive server-rendered web application and a fully interactive JSON REST API with OpenAPI/Swagger documentation.

---

## 🌟 Key Features

- **Multi-Role Authentication & Security**:
  - Separate accounts for **Farmers**, **Buyers**, and **Platform Administrators**.
  - **Gmail OTP Verification**: Two-step email verification for registration and secure passwordless OTP login.
  - **HMAC-SHA256 OTP Protection**: OTP codes are cryptographically hashed before storing in session state to prevent inspection; strictly compared via constant-time `hmac.compare_digest`.
  - **Google OAuth 2.0 Integration**: One-click "Continue with Google" social authentication.
  - **Brute-Force & Enumeration Defense**: Generic responses for unlisted accounts and IP-aware rate limiting (`enforce_limit`) on login and registration.
  - **CSRF Protection**: Synchronizer token pattern validated on all mutating HTTP actions.
- **Harvest Catalog & Direct Trade**:
  - Cultivators list produce with photo uploads, category tagging (Grains, Fruits, Spices, Plantation, etc.), stock levels, and metric units.
  - Buyers search and filter listings by commodity, region/location, price boundaries, and category.
  - Shopping bag, multi-address book with default setting, and seamless order checkout.
- **Milestone Order Fulfilment & Logistics**:
  - Live 5-stage consignment tracking from harvest allocation to final doorstep delivery.
  - Courier dispatch notes and tracking docket generation.
  - Automatic inventory deduction upon order acceptance.
- **ICAR-Aligned AI Plant Pathology**:
  - Deep agronomic diagnostic engine for Arecanut (Koleroga, Yellow Leaf Disease, Anabe Foot Rot, Bud Rot), Coconut, Rice, Coffee, Black Pepper, Cardamom, Mango, Banana, and Apples.
  - Organic bio-control recipes and chemical remediation guidelines.
- **Automated Email Notifications**:
  - Real-time alerts via Gmail SMTP for OTP verification, order placement, order status transitions, dispatches, and password resets.

---

## 📁 Project Structure

```text
Krishi_Bazaar/
├── app.py                      # ★ FastAPI main application & middleware entry point
├── seed.py                     # Database seeder (creates admin, demo users, & 13 products)
├── render.yaml                 # Infrastructure-as-code Blueprint for Render deployment
├── .python-version             # Python version pin (3.11)
├── requirements.txt            # Production dependencies with upper version bounds
├── requirements-dev.txt        # Development and testing dependencies (pytest, httpx)
├── .env.example                # Sample environment configuration template
├── .gitignore                  # Git ignore rules (.env, venv/, __pycache__/, *.sqlite3)
│
├── backend/
│   ├── config.py               # Central environment configuration & secrets loader
│   ├── database.py             # SQLAlchemy engine, session maker, schema auto-migration
│   ├── models.py               # ORM Models: AuthUser, Profile, Product, Address, Order, Review
│   ├── schemas.py              # Pydantic schemas for request validation & REST responses
│   ├── services.py             # Core business logic (orders, status changes, validation)
│   ├── auth.py                 # PBKDF2 password hashing, cookie sessions, reset tokens
│   ├── security.py             # CSRF verification dependency & in-memory sliding RateLimiter
│   ├── notify.py               # Asynchronous SMTP email delivery engine
│   ├── uploads.py              # Secure image sanitization and filesystem persistence
│   ├── templating.py           # Jinja2 templating extensions & context helpers
│   ├── pathology.py            # AI plant pathology engine & taxonomy catalog
│   ├── catalog.py              # Heavy farm machinery & equipment catalog
│   │
│   ├── data/
│   │   ├── __init__.py
│   │   ├── pathology.json      # Structured ICAR/CPCRI plant disease database
│   │   └── pathology.py        # Lightweight loader for pathology JSON data
│   │
│   └── routes/
│       ├── __init__.py         # Router registry exporting all endpoint collections
│       ├── _helpers.py         # Shared web route helpers, guards, and form readers
│       ├── api.py              # JSON REST API endpoints (/api/...)
│       ├── web_auth.py         # Login, registration, OTP, Google OAuth, & password reset
│       ├── web_market.py       # Homepage, product detail, cart, checkout, & plant health
│       ├── web_farmer.py       # Farmer dashboard, harvest allotments, & order dispatch
│       ├── web_orders.py       # Buyer order tracking, review posting, & address book
│       └── web_admin.py        # Staff-only platform governance console
│
├── frontend/
│   ├── static/                 # CSS stylesheets, JavaScript client helpers, icons
│   └── templates/              # Jinja2 HTML templates
│       ├── market/             # Catalog, cart, checkout, dashboard, tracking templates
│       └── registration/       # Auth portal, Google setup, and password reset templates
│
├── media/                      # Product images (curated photos + dynamic farmer uploads)
│   ├── products/
│   └── equipment/
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Test fixtures, in-memory DB, and CSRF/OTP test client
│   ├── test_flows.py           # E2E test flows (registration, orders, reviews, API)
│   └── test_security.py        # Security test cases (CSRF, rate limiting, OTP leak checks)
│
└── docs/                       # Architectural guides, ER diagram specifications, and SRS
```

---

## 🚀 How to Run Locally

### Prerequisites
- Python 3.11+ installed on your system.

### Step-by-Step Setup

1. **Clone or Open the Repository**:
   ```bash
   cd Krishi_Bazaar
   ```

2. **Create and Activate a Virtual Environment**:
   - **Windows**:
     ```powershell
     python -m venv venv
     .\venv\Scripts\activate
     ```
   - **macOS / Linux**:
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**:
   ```bash
   # Windows
   copy .env.example .env

   # macOS / Linux
   cp .env.example .env
   ```
   Open `.env` and set `SECRET_KEY`. To enable real Gmail OTP and notifications:
   - Provide your Gmail address in `SMTP_USER`.
   - Generate a 16-character Google App Password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) and enter it in `SMTP_PASSWORD`.
   *(When SMTP is unconfigured and `DEBUG=True`, verification codes are displayed on screen for testing).*

5. **Populate Demo Seed Data**:
   ```bash
   python seed.py
   ```
   This initializes the database with 13 regional agricultural crops and 3 demo accounts.

6. **Start the Application**:
   ```bash
   python app.py
   ```
   - **Marketplace Web Portal**: [http://localhost:8000](http://localhost:8000)
   - **Interactive Swagger REST API Docs**: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)
   - **Alternative ReDoc Documentation**: [http://localhost:8000/api/redoc](http://localhost:8000/api/redoc)

---

## 👥 Seeded Demo Accounts

Running `python seed.py` provisions accounts for quick exploration:

| Role | Username | Email | Staff Status | Purpose |
|---|---|---|---|---|
| **Platform Administrator** | `admin` | `admin@krishibazaar.local` | `Yes` (is_staff) | Access `/admin-dashboard/` console and platform metrics |
| **Demo Farmer** | `farmer1` | `farmer1@krishibazaar.local` | `No` | Manage harvest listings and dispatch buyer orders |
| **Demo Buyer** | `buyer1` | `buyer1@krishibazaar.local` | `No` | Browse commodities, place orders, and track shipments |

*Password*: Defined by the `SEED_PASSWORD` environment variable (or a random generated string printed during execution).

---

## 🧪 Running Automated Tests

Run the full automated test suite with `pytest`:

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Execute test suite
pytest -v
```

The test suite covers:
- CSRF token validation and spoof rejection.
- OTP hashing, delivery, and verification flows.
- Production leakage prevention (verifying `dev_otp` is never emitted when `DEBUG=False`).
- Sliding-window rate limit enforcement on web and REST auth endpoints.
- E2E order lifecycle: placement, acceptance, inventory deduction, dispatch, and review.

---

## ☁️ Deployment on Render

This repository includes a production-ready `render.yaml` Blueprint:

1. Push your repository to **GitHub** (local databases `*.sqlite3` and secret `.env` files are automatically excluded by `.gitignore`).
2. Log in to [Render Dashboard](https://dashboard.render.com).
3. Click **New +** → **Blueprint** and select your repository.
4. Render automatically parses `render.yaml` to provision:
   - A **Managed PostgreSQL Database** (`krishi-db`).
   - A **Web Service** (`krishi-bazaar`) running Python 3.11 with automatic schema migrations and database seeding.
5. In the Render Web Service settings under **Environment**, configure:
   - `SEED_PASSWORD`: Master demo account password.
   - `APP_URL`: Your Render public URL (e.g. `https://krishi-bazaar.onrender.com`).
   - `SMTP_USER` / `SMTP_PASSWORD`: For live production email delivery.
6. Future `git push` events to your tracked branch will trigger zero-downtime rolling deploys.

---

## 📄 License
Released under the [MIT License](LICENSE).
