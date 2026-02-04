import os
import shutil
import enum
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
import io, csv as _csv

from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import (create_engine, Column, Integer, String, Float, Text, DateTime, ForeignKey, CheckConstraint,
                        func, select, and_, or_, case)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session

# ---------- pzybar support --------
try:
    from pyzbar.pyzbar import decode as zbar_decode
    _HAS_PYZBAR = True
    _PYZBAR_ERR = ""
except Exception as _e:
    _HAS_PYZBAR = False
    _PYZBAR_ERR = str(_e)
from PIL import Image

# ---------- .env support ----------
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ---------- Config ----------
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./inventory.db")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
APPROVAL_THRESHOLD = int(os.getenv("APPROVAL_THRESHOLD", "1000"))

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

pwd_context = CryptContext(
    schemes=["argon2", "pbkdf2_sha256"],  # modern + portable fallback
    deprecated="auto",
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# ---------- Models ----------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="user")
    created_at = Column(DateTime, default=datetime.utcnow)

class ProductType(Base):
    __tablename__ = "product_types"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    id_code = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    unit_cost = Column(Float)
    product_type_id = Column(Integer, ForeignKey("product_types.id"), nullable=True)
    min_stock = Column(Integer, nullable=True)
    max_stock = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product_type = relationship("ProductType")
    movements = relationship("InventoryMovement", back_populates="product", cascade="all, delete")

class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    movement_type = Column(String, nullable=False)  # IN, OUT, ADJ
    movement_reason = Column(String, nullable=True) # purchase, sale, return, transfer, adjustment
    quantity = Column(Integer, nullable=False)
    unit_cost = Column(Float, nullable=True)
    note = Column(Text, nullable=True)
    moved_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="movements")
    __table_args__ = (
        CheckConstraint("movement_type IN ('IN','OUT','ADJ')", name="movement_type_check"),
    )

class DiscrepancyResolution(Base):
    __tablename__ = "discrepancy_resolutions"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    discrepancy_type = Column(String, nullable=False) # UNIT_COST_MISSING, BELOW_MIN_STOCK, ABOVE_MAX_STOCK
    note = Column(Text, nullable=True)
    stock_at = Column(Integer, nullable=True)
    unit_cost_at = Column(Float, nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime, default=datetime.utcnow)

class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    customer = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    total = Column(Float, nullable=True)

class SaleItem(Base):
    __tablename__ = "sale_items"
    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id", ondelete="CASCADE"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=True)
    subtotal = Column(Float, nullable=True)

# --- NUEVOS MODELOS PARA ÓRDENES ---
class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class OrderType(str, enum.Enum):
    SALE = "SALE"       # Salida de mercancía
    PURCHASE = "PURCHASE" # Entrada de mercancía

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_code = Column(String, unique=True, index=True) # Ej: ORD-2026-001
    customer_name = Column(String) # Cliente o Proveedor
    type = Column(String) # SALE o PURCHASE
    status = Column(String, default=OrderStatus.PENDING)
    evidence_photo_url = Column(String, nullable=True) # Ruta de la foto
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relación con items
    items = relationship("OrderItem", back_populates="order")

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer) # Cantidad requerida
    
    order = relationship("Order", back_populates="items")
    product = relationship("Product") # Para acceder al código y descripción

class Warehouse(Base):
    __tablename__ = "warehouses"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    location = Column(String)


# ---------- Pydantic ----------
class Token(BaseModel):
    access_token: str
    token_type: str

class UserCreate(BaseModel):
    email: str
    password: str
    role: Optional[str] = "user"

class UserOut(BaseModel):
    id: int
    email: str
    role: str
    class Config: orm_mode = True

class ProductTypeIn(BaseModel):
    name: str

class ProductTypeOut(BaseModel):
    id: int
    name: str
    class Config: orm_mode = True

class ProductIn(BaseModel):
    id_code: str
    description: str
    unit_cost: Optional[float] = None
    product_type_id: Optional[int] = None
    min_stock: Optional[int] = None
    max_stock: Optional[int] = None

class ProductUpdate(BaseModel):
    description: Optional[str] = None
    unit_cost: Optional[float] = None
    product_type_id: Optional[int] = None
    min_stock: Optional[int] = None
    max_stock: Optional[int] = None

class ProductOut(BaseModel):
    id: int
    id_code: str
    description: str
    unit_cost: Optional[float]
    product_type_id: Optional[int]
    min_stock: Optional[int]
    max_stock: Optional[int]
    class Config: orm_mode = True

class MovementIn(BaseModel):
    product_id: int
    movement_type: str
    quantity: int
    unit_cost: Optional[float] = None
    note: Optional[str] = None
    movement_reason: Optional[str] = None
    moved_at: Optional[datetime] = None

