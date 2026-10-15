from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List

class CodePoolItem(BaseModel):
    gtin: str = Field(..., min_length=14, max_length=14, pattern=r"^\d{14}$")
    serial_number: str = Field(..., min_length=1, max_length=30)
    packaging_tier: str = Field(default="Primary")

class CodePoolImportRequest(BaseModel):
    gtin: str = Field(..., min_length=14, max_length=14, pattern=r"^\d{14}$")
    packaging_tier: str = Field(default="Primary")
    serials: List[str] = Field(..., min_length=1)

class CodePoolResponse(BaseModel):
    id: int
    gtin: str
    serial_number: str
    packaging_tier: str
    status: str
    batch_id: Optional[str] = None
    imported_at: str

    model_config = ConfigDict(from_attributes=True)

class CodePoolStatsResponse(BaseModel):
    total_codes: int
    available_codes: int
    reserved_codes: int
    committed_codes: int
    rejected_codes: int
    by_tier: dict
