#!/usr/bin/env python3

import argparse

from main import SessionLocal, User, get_password_hash


def ensure_user(email: str, password: str, role: str = "admin") -> bool:
    """Create the user if it does not exist. Returns True when created."""
    with SessionLocal() as db:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"User already exists: {email}")
            return False

        db.add(User(email=email, password_hash=get_password_hash(password), role=role))
        db.commit()
        print(f"Created {role}: {email}")
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Ensure an admin user exists in the database.")
    parser.add_argument("--email", default="admin@company.com", help="Email for the admin user.")
    parser.add_argument("--password", default="ChangeMe123!", help="Initial password for the admin user.")
    parser.add_argument("--role", default="admin", help="Role assigned to the user (default: admin).")
    args = parser.parse_args()

    ensure_user(email=args.email, password=args.password, role=args.role)


if __name__ == "__main__":
    main()
