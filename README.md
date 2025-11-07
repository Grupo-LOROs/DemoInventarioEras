# DemoInventarioEras

Concept-test inventory system for a renewable energy company.  
Backend: **FastAPI + SQLite**. Frontends: **Plain SPA** and **React (Vite)**.  
Includes role-based movements, low-stock reports, discrepancies, product history, barcode scanning (pyzbar), and simple sales (with OUT movement).

> **Note**: I couldn’t fetch the GitHub URL you shared (likely private). This README matches the code and filenames we built together. If your repo paths differ, adjust the folder names below.

---

## ✨ Features

- **Products**: list, search, sort, edit `unit_cost`, `min_stock`, `max_stock`.
- **Movements**: IN/OUT/ADJ with **role rules** (admin, sales, purchasing).
- **Discrepancies**: detect and resolve; CSV export.
- **Low stock**: JSON & CSV export; **bulk min/max** uploader.
- **History**: per-product movement history.
- **Sales**: simple sale (creates OUT movement) + CSV export.
- **Barcode scanning (concept)**: upload image, decode with **pyzbar**; add stock by scan.
- **Auth**: JWT login; `/auth/me` exposes role.
- **SPAs**: Plain HTML/JS and React/Vite SPA with diagnostics (**Configurar API** and **Probar API**).

---

## 🗂️ Repository Layout (suggested)

```
.
├─ api/                     # FastAPI backend
│  ├─ main.py
│  ├─ seed.py
│  ├─ requirements.txt
│  └─ .env.example
├─ frontend/
│  ├─ plain/               # Plain SPA (single index.html)
│  │  └─ index.html
│  └─ react/               # React SPA (Vite)
│     ├─ index.html
│     ├─ package.json
│     └─ src/
│        ├─ App.jsx
│        ├─ api.js
│        └─ components/
│           ├─ Products.jsx
│           ├─ Discrepancies.jsx
│           ├─ LowStock.jsx
│           ├─ Movements.jsx
│           └─ Sales.jsx
└─ data/
   ├─ Almacen_Joined(INVENTARIO).csv
   └─ inventario_limpio.csv
```

> If your repo already has a different structure, keep files in place and only use the commands, endpoints, and env variables below.

---

## ⚙️ Requirements

- **Python** 3.11+
- **Node.js** 18+ and npm (for React SPA)
- **SQLite** (bundled with Python)
- **zbar** system library (for barcode decoding with `pyzbar`)
- **pip** (Python package manager)

### Install zbar (required for barcode decoding)

- **Ubuntu/Debian**
  ```bash
  sudo apt-get update && sudo apt-get install -y libzbar0
  ```

- **Fedora/RHEL**
  ```bash
  sudo dnf install -y zbar
  ```

- **macOS (Homebrew)**
  ```bash
  brew install zbar
  ```

- **Windows**
  - Install zbar via Chocolatey:
    ```powershell
    choco install zbar
    ```
  - Or download zbar binaries and add them to your PATH.

Then install Python libs:
```bash
pip install pyzbar Pillow
```

---

## 🔐 Environment variables

Create `api/.env` (or export environment vars in your shell) based on:

```dotenv
# api/.env.example
DATABASE_URL=sqlite:///./inventory.db
JWT_SECRET=change-me-please-32bytes-min
ACCESS_TOKEN_EXPIRE_MINUTES=43200
CORS_ORIGINS=*
APPROVAL_THRESHOLD=50
```

Copy it:

```bash
cp api/.env.example api/.env
```

---

## 📦 Backend Setup (FastAPI)

### 1) Create and activate a virtual environment

**Linux/macOS**
```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)**
```powershell
cd api
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2) Install dependencies
If your repo has `requirements.txt`, use it. Otherwise:

```bash
pip install fastapi uvicorn[standard] sqlalchemy pydantic passlib[argon2] python-multipart pyjwt pyzbar Pillow
```

> If password hashing with bcrypt gave a 72-byte error earlier, we switched to **argon2** which avoids that limit.

### 3) (Optional) Seed the database

Place your CSV (e.g., `data/inventario_limpio.csv`) and run:

```bash
export DATABASE_URL=sqlite:///./inventory.db   # Windows: $env:DATABASE_URL="sqlite:///./inventory.db"
python seed.py data/inventario_limpio.csv
```

### 4) Create an admin user

**Option A — via `/auth/register`** (if present):
```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123","role":"admin"}'
```

