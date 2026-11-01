from typing import Optional, Callable
from fastapi import Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db_models import User
from app.services.auth_service import AuthService
from app.services.rbac_service import RBACService


def extract_auth_token(
    authorization: Optional[str] = Header(None),
    x_auth_token: Optional[str] = Header(None)
) -> Optional[str]:
    if authorization and authorization.startswith("Bearer "):
        return authorization.split("Bearer ")[1].strip()
    if x_auth_token:
        return x_auth_token.strip()
    return None


def get_current_user(
    authorization: Optional[str] = Header(None),
    x_auth_token: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> User:
    token = extract_auth_token(authorization, x_auth_token)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Electronic signature/identity required under 21 CFR Part 11.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = AuthService.validate_token(db, token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or been revoked. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This user account has been deactivated. Please contact your administrator.",
        )

    return user


def require_permission(module_key: str, action_key: str) -> Callable:
    def dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> User:
        if not RBACService.has_permission(db, current_user, module_key, action_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access Denied: Account '{current_user.username}' does not have '{action_key}' permission on module '{module_key}'."
            )
        return current_user
    return dependency
