"""
BharatTraq (BT SN Portal) — Initial System Administrator Bootstrap CLI
Usage:
  Interactive:
    python scripts/bootstrap_admin.py

  Non-Interactive / Automated:
    python scripts/bootstrap_admin.py --user-id admin --full-name "Chief Quality Officer" --email "admin@plant.local" --password "SecureAdminPassword123"

  Environment Variable Driven:
    BT_ADMIN_USER_ID=admin BT_ADMIN_PASSWORD=SecurePassword python scripts/bootstrap_admin.py
"""

import os
import sys
import argparse
import getpass
from datetime import datetime, timezone

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal, Base, engine
from app.models.db_models import User, Role
from app.services.auth_service import AuthService
from app.services.rbac_service import RBACService
from app.repositories.audit_log_repository import AuditLogRepository


def bootstrap_admin():
    parser = argparse.ArgumentParser(description="Bootstrap the initial BharatTraq Administrator account.")
    parser.add_argument("--user-id", default=os.getenv("BT_ADMIN_USER_ID"), help="Unique Administrator User ID")
    parser.add_argument("--full-name", default=os.getenv("BT_ADMIN_FULL_NAME", "System Administrator"), help="Full Name")
    parser.add_argument("--email", default=os.getenv("BT_ADMIN_EMAIL"), help="Corporate Email")
    parser.add_argument("--password", default=os.getenv("BT_ADMIN_PASSWORD"), help="Admin Password")
    parser.add_argument("--force", action="store_true", help="Force creation even if another admin exists")
    args = parser.parse_args()

    print("====================================================================")
    print("BharatTraq Pharmaceutical Serialization System — Admin Bootstrap CLI")
    print("====================================================================")

    # Initialize tables if necessary
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 1. Seed Roles
        print("[1/4] Checking and seeding standard RBAC roles...")
        RBACService.seed_default_roles(db)
        admin_role = db.query(Role).filter(Role.role_name == "System Administrator").first()
        if not admin_role:
            print("ERROR: System Administrator role could not be verified.")
            sys.exit(1)

        # 2. Check for existing administrators
        existing_admin = db.query(User).filter(
            (User.role_id == admin_role.id) | (User.role == "System Administrator") | (User.username == "admin")
        ).first()

        if existing_admin and not args.force:
            print(f"\n[INFO] An administrator account already exists: User ID '{existing_admin.username}' ({existing_admin.full_name}).")
            print("To protect data integrity, repeated bootstrap is prevented.")
            print("If you need to create additional users, log into BharatTraq with this account and use User Management.")
            sys.exit(0)

        # 3. Prompt for credentials if not supplied via arguments or environment
        user_id = args.user_id
        while not user_id:
            user_id = input("Enter Administrator User ID [default: admin]: ").strip() or "admin"

        full_name = args.full_name
        while not full_name:
            full_name = input("Enter Administrator Full Name: ").strip()

        email = args.email
        while not email:
            email = input("Enter Administrator Corporate Email: ").strip()

        password = args.password
        if not password:
            while True:
                p1 = getpass.getpass("Enter Administrator Password (min 6 characters): ")
                if len(p1) < 6:
                    print("Error: Password must be at least 6 characters.")
                    continue
                p2 = getpass.getpass("Confirm Administrator Password: ")
                if p1 != p2:
                    print("Error: Passwords do not match. Try again.")
                    continue
                password = p1
                break

        # 4. Hash password with modern Argon2id and persist
        print("[2/4] Securing password with Argon2id cryptographic hashing...")
        pwd_hash, salt = AuthService.hash_password(password)
        now_str = datetime.now(timezone.utc).isoformat()

        # Check if user with this username exists
        target_user = db.query(User).filter(User.username == user_id).first()
        if target_user:
            print(f"[3/4] Updating existing user '{user_id}' with System Administrator privileges...")
            target_user.full_name = full_name
            target_user.email = email
            target_user.role = "System Administrator"
            target_user.role_id = admin_role.id
            target_user.password_hash = pwd_hash
            target_user.salt = salt
            target_user.is_active = True
            target_user.require_password_change = False
            target_user.failed_login_attempts = 0
            target_user.locked_until = None
        else:
            print(f"[3/4] Creating new System Administrator record '{user_id}'...")
            target_user = User(
                username=user_id,
                email=email,
                full_name=full_name,
                role="System Administrator",
                role_id=admin_role.id,
                plant="PLANT-MASTER",
                password_hash=pwd_hash,
                salt=salt,
                is_active=True,
                require_password_change=False,
                failed_login_attempts=0,
                locked_until=None,
                created_at=now_str,
                last_login=now_str
            )
            db.add(target_user)

        db.commit()
        db.refresh(target_user)

        # Audit event
        AuditLogRepository.log(
            db=db,
            event_type="BOOTSTRAP_ADMIN_CREATED",
            table_name="users",
            record_id=str(target_user.id),
            previous_value=None,
            updated_value={
                "id": target_user.id,
                "username": target_user.username,
                "role": target_user.role,
                "email": target_user.email
            },
            performed_by="cli_bootstrap"
        )
        db.commit()

        print("[4/4] Administrator setup completed successfully!")
        print("--------------------------------------------------------------------")
        print(f"User ID   : {target_user.username}")
        print(f"Full Name : {target_user.full_name}")
        print(f"Role      : {target_user.role}")
        print(f"Email     : {target_user.email}")
        print("Status    : Active (Argon2id protected)")
        print("--------------------------------------------------------------------")
        print("You can now start the application and log in locally with these credentials.")

    finally:
        db.close()


if __name__ == "__main__":
    bootstrap_admin()
