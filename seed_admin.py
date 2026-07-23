"""
Run this once to create your admin login.
Usage:  python seed_admin.py
"""

import getpass
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from prisma import Prisma

load_dotenv()


def main():
    email = input("Admin email: ").strip().lower()
    password = getpass.getpass("Admin password: ")

    db = Prisma()
    db.connect()

    existing = db.admin.find_unique(where={"email": email})
    if existing:
        print("An admin with that email already exists.")
    else:
        db.admin.create(
            data={"email": email, "passwordHash": generate_password_hash(password)}
        )
        print(f"Admin account created for {email}. You can now log in at /admin/login")

    db.disconnect()


if __name__ == "__main__":
    main()
