import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from app.models.db_models import User, UserSession
from app.models.auth import SignUpRequest, LoginRequest
from app.repositories.audit_log_repository import AuditLogRepository

class AuthService:
    ITERATIONS = 100_000

    @classmethod
    def hash_password(cls, password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        if not salt:
            salt = secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            cls.ITERATIONS
        ).hex()
        return pwd_hash, salt

    @classmethod
    def verify_password(cls, password: str, password_hash: str, salt: str) -> bool:
        check_hash, _ = cls.hash_password(password, salt)
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
            expires_at=expires_at
        )
        db.add(session)
        db.commit()
        return token, expires_at

    @classmethod
    def register_user(cls, db: Session, req: SignUpRequest) -> Tuple[User, str, str]:
        # Check uniqueness of username and email
        clean_username = req.username.strip().lower()
        clean_email = req.email.strip().lower()

        existing_user = db.query(User).filter(
            (User.username.ilike(clean_username)) | (User.email.ilike(clean_email))
        ).first()
        if existing_user:
            if existing_user.username.lower() == clean_username:
                raise ValueError(f"Username '{req.username}' is already registered.")
            raise ValueError(f"Email '{req.email}' is already registered.")

        pwd_hash, salt = cls.hash_password(req.password)
        now_str = datetime.now(timezone.utc).isoformat()

        user = User(
            username=req.username.strip(),
            email=clean_email,
            full_name=req.full_name.strip(),
            role=req.role or "Packaging Line Supervisor",
            plant=req.plant or "TESTPLANT",
            password_hash=pwd_hash,
            salt=salt,
            is_active=True,
            created_at=now_str,
            last_login=now_str
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Audit log creation
        AuditLogRepository.log(
            db=db,
            event_type="USER_SIGNUP",
            table_name="users",
            record_id=str(user.id),
            previous_value=None,
            updated_value={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "plant": user.plant
            },
            performed_by=user.username
        )
        db.commit()

        token, expires_at = cls.create_session(db, user, remember_me=False)
        return user, token, expires_at

    @classmethod
    def authenticate_user(cls, db: Session, req: LoginRequest) -> Tuple[User, str, str]:
        identifier = req.username_or_email.strip().lower()
        user = db.query(User).filter(
            (User.username.ilike(identifier)) | (User.email.ilike(identifier))
        ).first()

        if not user or not user.is_active:
            raise ValueError("Invalid username/email or password.")

        if not cls.verify_password(req.password, user.password_hash, user.salt):
            raise ValueError("Invalid username/email or password.")

        # Update last login
        now_str = datetime.now(timezone.utc).isoformat()
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
        if not session:
            return None

        # Check expiration
        try:
            expires_at_dt = datetime.fromisoformat(session.expires_at)
            if datetime.now(timezone.utc) > expires_at_dt:
                db.delete(session)
                db.commit()
                return None
        except Exception:
            pass

        user = db.query(User).filter(User.id == session.user_id).first()
        if not user or not user.is_active:
            return None
        return user

    @classmethod
    def terminate_session(cls, db: Session, token: str) -> bool:
        session = db.query(UserSession).filter(UserSession.token == token).first()
        if not session:
            return False

        user = db.query(User).filter(User.id == session.user_id).first()
        user_name = user.username if user else "unknown"

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
    def seed_default_users(cls, db: Session):
        now_str = datetime.now(timezone.utc).isoformat()

        # 1. Admin
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            pwd_hash, salt = cls.hash_password("Admin@1234")
            admin = User(
                username="admin",
                email="admin@pharma-portal.local",
                full_name="Dr. Alexander Wright",
                role="QA & Compliance Lead (Qualified Person)",
                plant="TESTPLANT",
                password_hash=pwd_hash,
                salt=salt,
                is_active=True,
                created_at=now_str,
                last_login=now_str
            )
            db.add(admin)

        # 2. Packaging Operator
        operator = db.query(User).filter(User.username == "operator").first()
        if not operator:
            pwd_hash, salt = cls.hash_password("Operator@1234")
            operator = User(
                username="operator",
                email="operator@pharma-portal.local",
                full_name="Marcus Vance",
                role="Packaging Line Supervisor",
                plant="TESTPLANT",
                password_hash=pwd_hash,
                salt=salt,
                is_active=True,
                created_at=now_str,
                last_login=now_str
            )
            db.add(operator)

        db.commit()
