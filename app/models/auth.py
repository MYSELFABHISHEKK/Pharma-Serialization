from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional

class SignUpRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=100)
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)
    role: Optional[str] = Field(default="Packaging Line Supervisor")
    plant: Optional[str] = Field(default="TESTPLANT")

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
    plant: Optional[str] = None
    is_active: bool
    created_at: str
    last_login: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class AuthResponse(BaseModel):
    user: UserResponse
    token: str
    access_token: Optional[str] = None
    token_type: Optional[str] = "Bearer"
    expires_at: str

    @model_validator(mode='before')
    @classmethod
    def populate_access_token(cls, data):
        if isinstance(data, dict):
            if not data.get("access_token") and data.get("token"):
                data["access_token"] = data["token"]
            elif not data.get("token") and data.get("access_token"):
                data["token"] = data["access_token"]
        return data

class DemoUser(BaseModel):
    username: str
    full_name: Optional[str] = ""
    role: str
    plant: str
    description: str

