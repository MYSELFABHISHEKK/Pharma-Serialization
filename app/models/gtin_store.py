from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

class GTINStoreBase(BaseModel):
    manufacturer: str = Field(..., min_length=1)
    plant: str = Field(..., min_length=1)
    packaging_level: str = Field(..., min_length=1)
    product_id: str = Field(..., min_length=1)
    product_code: str = Field(..., min_length=1)
    packing_size: str = Field(..., min_length=1)
    gtin: str = Field(..., min_length=14, max_length=14, pattern=r"^\d{14}$")
    enable_gtin: bool = Field(default=True)
    case_quantity: Optional[int] = Field(default=None, ge=0)
    limit: int = Field(..., ge=1)
    code_length: int = Field(..., ge=1)
    serial_no_type: Optional[str] = Field(default="SGTIN")
    packaging_category: Optional[str] = Field(default="Primary")

class GTINStoreCreate(GTINStoreBase):
    pass

class GTINStoreResponse(GTINStoreBase):
    id: int
    created_at: str

    model_config = ConfigDict(from_attributes=True)
