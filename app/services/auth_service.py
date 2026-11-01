import os
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
    _argon2_hasher: Optional[PasswordHasher] = PasswordHasher()
except ImportError:
    _argon2_hasher = None

from app.models.db_models import User, UserSession, Role
from app.models.auth import SignUpRequest, LoginRequest
from app.repositories.audit_log_repository import AuditLogRepository
from app.services.rbac_service import RBACService
from app.core.security import validate_password_complexity


class AuthService:
    ITERATIONS = 100_000
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 15
    SESSION_INACTIVITY_HOURS = 2

    @classmethod
    def hash_password(cls, password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        if not salt:
            salt = secrets.token_hex(16)
        
        if _argon2_hasher is not None:
            pwd_hash = _argon2_hasher.hash(password)
            return pwd_hash, salt
        else:
            # Fallback to PBKDF2 if argon2-cffi is unavailable
            pwd_hash = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt.encode("utf-8"),
                cls.ITERATIONS
            ).hex()
            return pwd_hash, salt

    @classmethod
    def verify_password(cls, password: str, password_hash: str, salt: str) -> bool:
        if password_hash.startswith("$argon2"):
            if _argon2_hasher is None:
                return False
            try:
                return _argon2_hasher.verify(password_hash, password)
            except Exception:
                return False
        else:
            # Legacy PBKDF2 check
            check_hash = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt.encode("utf-8"),
                cls.ITERATIONS
            ).hex()
            return secrets.compare_digest(check_hash, password_hash)

    @classmethod
    def create_session(cls, db: Session, user: User, remember_me: bool = False) -> Tuple[str, str]:
        token = secrets.token_urlsafe(48)
        now = datetime.now(timezone.utc)
        duration_days = 30 if remember_me else 7
        expires_at = (now + timedelta(days=duration_days)).isoformat()
        
        session = UserSession(
            token=token,
            user_id=user.id,
            created_at=now.isoformat(),
            last_activity_at=now.isoformat(),
            expires_at=expires_at,
            is_revoked=False
        )
        db.add(session)
        db.commit()
        return token, expires_at

    @classmethod
    def register_user(
        cls, 
        db: Session, 
        req: SignUpRequest, 
        created_by: Optional[str] = None,
        role_id: Optional[int] = None,
        require_password_change: bool = False
    ) -> Tuple[User, str, str]:
        clean_username = req.username.strip()
        clean_email = req.email.strip().lower()

        # Database uniqueness check
        existing_user = db.query(User).filter(
            (User.username.ilike(clean_username)) | (User.email.ilike(clean_email))
        ).first()
        if existing_user:
            if existing_user.username.lower() == clean_username.lower():
                raise ValueError(f"User ID '{req.username}' is already registered.")
            raise ValueError(f"Email '{req.email}' is already registered.")

        # Determine role_id if not explicitly provided
        target_role_id = role_id
        assigned_role_name = req.role or "Serialization Operator"
        if not target_role_id:
            matched_role = db.query(Role).filter(Role.role_name == assigned_role_name).first()
            if matched_role:
                target_role_id = matched_role.id
            else:
                # Default to first role or System Administrator if initial
                first_role = db.query(Role).first()
                if first_role:
                    target_role_id = first_role.id

        # Enforce 21 CFR Part 11 / GAMP 5 password complexity
        is_valid_pwd, pwd_err = validate_password_complexity(req.password)
        if not is_valid_pwd:
            raise ValueError(pwd_err)

        pwd_hash, salt = cls.hash_password(req.password)
        now_str = datetime.now(timezone.utc).isoformat()

        user = User(
            username=clean_username,
            email=clean_email,
            full_name=req.full_name.strip(),
            role=assigned_role_name,
            role_id=target_role_id,
            plant=req.plant or "TESTPLANT",
            password_hash=pwd_hash,
            salt=salt,
            is_active=True,
            require_password_change=require_password_change,
            failed_login_attempts=0,
            locked_until=None,
            created_at=now_str,
            last_login=now_str
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Audit log creation
        actor = created_by or user.username
        event_name = "USER_PROVISIONED" if created_by else "USER_SIGNUP"
        AuditLogRepository.log(
            db=db,
            event_type=event_name,
            table_name="users",
            record_id=str(user.id),
            previous_value=None,
            updated_value={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "role_id": user.role_id,
                "plant": user.plant,
                "require_password_change": require_password_change,
                "provisioned_by": actor
            },
            performed_by=actor
        )
        db.commit()

        token, expires_at = cls.create_session(db, user, remember_me=False)
        return user, token, expires_at

    @classmethod
    def list_users(cls, db: Session) -> List[User]:
        return db.query(User).order_by(User.id.asc()).all()

    @classmethod
    def authenticate_user(cls, db: Session, req: LoginRequest) -> Tuple[User, str, str]:
        identifier = (req.username_or_email or req.username or "").strip()
        if not identifier:
            raise ValueError("Please provide a User ID or corporate email.")

        user = db.query(User).filter(
            (User.username.ilike(identifier)) | (User.email.ilike(identifier))
        ).first()

        now = datetime.now(timezone.utc)
        now_str = now.isoformat()

        if not user:
            # Generic error to prevent user enumeration
            raise ValueError("Invalid User ID or password.")

        # Check account lockout
        if user.locked_until:
            is_locked = False
            diff_mins = 0
            try:
                locked_dt = datetime.fromisoformat(user.locked_until)
                if now < locked_dt:
                    is_locked = True
                    diff_mins = int((locked_dt - now).total_seconds() / 60) + 1
                else:
                    user.locked_until = None
                    user.failed_login_attempts = 0
                    db.commit()
            except (ValueError, TypeError):
                user.locked_until = None
                user.failed_login_attempts = 0
                db.commit()

            if is_locked:
                raise ValueError(f"Account is temporarily locked due to repeated failed login attempts. Retry in {diff_mins} minute(s) or contact administrator.")

        if not user.is_active:
            raise ValueError("This user account has been deactivated. Please contact your System Administrator.")

        if not cls.verify_password(req.password, user.password_hash, user.salt):
            # Dual-bootstrap support for default admin across local and deployed (Render) environments:
            # Accepts both Bharattraq@321 and Admin@1234 for initial administrative access
            is_admin_dual_valid = (
                user.username.lower() == "admin" and
                (
                    (req.password == "Bharattraq@321" and cls.verify_password("Admin@1234", user.password_hash, user.salt)) or
                    (req.password == "Admin@1234" and cls.verify_password("Bharattraq@321", user.password_hash, user.salt))
                )
            )
            if is_admin_dual_valid:
                # Synchronize hash to the password the user entered so subsequent logins are instant
                user.password_hash, user.salt = cls.hash_password(req.password)
                user.failed_login_attempts = 0
                user.locked_until = None
                db.commit()
            else:
                user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
                if user.failed_login_attempts >= cls.MAX_FAILED_ATTEMPTS:
                    user.locked_until = (now + timedelta(minutes=cls.LOCKOUT_DURATION_MINUTES)).isoformat()
                db.commit()
                raise ValueError("Invalid User ID or password.")

        # If password was legacy PBKDF2 and argon2 is available, transparently re-hash to Argon2id
        if not user.password_hash.startswith("$argon2") and _argon2_hasher is not None:
            user.password_hash, user.salt = cls.hash_password(req.password)

        # Successful authentication: reset failed attempts & update last login
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login = now_str
        db.commit()

        # Audit log login event
        AuditLogRepository.log(
            db=db,
            event_type="USER_LOGIN",
            table_name="users",
            record_id=str(user.id),
            previous_value=None,
            updated_value={"id": user.id, "username": user.username, "last_login": now_str},
            performed_by=user.username
        )
        db.commit()

        token, expires_at = cls.create_session(db, user, remember_me=req.remember_me or False)
        return user, token, expires_at

    @classmethod
    def validate_token(cls, db: Session, token: str) -> Optional[User]:
        if not token:
            return None
        session = db.query(UserSession).filter(UserSession.token == token).first()
        if not session or session.is_revoked:
            return None

        now = datetime.now(timezone.utc)

        # Check absolute expiration
        try:
            expires_at_dt = datetime.fromisoformat(session.expires_at)
            if now > expires_at_dt:
                session.is_revoked = True
                db.commit()
                return None
        except Exception:
            return None

        # Check inactivity timeout (2 hours)
        if session.last_activity_at:
            try:
                last_act = datetime.fromisoformat(session.last_activity_at)
                if now - last_act > timedelta(hours=cls.SESSION_INACTIVITY_HOURS):
                    session.is_revoked = True
                    db.commit()
                    return None
            except Exception:
                pass

        # Update last activity timestamp
        session.last_activity_at = now.isoformat()
        db.commit()

        user = db.query(User).filter(User.id == session.user_id).first()
        if not user or not user.is_active:
            return None
        return user

    @classmethod
    def revoke_all_user_sessions(cls, db: Session, user_id: int):
        db.query(UserSession).filter(UserSession.user_id == user_id).update({"is_revoked": True})
        db.commit()

    @classmethod
    def terminate_session(cls, db: Session, token: str) -> bool:
        session = db.query(UserSession).filter(UserSession.token == token).first()
        if not session:
            return False

        user = db.query(User).filter(User.id == session.user_id).first()
        user_name = user.username if user else "unknown"

        session.is_revoked = True
        db.delete(session)
        db.commit()

        AuditLogRepository.log(
            db=db,
            event_type="USER_LOGOUT",
            table_name="user_sessions",
            record_id=token[:8] + "...",
            previous_value={"user_id": session.user_id},
            updated_value=None,
            performed_by=user_name
        )
        db.commit()
        return True

    @classmethod
    def change_user_password(
        cls,
        db: Session,
        user: User,
        old_password: str,
        new_password: str
    ):
        if not cls.verify_password(old_password, user.password_hash, user.salt):
            raise ValueError("Current password is incorrect.")
        
        is_valid_pwd, pwd_err = validate_password_complexity(new_password)
        if not is_valid_pwd:
            raise ValueError(pwd_err)
        
        pwd_hash, salt = cls.hash_password(new_password)
        user.password_hash = pwd_hash
        user.salt = salt
        user.require_password_change = False
        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()

        AuditLogRepository.log(
            db=db,
            event_type="PASSWORD_CHANGE",
            table_name="users",
            record_id=str(user.id),
            previous_value=None,
            updated_value={"require_password_change": False},
            performed_by=user.username
        )
        db.commit()

    @classmethod
    def reset_user_password(
        cls, 
        db: Session, 
        user: User, 
        new_password: str, 
        require_change: bool = True,
        actor_name: str = "system"
    ):
        is_valid_pwd, pwd_err = validate_password_complexity(new_password)
        if not is_valid_pwd:
            raise ValueError(pwd_err)

        pwd_hash, salt = cls.hash_password(new_password)
        user.password_hash = pwd_hash
        user.salt = salt
        user.require_password_change = require_change
        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()

        # Revoke existing sessions to enforce security
        cls.revoke_all_user_sessions(db, user.id)

        AuditLogRepository.log(
            db=db,
            event_type="PASSWORD_RESET",
            table_name="users",
            record_id=str(user.id),
            previous_value=None,
            updated_value={"require_password_change": require_change},
            performed_by=actor_name
        )
        db.commit()

    @classmethod
    def seed_default_users(cls, db: Session):
        now_str = datetime.now(timezone.utc).isoformat()

        # Ensure default roles exist first
        RBACService.seed_default_roles(db)

        admin_role = db.query(Role).filter(Role.role_name == "System Administrator").first()
        op_role = db.query(Role).filter(Role.role_name == "Serialization Operator").first()

        admin_role_id = admin_role.id if admin_role else None
        op_role_id = op_role.id if op_role else None

        # 1. Admin
        admin = db.query(User).filter(User.username == "admin").first()
        admin_default_pwd = os.getenv("ADMIN_PASSWORD", "Bharattraq@321")
        if not admin:
            pwd_hash, salt = cls.hash_password(admin_default_pwd)
            admin = User(
                username="admin",
                email="admin@pharma-portal.local",
                full_name="Dr. Alexander Wright",
                role="System Administrator (Qualified Person)",
                role_id=admin_role_id,
                plant="TESTPLANT",
                password_hash=pwd_hash,
                salt=salt,
                is_active=True,
                require_password_change=False,
                created_at=now_str,
                last_login=now_str
            )
            db.add(admin)
        else:
            if not admin.role_id and admin_role_id:
                admin.role_id = admin_role_id
            if "Qualified Person" not in admin.role:
                admin.role = "System Administrator (Qualified Person)"
            # If admin still has old default seed Admin@1234, upgrade it to Bharattraq@321
            if cls.verify_password("Admin@1234", admin.password_hash, admin.salt):
                admin.password_hash, admin.salt = cls.hash_password(admin_default_pwd)
            # Reset any lockout from failed attempts so the user can immediately log in on Render
            admin.failed_login_attempts = 0
            admin.locked_until = None
            admin.is_active = True

        # 2. Packaging Operator
        operator = db.query(User).filter(User.username == "operator").first()
        if not operator:
            pwd_hash, salt = cls.hash_password("Operator@1234")
            operator = User(
                username="operator",
                email="operator@pharma-portal.local",
                full_name="Marcus Vance",
                role="Serialization Operator",
                role_id=op_role_id,
                plant="TESTPLANT",
                password_hash=pwd_hash,
                salt=salt,
                is_active=True,
                require_password_change=False,
                created_at=now_str,
                last_login=now_str
            )
            db.add(operator)
        else:
            if not operator.role_id and op_role_id:
                operator.role_id = op_role_id
                operator.role = "Serialization Operator"

        db.commit()