class MovementOut(BaseModel):
    id: int
    product_id: int
    movement_type: str
    movement_reason: Optional[str]
    quantity: int
    unit_cost: Optional[float]
    note: Optional[str]
    moved_at: datetime
    class Config: orm_mode = True

class ProductFull(BaseModel):
    id: int
    id_code: str
    description: str
    unit_cost: Optional[float]
    stock: int
    valuation: float
    product_type: Optional[str]
    min_stock: Optional[int]
    max_stock: Optional[int]
    class Config: orm_mode = True

class Discrepancy(BaseModel):
    product_id: int
    id_code: str
    description: str
    discrepancy_type: str
    detail: str
    stock: int
    unit_cost: Optional[float]

class ResolveIn(BaseModel):
    product_id: int
    discrepancy_type: str
    note: Optional[str] = None

class MinMaxRow(BaseModel):
    id_code: str
    min_stock: Optional[int] = None
    max_stock: Optional[int] = None

class SaleIn(BaseModel):
    product_id: Optional[int] = None
    id_code: Optional[str] = None
    quantity: int
    unit_price: Optional[float] = None
    customer: Optional[str] = None
    note: Optional[str] = None

class SaleOut(BaseModel):
    id: int
    created_at: datetime
    product_id: int
    id_code: str
    quantity: int
    unit_price: Optional[float]
    subtotal: float
    total: float
    customer: Optional[str]
    note: Optional[str]

class UserUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None

# --- SCHEMAS PARA ÓRDENES ---
class OrderItemOut(BaseModel):
    product_id: int
    product_code: str
    description: str
    quantity: int
    
    class Config:
        from_attributes = True

class OrderOut(BaseModel):
    id: int
    order_code: str
    type: str
    customer_name: str
    status: str
    items: List[OrderItemOut]

    class Config:
        from_attributes = True

class WarehouseCreate(BaseModel):
    name: str
    location: str

class TransferRequest(BaseModel):
    product_id: int
    from_warehouse_id: int
    to_warehouse_id: int
    quantity: int
    notes: Optional[str] = None

# ---------- Auth helpers ----------

def _normalize_password(p: str) -> str:
    if p is None:
        return ""
    b = p.encode("utf-8")
    if len(b) > 72:
        # still truncate for compatibility if you later re-enable bcrypt
        p = b[:72].decode("utf-8", errors="ignore")
    return p

def get_password_hash(password):
    password = _normalize_password(password)
    return pwd_context.hash(password)

