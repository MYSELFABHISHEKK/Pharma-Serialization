from pydantic import BaseModel, Field


class SGTINGenerateRequest(BaseModel):
    gtin: str = Field(..., min_length=14, max_length=14, pattern=r"^\d{14}$")
    quantity: int = Field(..., ge=1, le=1000000)
    start_sequence: int = Field(default=1, ge=1)
    length: int = Field(default=20, ge=5, le=20)
    alphabet: str = Field(default="23456789ABCDEFGHJKMNPQRSTVWXYZ")
    require_alpha: bool = Field(default=True)
    require_numeric: bool = Field(default=True)
