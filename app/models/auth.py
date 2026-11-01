from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, Dict, List

class SignUpRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50) # Administrator-assigned User ID
    email: str = Field(..., min_length=5, max_length=100)
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)
    role: Optional[str] = Field(default="Serialization Operator")
    role_id: Optional[int] = None
    plant: Optional[str] = Field(default="TESTPLANT")
    require_password_change: Optional[bool] = False

class LoginRequest(BaseModel):
    username_or_email: Optional[str] = None
    username: Optional[str] = None
    password: str = Field(..., min_length=1)
    remember_me: Optional[bool] = False

    @model_validator(mode='before')
    @classmethod
    def set_identifier(cls, data):
        if isinstance(data, dict):
            if not data.get("username_or_email") and data.get("username"):
                data["username_or_email"] = data["username"]
        return data

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    role: str
    role_id: Optional[int] = None
    plant: Optional[str] = None
    is_active: bool
    require_password_change: bool = False
    created_at: str
    last_login: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class AuthResponse(BaseModel):
    user: UserResponse
    token: str
    access_token: Optional[str] = None
    token_type: Optional[str] = "Bearer"
    expires_at: str
    require_password_change: bool = False
    permissions: Optional[Dict[str, List[str]]] = None

    @model_validator(mode='before')
    @classmethod
    def populate_access_token(cls, data):
        if isinstance(data, dict):
            if not data.get("access_token") and data.get("token"):
                data["access_token"] = data["token"]
            elif not data.get("token") and data.get("access_token"):
                data["token"] = data["access_token"]
            if data.get("user") and isinstance(data["user"], dict):
                data["require_password_change"] = data["user"].get("require_password_change", False)
        return data

class RoleResponse(BaseModel):
    id: int
    role_name: str
    description: Optional[str] = None
    is_system_role: bool = False
    created_at: str
    permissions: Dict[str, List[str]] = {}

class RoleCreateRequest(BaseModel):
    role_name: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = Field(default="")
    permissions: Dict[str, List[str]] = {}

class RoleUpdateRequest(BaseModel):
    description: Optional[str] = None
    permissions: Optional[Dict[str, List[str]]] = None

class UserStatusUpdateRequest(BaseModel):
    is_active: bool

class UserPasswordResetRequest(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=100)
    require_password_change: Optional[bool] = True

class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=100)

class UserPermissionOverrideRequest(BaseModel):
    module_key: str
    action_key: str
    is_allowed: bool

class DemoUser(BaseModel):
    username: str
    full_name: Optional[str] = ""
    role: str
    plant: str
    description: str