**Option B — directly in the DB:**
```python
# Run in a Python REPL from the 'api' folder
from main import SessionLocal, User
from passlib.hash import argon2
db = SessionLocal()
db.add(User(email="admin@example.com", password_hash=argon2.hash("admin123"), role="admin"))
db.commit(); db.close()
```

### 5) Run the API

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Visit:
- Swagger: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

---

## 🖥️ Frontends

### A) Plain SPA
- Open `frontend/plain/index.html` directly in a browser, or serve it:
  ```bash
  cd frontend/plain
  python -m http.server 8080
  # then open http://127.0.0.1:8080
  ```
- Click **Configurar API** and set `http://127.0.0.1:8000`.
- Click **Probar API** → should show OK for `/health` and `/products_full`.

### B) React SPA (Vite)
```bash
cd frontend/react
npm install
npm run dev
# open the printed URL (usually http://127.0.0.1:5173)
```
- Use **Configurar API** in the header, set `http://127.0.0.1:8000`.
- Use **Probar API** to verify `/health` and `/products_full`.

---

## 🔑 Authentication flow

1. **Login**
   ```bash
   curl -X POST http://127.0.0.1:8000/auth/login \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=admin@example.com&password=admin123"
   ```
   Copy `access_token` from the response.

2. **Swagger Auth**  
   In `/docs`, click **Authorize**, paste `Bearer YOUR_TOKEN`.

3. **Client role**  
   The SPA reads role via `/auth/me` and adjusts UI (e.g., allowed movement types).

---

## 🧾 API Endpoints (summary)

**Health & Auth**
- `GET /health`
- `POST /auth/login`
- `GET /auth/me`

**Products**
- `GET /types`
- `POST /products` — create (admin)
- `PATCH /products/{id}` — update fields (admin)
- `GET /products_full` — query params: `q, type_id, limit, offset, sort, order`
- `GET /export/products.csv` — CSV

**Movements**
- `POST /movements` — role rules:
  - `admin`: IN/OUT/ADJ
  - `sales`: OUT
  - `purchasing`: IN
- `GET /movements`
- `GET /products/{id}/movements` — history per product
- `GET /export/movements.csv`

**Discrepancies**
- `GET /discrepancies`
- `POST /discrepancies/resolve`
- `GET /export/discrepancies.csv`

**Low stock**
- `GET /reports/low_stock`
- `GET /export/low_stock.csv`
- `POST /policies/bulk_minmax` — admin

**Barcode & Sales (concept)**
- `POST /barcode/decode` — upload image, respond with decoded barcodes and matched product
- `POST /sales` — creates sale and OUT movement (admin/sales)
- `GET /sales`
- `GET /export/sales.csv`

---

## 🧪 Quick CLI Examples

```bash
# List first 3 products
curl -s "http://127.0.0.1:8000/products_full?limit=3" | python -m json.tool

# Create a movement (IN 10 units) — admin token required
curl -s -X POST "http://127.0.0.1:8000/movements" \
  -H "Authorization: Bearer YOUR_TOKEN" -H "Content-Type: application/json" \
  -d '{"product_id":1,"movement_type":"IN","quantity":10,"unit_cost":100,"movement_reason":"INIT","note":"seed"}'

# Generate low stock CSV
curl -OJ "http://127.0.0.1:8000/export/low_stock.csv"
```

---

## 🩺 Troubleshooting

- **CORS/NetworkError in SPA**  
  Set `CORS_ORIGINS=*` in `.env`, restart `uvicorn`.

- **`/products_full` 500 error (SQLAlchemy 2.x)**  
  Ensure queries use `from sqlalchemy import case` (not `func.case`).

- **“password cannot be longer than 72 bytes”**  
  Use **argon2** hashing (we do).

- **Barcode decode failure**  
  Install **zbar** system library and `pip install pyzbar Pillow`.

- **Seeded but app shows empty**  
  Confirm the **API** and **seed script** point to the SAME SQLite file:
  `DATABASE_URL=sqlite:///./inventory.db`

- **Role shows as user** in the SPA  
  Ensure `/auth/me` returns the correct role and the SPA is Authorized (token present).

---

## ✅ Production Notes (future)

- Replace SQLite with PostgreSQL (set `DATABASE_URL` accordingly).
- Enable HTTPS and secure `JWT_SECRET` in environment.
- Lock down CORS to trusted origins.
- Add proper migrations (Alembic).
- Add structured logging & metrics.

---

## 📄 License

MIT (or your preferred license).
