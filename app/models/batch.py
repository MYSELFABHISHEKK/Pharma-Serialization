from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List

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
    line_id: Optional[str] = None
    secondary_ratio: Optional[int] = Field(default=1, ge=1)
    tertiary_ratio: Optional[int] = Field(default=1, ge=1)
    io_channel: Optional[str] = Field(default="DIRECT_API")

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

    # L3 / L2 operational workflow fields
    line_id: Optional[str] = None
    secondary_ratio: int = 1
    tertiary_ratio: int = 1
    primary_quantity: int = 0
    secondary_quantity: int = 0
    tertiary_quantity: int = 0
    reconciled_good_count: int = 0
    reconciled_rejected_count: int = 0
    reconciled_unused_count: int = 0
    yield_percentage: float = 0.0
    is_locked: bool = False
    io_channel: str = "DIRECT_API"

    model_config = ConfigDict(from_attributes=True)

class BatchReconcileRequest(BaseModel):
    good_serials: Optional[List[str]] = None
    rejected_serials: Optional[List[str]] = None
    raw_feedback_content: Optional[str] = None
    auto_simulate: bool = False
    simulated_yield_pct: Optional[float] = Field(default=98.0, ge=0.0, le=100.0)

class BatchSummaryResponse(BaseModel):
    batch_id: str
    product_id: str
    batch_lot: str
    status: str
    line_id: Optional[str] = None
    io_channel: str = "DIRECT_API"
    is_locked: bool = False
    total_requested: int
    total_generated: int
    primary_quantity: int
    secondary_quantity: int
    tertiary_quantity: int
    secondary_ratio: int
    tertiary_ratio: int
    reconciled_good_count: int
    reconciled_rejected_count: int
    reconciled_unused_count: int
    yield_percentage: float
    created_at: str