def verify_password(plain_password, password_hash):
    plain_password = _normalize_password(plain_password)
    return pwd_context.verify(plain_password, password_hash)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(db=Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user

def require_admin(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Forbidden")
    return user

def _current_stock_subquery(db):
    stock_expr = func.sum(
        case(
            (InventoryMovement.movement_type == "IN",  InventoryMovement.quantity),
            (InventoryMovement.movement_type == "OUT", -InventoryMovement.quantity),
            else_=InventoryMovement.quantity,
        )
    )
    return (
        db.query(
            InventoryMovement.product_id,
            stock_expr.label("stock")
        ).group_by(InventoryMovement.product_id)
    ).subquery()

def _require_sales_role(user: User):
    if user.role not in ("admin", "sales"):
        raise HTTPException(403, f"Role '{user.role}' no puede crear ventas")
    
# ---------- App ----------
app = FastAPI(title="Inventory API v2", version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Startup: create tables (dev) ----------
Base.metadata.create_all(bind=engine)

# ---------- Folders ----------
os.makedirs("uploads/evidence", exist_ok=True)

# ---------- Routes ----------
@app.get("/health")
def health():
    return {"status":"ok","time": datetime.utcnow().isoformat()}

# Auth
@app.post("/auth/register", response_model=UserOut)
def register(user: UserCreate, db=Depends(get_db)):
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(400, "Email already registered")
    u = User(email=user.email, password_hash=get_password_hash(user.password), role=user.role)
    db.add(u); db.commit(); db.refresh(u)
    return u

@app.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(400, "Incorrect username or password")
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/auth/me")
def auth_me(user: User = Depends(get_current_user)):
    return {"email": user.email, "role": user.role}

# Product Types
@app.get("/types", response_model=List[ProductTypeOut])
def list_types(db=Depends(get_db)):
    return db.query(ProductType).order_by(ProductType.name).all()

@app.post("/types", response_model=ProductTypeOut, dependencies=[Depends(require_admin)])
def create_type(pt: ProductTypeIn, db=Depends(get_db)):
    existing = db.query(ProductType).filter(ProductType.name == pt.name).first()
    if existing: raise HTTPException(400, "Type already exists")
    obj = ProductType(name=pt.name); db.add(obj); db.commit(); db.refresh(obj); return obj

# Products
@app.get("/products", response_model=List[ProductOut])
def list_products(q: Optional[str] = None, type_id: Optional[int] = None, limit: int = 200, offset: int = 0, db=Depends(get_db)):
    stmt = db.query(Product)
    if q:
        like = f"%{q}%"
        stmt = stmt.filter((Product.id_code.like(like)) | (Product.description.like(like)))
    if type_id:
        stmt = stmt.filter(Product.product_type_id == type_id)
    stmt = stmt.order_by(Product.id_code).limit(limit).offset(offset)
    return stmt.all()

@app.post("/products", response_model=ProductOut, dependencies=[Depends(require_admin)])
def create_product(p: ProductIn, db=Depends(get_db)):
    if db.query(Product).filter(Product.id_code == p.id_code).first():
        raise HTTPException(400, "Product id_code already exists")
    obj = Product(id_code=p.id_code, description=p.description, unit_cost=p.unit_cost, product_type_id=p.product_type_id,
                  min_stock=p.min_stock, max_stock=p.max_stock)
    db.add(obj); db.commit(); db.refresh(obj); return obj

@app.patch("/products/{id}", response_model=ProductOut, dependencies=[Depends(require_admin)])
def update_product(id: int, p: ProductUpdate, db=Depends(get_db)):
    prod = db.query(Product).filter(Product.id == id).first()
    if not prod: raise HTTPException(404, "Product not found")
    for field, value in p.dict(exclude_unset=True).items():
        setattr(prod, field, value)
    db.commit(); db.refresh(prod); return prod

@app.get("/movements")
def list_movements(limit: int = 50, offset: int = 0, order: str = "desc", db=Depends(get_db)):
    q = db.query(
        InventoryMovement.id,
        InventoryMovement.product_id,
        Product.id_code,
        Product.description,
        InventoryMovement.movement_type,
        InventoryMovement.quantity,
        InventoryMovement.unit_cost,
        InventoryMovement.moved_at,
        InventoryMovement.movement_reason,
        InventoryMovement.note,
    ).join(Product, Product.id == InventoryMovement.product_id)
    if order.lower() == "asc":
        q = q.order_by(InventoryMovement.moved_at.asc())
    else:
        q = q.order_by(InventoryMovement.moved_at.desc())
    rows = q.limit(limit).offset(offset).all()
    return [dict(
        id=r[0], product_id=r[1], id_code=r[2], description=r[3],
        movement_type=r[4], quantity=r[5], unit_cost=r[6], moved_at=r[7],
        movement_reason=r[8], note=r[9]
    ) for r in rows]

@app.post("/movements", response_model=MovementOut)
def create_movement(m: MovementIn, user: User = Depends(get_current_user), db=Depends(get_db)):
    # Role-based policy
    allowed_by_role = {
        "admin": {"IN", "OUT", "ADJ"},
        "user": {"IN", "OUT", "ADJ"},
    }
    allowed = allowed_by_role.get(user.role, set())

    if m.movement_type not in {"IN", "OUT", "ADJ"}:
        raise HTTPException(400, "movement_type must be IN, OUT, or ADJ")
    if m.movement_type not in allowed:
        raise HTTPException(403, f"Role '{user.role}' cannot create {m.movement_type} movements")

    prod = db.query(Product).filter(Product.id == m.product_id).first()
    if not prod:
        raise HTTPException(404, "Product not found")

    # large OUT/ADJ require admin
    if (m.movement_type in ("OUT", "ADJ")) and abs(m.quantity) >= APPROVAL_THRESHOLD and user.role != "admin":
        raise HTTPException(403, f"Movements of |qty|>={APPROVAL_THRESHOLD} require admin")

    moved_at = m.moved_at or datetime.utcnow()
    obj = InventoryMovement(
        product_id=m.product_id,
        movement_type=m.movement_type,
        quantity=m.quantity,
        unit_cost=m.unit_cost,
        note=m.note,
        moved_at=m.moved_at or datetime.utcnow(),
        movement_reason=m.movement_reason,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

# Derived stock/valuation
@app.get("/products_full", response_model=List[ProductFull])
def products_full(q: Optional[str] = None, type_id: Optional[int] = None,
                  limit: int = 50, offset: int = 0,
                  sort: str = "id_code", order: str = "asc",
                  db=Depends(get_db)):
    stock_expr = func.sum(
        case(
            (InventoryMovement.movement_type == "IN",  InventoryMovement.quantity),
            (InventoryMovement.movement_type == "OUT", -InventoryMovement.quantity),
            else_=InventoryMovement.quantity)
        )
    subq = (
    db.query(
        InventoryMovement.product_id,
        stock_expr.label("stock")
        ).group_by(InventoryMovement.product_id)).subquery()


    selectable = (db.query(Product.id, Product.id_code, Product.description, Product.unit_cost,
                      func.coalesce(subq.c.stock, 0).label("stock"),
                      (func.coalesce(subq.c.stock, 0) * func.coalesce(Product.unit_cost, 0.0)).label("valuation"),
                      ProductType.name.label("product_type"),
                      Product.min_stock, Product.max_stock)
             .outerjoin(subq, subq.c.product_id == Product.id)
             .outerjoin(ProductType, ProductType.id == Product.product_type_id))

    if q:
        like = f"%{q}%"
        selectable = selectable.filter(or_(Product.id_code.like(like), Product.description.like(like)))
    if type_id:
        selectable = selectable.filter(Product.product_type_id == type_id)

    sort_map = {
        "id_code": Product.id_code,
        "description": Product.description,
        "unit_cost": Product.unit_cost,
        "stock": func.coalesce(subq.c.stock, 0),
        "valuation": (func.coalesce(subq.c.stock, 0) * func.coalesce(Product.unit_cost, 0.0)),
        "product_type": ProductType.name
    }
    sort_col = sort_map.get(sort, Product.id_code)
    selectable = selectable.order_by(sort_col.desc() if order.lower() == "desc" else sort_col.asc())

    rows = selectable.limit(limit).offset(offset).all()
    return [ProductFull(
        id=r[0], id_code=r[1], description=r[2], unit_cost=r[3], stock=int(r[4] or 0), valuation=float(r[5] or 0.0),
        product_type=r[6], min_stock=r[7], max_stock=r[8]
    ) for r in rows]

# Discrepancies
@app.get("/discrepancies", response_model=List[Discrepancy])
def list_discrepancies(db=Depends(get_db)):
    stock_expr = func.sum(
        case(
            (InventoryMovement.movement_type == "IN",  InventoryMovement.quantity),
            (InventoryMovement.movement_type == "OUT", -InventoryMovement.quantity),
            else_=InventoryMovement.quantity
        )
    )
    subq = (
        db.query(
            InventoryMovement.product_id,
            stock_expr.label("stock")
        )
        .group_by(InventoryMovement.product_id)).subquery()

    rows = (db.query(Product.id, Product.id_code, Product.description, Product.unit_cost,
                     func.coalesce(subq.c.stock, 0).label("stock"),
                     Product.min_stock, Product.max_stock)
            .outerjoin(subq, subq.c.product_id == Product.id)
            ).all()

    discrepancies = []
    for pid, code, desc, unit_cost, stock, min_stock, max_stock in rows:
        candidates = []
        if (unit_cost is None or unit_cost == 0) and (stock or 0) > 0:
            candidates.append(("UNIT_COST_MISSING", "Stock > 0 pero unit_cost nulo o 0"))
        if min_stock is not None and stock is not None and stock < min_stock:
            candidates.append(("BELOW_MIN_STOCK", f"Stock {stock} < Min {min_stock}"))
        if max_stock is not None and stock is not None and stock > max_stock:
            candidates.append(("ABOVE_MAX_STOCK", f"Stock {stock} > Max {max_stock}"))
        for dtype, detail in candidates:
            res = (db.query(DiscrepancyResolution)
                     .filter(DiscrepancyResolution.product_id == pid,
                             DiscrepancyResolution.discrepancy_type == dtype,
                             DiscrepancyResolution.stock_at == stock,
                             DiscrepancyResolution.unit_cost_at == unit_cost)
                     ).first()
            if res:
                continue
            discrepancies.append(Discrepancy(product_id=pid, id_code=code, description=desc,
                                             discrepancy_type=dtype, detail=detail, stock=int(stock or 0),
                                             unit_cost=unit_cost))
    return discrepancies

@app.post("/discrepancies/resolve")
def resolve_discrepancy(body: ResolveIn, user: User = Depends(get_current_user), db=Depends(get_db)):
    stock = (db.query(func.coalesce(func.sum(func.case([(InventoryMovement.movement_type == "IN", InventoryMovement.quantity),
                                                        (InventoryMovement.movement_type == "OUT", -InventoryMovement.quantity)],
                                                       else_=InventoryMovement.quantity)), 0))
               .filter(InventoryMovement.product_id == body.product_id).scalar())
    unit_cost = db.query(Product.unit_cost).filter(Product.id == body.product_id).scalar()
    rec = DiscrepancyResolution(product_id=body.product_id, discrepancy_type=body.discrepancy_type,
                                note=body.note, stock_at=int(stock or 0), unit_cost_at=unit_cost,
                                resolved_by=user.id, resolved_at=datetime.utcnow())
    db.add(rec); db.commit()
    return {"status": "resolved", "product_id": body.product_id, "type": body.discrepancy_type}

@app.get("/products/{product_id}/movements")
def product_history(product_id: int, limit: int = 50, offset: int = 0, order: str = "desc", db=Depends(get_db)):
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(404, "Product not found")
    q = db.query(
        InventoryMovement.id,
        InventoryMovement.movement_type,
        InventoryMovement.quantity,
        InventoryMovement.unit_cost,
        InventoryMovement.moved_at,
        InventoryMovement.movement_reason,
        InventoryMovement.note,
    ).filter(InventoryMovement.product_id == product_id)
    if order.lower() == "asc":
        q = q.order_by(InventoryMovement.moved_at.asc())
    else:
        q = q.order_by(InventoryMovement.moved_at.desc())
    rows = q.limit(limit).offset(offset).all()
    return [dict(
        id=r[0], movement_type=r[1], quantity=r[2], unit_cost=r[3],
        moved_at=r[4], movement_reason=r[5], note=r[6]
    ) for r in rows]

@app.get("/export/movements.csv")
def export_movements(limit: int = 1000, offset: int = 0, order: str = "desc", db=Depends(get_db)):
    data = list_movements(limit=limit, offset=offset, order=order, db=db)
    out = io.StringIO()
    w = _csv.writer(out)
    w.writerow(["id","id_code","description","movement_type","quantity","unit_cost","moved_at","movement_reason","note"])
    for r in data:
        w.writerow([r["id"], r["id_code"], r["description"], r["movement_type"], r["quantity"], r["unit_cost"], r["moved_at"], r["movement_reason"] or "", r["note"] or ""])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=movements.csv"})

@app.get("/export/products.csv")
def export_products(q: Optional[str] = None, type_id: Optional[int] = None, db=Depends(get_db)):
    # Reuse the same products_full query (without pagination) for export
    subq = (db.query(
                InventoryMovement.product_id,
                func.sum(func.case([(InventoryMovement.movement_type == "IN", InventoryMovement.quantity),
                                    (InventoryMovement.movement_type == "OUT", -InventoryMovement.quantity)],
                                   else_=InventoryMovement.quantity)).label("stock")
            ).group_by(InventoryMovement.product_id)).subquery()

    query = (db.query(Product.id_code, Product.description, Product.unit_cost,
                      func.coalesce(subq.c.stock, 0).label("stock"),
                      (func.coalesce(subq.c.stock, 0) * func.coalesce(Product.unit_cost, 0.0)).label("valuation"),
                      ProductType.name.label("product_type"),
                      Product.min_stock, Product.max_stock)
             .outerjoin(subq, subq.c.product_id == Product.id)
             .outerjoin(ProductType, ProductType.id == Product.product_type_id))

    if q:
        like = f"%{q}%"
        query = query.filter((Product.id_code.like(like)) | (Product.description.like(like)))
    if type_id:
        query = query.filter(Product.product_type_id == type_id)

    rows = query.order_by(Product.id_code).all()

    output = io.StringIO()
    writer = _csv.writer(output)
    writer.writerow(["codigo","descripcion","costo_unitario","stock","valuacion","tipo","min_stock","max_stock"])
    for r in rows:
        writer.writerow([r[0], r[1], r[2] if r[2] is not None else "", int(r[3] or 0), float(r[4] or 0.0), r[5] or "", r[6] or "", r[7] or ""])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=productos.csv"})

@app.get("/export/discrepancies.csv")
def export_discrepancies(db=Depends(get_db)):
    # Build the discrepancies list as in /discrepancies
    subq = (db.query(
                InventoryMovement.product_id,
                func.sum(func.case([(InventoryMovement.movement_type == "IN", InventoryMovement.quantity),
                                    (InventoryMovement.movement_type == "OUT", -InventoryMovement.quantity)],
                                   else_=InventoryMovement.quantity)).label("stock")
            ).group_by(InventoryMovement.product_id)).subquery()

    rows = (db.query(Product.id, Product.id_code, Product.description, Product.unit_cost,
                     func.coalesce(subq.c.stock, 0).label("stock"),
                     Product.min_stock, Product.max_stock)
            .outerjoin(subq, subq.c.product_id == Product.id)
            ).all()

    discrepancies = []
    for pid, code, desc, unit_cost, stock, min_stock, max_stock in rows:
        candidates = []
        if (unit_cost is None or unit_cost == 0) and (stock or 0) > 0:
            candidates.append(("UNIT_COST_MISSING", "Stock > 0 pero unit_cost nulo o 0"))
        if min_stock is not None and stock is not None and stock < min_stock:
            candidates.append(("BELOW_MIN_STOCK", f"Stock {stock} < Min {min_stock}"))
        if max_stock is not None and stock is not None and stock > max_stock:
            candidates.append(("ABOVE_MAX_STOCK", f"Stock {stock} > Max {max_stock}"))
        for dtype, detail in candidates:
            res = (db.query(DiscrepancyResolution)
                     .filter(DiscrepancyResolution.product_id == pid,
                             DiscrepancyResolution.discrepancy_type == dtype,
                             DiscrepancyResolution.stock_at == stock,
                             DiscrepancyResolution.unit_cost_at == unit_cost)
                     ).first()
            if res:
                continue
            discrepancies.append((code, desc, dtype, detail, int(stock or 0), unit_cost))

    output = io.StringIO()
    writer = _csv.writer(output)
    writer.writerow(["codigo","descripcion","discrepancia","detalle","stock","costo_unitario"])
    for row in discrepancies:
        writer.writerow(row)
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=discrepancias.csv"})

def _current_stock_subquery(db):
    from sqlalchemy import case
    stock_expr = func.sum(
        case(
            (InventoryMovement.movement_type == "IN",  InventoryMovement.quantity),
            (InventoryMovement.movement_type == "OUT", -InventoryMovement.quantity),
            else_=InventoryMovement.quantity,
        )
    )
    return (
        db.query(
            InventoryMovement.product_id,
            stock_expr.label("stock")
        ).group_by(InventoryMovement.product_id)
    ).subquery()

@app.get("/reports/low_stock")
def report_low_stock(db=Depends(get_db)):
    subq = _current_stock_subquery(db)
    rows = (
        db.query(
            Product.id_code,
            Product.description,
            Product.unit_cost,
            func.coalesce(subq.c.stock, 0).label("stock"),
            Product.min_stock,
            Product.max_stock,
            ProductType.name.label("product_type"),
        )
        .outerjoin(subq, subq.c.product_id == Product.id)
        .outerjoin(ProductType, ProductType.id == Product.product_type_id)
        .filter(Product.min_stock.isnot(None))
        .filter(func.coalesce(subq.c.stock, 0) < Product.min_stock)
        .order_by(Product.id_code)
        .all()
    )
    return [
        {
            "codigo": r[0],
            "descripcion": r[1],
            "costo_unitario": r[2],
            "stock": int(r[3] or 0),
            "min_stock": r[4],
            "max_stock": r[5],
            "tipo": r[6],
            "faltante": int((r[4] or 0) - int(r[3] or 0)),
        }
        for r in rows
    ]

@app.get("/export/low_stock.csv")
def export_low_stock(db=Depends(get_db)):
    data = report_low_stock(db)
    output = io.StringIO()
    writer = _csv.writer(output)
    writer.writerow(["codigo","descripcion","tipo","stock","min_stock","faltante","costo_unitario"])
    for r in data:
        writer.writerow([
            r["codigo"], r["descripcion"], r["tipo"] or "",
            r["stock"], r["min_stock"] or "", r["faltante"], r["costo_unitario"] or ""
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=low_stock.csv"},
    )

@app.post("/policies/bulk_minmax", dependencies=[Depends(require_admin)])
def bulk_minmax(rows: List[MinMaxRow], db=Depends(get_db)):
    updated, missing = 0, []
    for r in rows:
        p = db.query(Product).filter(Product.id_code == r.id_code).first()
        if not p:
            missing.append(r.id_code)
            continue
        if r.min_stock is not None:
            p.min_stock = r.min_stock
        if r.max_stock is not None:
            p.max_stock = r.max_stock
        updated += 1
    db.commit()
    return {"updated": updated, "missing_id_codes": missing}

@app.post("/barcode/decode")
def barcode_decode(file: UploadFile = File(...), db=Depends(get_db)):
    if not _HAS_PYZBAR:
        raise HTTPException(
            status_code=501,
            detail=f"pyzbar/zbar no disponible: install zbar + pip install pyzbar Pillow. Loader error: {_PYZBAR_ERR}"
        )
    try:
        img_bytes = file.file.read()
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    except Exception as e:
        raise HTTPException(400, f"Imagen inválida: {e}")

    results = zbar_decode(img)
    payload = []
    for r in results:
        code = r.data.decode("utf-8", errors="ignore").strip()
        sym = r.type
        prod = db.query(Product).filter(Product.id_code == code).first()
        payload.append({
            "data": code,
            "symbology": sym,
            "product": None if not prod else {
                "id": prod.id,
                "id_code": prod.id_code,
                "description": prod.description
            }
        })
    return {"count": len(payload), "barcodes": payload}

@app.post("/sales", response_model=SaleOut)
def create_sale(s: SaleIn, user: User = Depends(get_current_user), db=Depends(get_db)):
    _require_sales_role(user)
    if not s.product_id and not s.id_code:
        raise HTTPException(400, "Provide product_id or id_code")

    if s.product_id:
        prod = db.query(Product).filter(Product.id == s.product_id).first()
    else:
        prod = db.query(Product).filter(Product.id_code == s.id_code).first()

    if not prod:
        raise HTTPException(404, "Product not found")

    qty = int(s.quantity)
    if qty <= 0:
        raise HTTPException(400, "quantity must be > 0")

    unit_price = s.unit_price if s.unit_price is not None else prod.unit_cost
    unit_price = float(unit_price) if unit_price is not None else 0.0
    subtotal = unit_price * qty

    sale = Sale(customer=s.customer, note=s.note, total=subtotal)
    db.add(sale); db.commit(); db.refresh(sale)

    item = SaleItem(sale_id=sale.id, product_id=prod.id, quantity=qty, unit_price=unit_price, subtotal=subtotal)
    db.add(item)

    # Register OUT movement linked logically via note/reason
    mv = InventoryMovement(
        product_id=prod.id,
        movement_type="OUT",
        quantity=qty,
        unit_cost=unit_price,
        movement_reason="SALE",
        note=f"SALE #{sale.id}" + (f" · {s.note}" if s.note else "")
    )
    db.add(mv)
    db.commit()

    return SaleOut(
        id=sale.id,
        created_at=sale.created_at,
        product_id=prod.id,
        id_code=prod.id_code,
        quantity=qty,
        unit_price=unit_price,
        subtotal=subtotal,
        total=subtotal,
        customer=sale.customer,
        note=sale.note
    )

@app.get("/sales")
def list_sales(limit: int = 50, offset: int = 0, order: str = "desc", db=Depends(get_db)):
    q = (
        db.query(
            Sale.id, Sale.created_at, Sale.customer, Sale.note, Sale.total,
            SaleItem.product_id, Product.id_code, Product.description,
            SaleItem.quantity, SaleItem.unit_price, SaleItem.subtotal
        )
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .join(Product, Product.id == SaleItem.product_id)
    )
    q = q.order_by(Sale.created_at.asc() if order.lower()=="asc" else Sale.created_at.desc())
    rows = q.limit(limit).offset(offset).all()
    return [dict(
        id=r[0], created_at=r[1], customer=r[2], note=r[3], total=r[4],
        product_id=r[5], id_code=r[6], description=r[7],
        quantity=r[8], unit_price=r[9], subtotal=r[10],
    ) for r in rows]

@app.get("/export/sales.csv")
def export_sales(limit: int = 1000, offset: int = 0, order: str = "desc", db=Depends(get_db)):
    data = list_sales(limit=limit, offset=offset, order=order, db=db)
    out = io.StringIO(); w = _csv.writer(out)
    w.writerow(["sale_id","created_at","customer","id_code","description","quantity","unit_price","subtotal","total","note"])
    for r in data:
        w.writerow([r["id"], r["created_at"], r["customer"] or "", r["id_code"], r["description"], r["quantity"], r["unit_price"] or "", r["subtotal"], r["total"], r["note"] or ""])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition":"attachment; filename=sales.csv"})

@app.get("/users", response_model=List[UserOut], dependencies=[Depends(require_admin)])
def list_users(limit: int = 50, offset: int = 0, db=Depends(get_db)):
    """
    Lista usuarios (admin only). Paginado: limit/offset.
    """
    users = db.query(User).order_by(User.email).offset(offset).limit(limit).all()
    return users

@app.post("/users", response_model=UserOut, dependencies=[Depends(require_admin)])
def create_user_admin(payload: UserCreate, db=Depends(get_db)):
    """
    Crear usuario (admin). Usa la misma Pydantic UserCreate (email,password,role).
    """
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(400, "Email already registered")
    u = User(email=payload.email, password_hash=get_password_hash(payload.password), role=payload.role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u

@app.get("/users/{user_id}", response_model=UserOut, dependencies=[Depends(require_admin)])
def get_user_admin(user_id: int, db=Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    return u

@app.put("/users/{user_id}", response_model=UserOut, dependencies=[Depends(require_admin)])
def update_user_admin(user_id: int, payload: UserUpdate, db=Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")

    if payload.email and payload.email != u.email:
        # chequear unicidad
        if db.query(User).filter(User.email == payload.email).first():
            raise HTTPException(400, "Email already registered")
        u.email = payload.email

    if payload.role:
        u.role = payload.role

    if payload.password:
        u.password_hash = get_password_hash(payload.password)

    db.add(u)
    db.commit()
    db.refresh(u)
    return u

@app.delete("/users/{user_id}", dependencies=[Depends(require_admin)])
def delete_user_admin(user_id: int, db=Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    db.delete(u)
    db.commit()
    return {"detail": "deleted"}

@app.get("/orders/search", response_model=OrderOut)
def search_order(code: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.order_code == code).first()
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    
    # Construimos la respuesta plana para facilitar a Flutter
    response_items = []
    for item in order.items:
        response_items.append({
            "product_id": item.product.id,
            "product_code": item.product.id_code,
            "description": item.product.description,
            "quantity": item.quantity
        })
        
    return {
        "id": order.id,
        "order_code": order.order_code,
        "type": order.type,
        "customer_name": order.customer_name,
        "status": order.status,
        "items": response_items
    }

# 2. FINALIZAR ORDEN Y SUBIR EVIDENCIA
@app.post("/orders/{order_id}/complete")
def complete_order(
    order_id: int, 
    file: UploadFile = File(...), 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # Requiere auth
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    
    if order.status == OrderStatus.COMPLETED:
         raise HTTPException(status_code=400, detail="La orden ya fue completada")

    # 1. Guardar la Foto
    file_location = f"uploads/evidence/{order.order_code}_{file.filename}"
    with open(file_location, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)
    
    # 2. Generar Movimientos de Inventario Automáticos
    # Si es VENTA -> Restamos stock (OUT)
    # Si es COMPRA -> Sumamos stock (IN)
    mov_type = "OUT" if order.type == "SALE" else "IN"
    
    for item in order.items:
        new_movement = Movement(
            product_id=item.product_id,
            movement_type=mov_type,
            quantity=item.quantity,
            user_id=current_user.id, # Usuario que escaneó
            notes=f"Orden completada: {order.order_code}",
            moved_at=datetime.utcnow()
        )
        db.add(new_movement)
        
        # Actualizar stock maestro del producto
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if mov_type == "IN":
            product.stock += item.quantity
        else:
            product.stock -= item.quantity

    # 3. Actualizar Estado de la Orden
    order.status = OrderStatus.COMPLETED
    order.evidence_photo_url = file_location
    
    db.commit()
    return {"message": "Orden completada y stock actualizado"}

# 3. CREAR ORDEN (Seed/Prueba para que tengas datos que escanear)
class OrderCreateItem(BaseModel):
    product_id: int
    quantity: int

class OrderCreate(BaseModel):
    order_code: str
    customer_name: str
    type: str # SALE o PURCHASE
    items: List[OrderCreateItem]

@app.post("/orders")
def create_order(order_data: OrderCreate, db: Session = Depends(get_db)):
    # Validar que no exista
    if db.query(Order).filter(Order.order_code == order_data.order_code).first():
        raise HTTPException(status_code=400, detail="Código de orden ya existe")

    new_order = Order(
        order_code=order_data.order_code,
        customer_name=order_data.customer_name,
        type=order_data.type,
        status=OrderStatus.PENDING
    )
    db.add(new_order)
    db.commit() # Commit para obtener ID
    db.refresh(new_order)

    for item in order_data.items:
        new_item = OrderItem(
            order_id=new_order.id,
            product_id=item.product_id,
            quantity=item.quantity
        )
        db.add(new_item)
    
    db.commit()
    return {"message": "Orden creada exitosamente"}

@app.post("/warehouses")
def create_warehouse(wh: WarehouseCreate, db: Session = Depends(get_db)):
    new_wh = Warehouse(name=wh.name, location=wh.location)
    db.add(new_wh)
    db.commit()
    return {"message": "Almacén creado"}

@app.get("/warehouses")
def get_warehouses(db: Session = Depends(get_db)):
    return db.query(Warehouse).all()

@app.post("/movements/transfer")
def create_transfer(
    transfer: TransferRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Validar Stock (Simplificado: Asumimos stock global por ahora, 
    # en un sistema real validarías stock por almacén origen)
    product = db.query(Product).filter(Product.id == transfer.product_id).first()
    if product.stock < transfer.quantity:
        raise HTTPException(status_code=400, detail="Stock global insuficiente")

    # 2. Registrar Salida del Origen
    mov_out = Movement(
        product_id=transfer.product_id,
        movement_type="TRANSFER_OUT",
        quantity=transfer.quantity,
        user_id=current_user.id,
        notes=f"Transferencia hacia Alm. {transfer.to_warehouse_id} | {transfer.notes or ''}",
        moved_at=datetime.utcnow()
    )
    
    # 3. Registrar Entrada en Destino
    mov_in = Movement(
        product_id=transfer.product_id,
        movement_type="TRANSFER_IN",
        quantity=transfer.quantity,
        user_id=current_user.id,
        notes=f"Recepción desde Alm. {transfer.from_warehouse_id} | {transfer.notes or ''}",
        moved_at=datetime.utcnow()
    )

    db.add(mov_out)
    db.add(mov_in)
    
    # El stock global no cambia (solo se mueve), pero registramos el movimiento
    db.commit()
    return {"message": "Transferencia exitosa"}