from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

class BatchCreate(BaseModel):
    product_id: str = Field(...)
    quantity: int = Field(..., ge=1, le=1000000, description="Amount of serials to generate")
    batch_lot: str = Field(..., min_length=2, max_length=50, description="Manufacturer Batch/Lot Number")
    expiry_date: str = Field(..., pattern=r"^\d{6}$", description="Expiry date in YYMMDD format")
    idempotency_key: str = Field(..., min_length=1)

class BatchMasterCreate(BaseModel):
    manufacturer: str = Field(..., min_length=1)
    plant: str = Field(..., min_length=1)
    packaging_level: str = Field(..., min_length=1)
    product_id: str = Field(..., min_length=1)
    packaging_size: str = Field(..., min_length=1)
    work_order_no: str = Field(..., min_length=1)
    batch_lot: str = Field(..., min_length=1, max_length=50) # Batch Number
    gtin: str = Field(..., min_length=14, max_length=14, pattern=r"^\d{14}$")
    mfg_date: str = Field(..., min_length=6, max_length=10)
    expiry_date: str = Field(..., pattern=r"^\d{6}$")
    quantity: int = Field(..., ge=1, le=1000000)
    is_enabled: bool = Field(default=True)
    package_aggregation: bool = Field(default=False)
    parent_code_required: bool = Field(default=False)
    aggregated_batch: bool = Field(default=False)
    idempotency_key: Optional[str] = None

class BatchResponse(BaseModel):
    batch_id: str
    product_id: str
    requested_quantity: int
    generated_quantity: int
    start_sequence: int
    end_sequence: int
    batch_lot: str
    expiry_date: str
    status: str
    created_at: str
    
    # Additional Batch Master columns
    manufacturer: Optional[str] = None
    plant: Optional[str] = None
    packaging_level: Optional[str] = None
    packaging_size: Optional[str] = None
    work_order_no: Optional[str] = None
    mfg_date: Optional[str] = None
    is_enabled: bool = True
    package_aggregation: bool = False
    parent_code_required: bool = False
    aggregated_batch: bool = False

    model_config = ConfigDict(from_attributes=True)
