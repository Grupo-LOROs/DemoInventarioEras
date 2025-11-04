# Seed script: loads product types, products and opening balance movements from the cleaned CSV.
import os, sys, csv
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import Base, ProductType, Product, InventoryMovement

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./inventory.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine)

def main(path):
    session = SessionLocal()
    Base.metadata.create_all(bind=engine)

    # First pass: collect types
    types_seen = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tname = row.get("tipo") or ""
            if tname and tname not in types_seen:
                pt = session.query(ProductType).filter_by(name=tname).first()
                if not pt:
                    pt = ProductType(name=tname)
                    session.add(pt); session.commit(); session.refresh(pt)
                types_seen[tname] = pt.id

    # Second pass: products + opening balances
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = str(row.get("codigo","")).strip()
            desc = str(row.get("descripcion","")).strip()
            if not code or not desc: continue
            unit_cost = row.get("costo_unitario")
            unit_cost = float(unit_cost) if unit_cost not in (None, "", "nan") else None
            tname = row.get("tipo") or ""
            type_id = types_seen.get(tname)
            min_stock = None
            max_stock = None
            prod = session.query(Product).filter_by(id_code=code).first()
            if not prod:
                prod = Product(id_code=code, description=desc, unit_cost=unit_cost, product_type_id=type_id,
                               min_stock=min_stock, max_stock=max_stock)
                session.add(prod); session.commit(); session.refresh(prod)
            try:
                qty = int(float(row.get("existencias") or 0))
            except:
                qty = 0
            if qty > 0:
                session.add(InventoryMovement(product_id=prod.id, movement_type="IN", quantity=qty,
                                              unit_cost=unit_cost, note="Saldo inicial importado", moved_at=datetime.utcnow(),
                                              movement_reason="opening_balance"))
        session.commit()
    print("Seed completed.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python seed.py <inventario_limpio.csv>")
        sys.exit(1)
    main(sys.argv[1])
