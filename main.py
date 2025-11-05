import os
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
import io, csv as _csv

from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import (create_engine, Column, Integer, String, Float, Text, DateTime, ForeignKey, CheckConstraint,
                        func, select, and_, or_, case)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

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
        "sales": {"OUT"},
        "purchasing": {"IN"},
        "user": set(),  # default read-only
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
