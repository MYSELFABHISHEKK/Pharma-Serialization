from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional

class StatusHistory(BaseModel):
    status: str
    updated_by: str
    timestamp: str
    notes: Optional[str] = None

class SerialResponse(BaseModel):
    serial_number: str
    sequence_number: int
    product_id: str
    batch_id: str
    batch_lot: str
    expiry_date: str
    status: str
    created_at: str
    history: List[StatusHistory] = []

    model_config = ConfigDict(from_attributes=True)

class SerialStatusUpdate(BaseModel):
    status: str = Field(..., description="Target status, e.g. ALLOCATED, SHIPPED, SOLD, DECOMMISSIONED")
    updated_by: str = Field(default="system")
    notes: Optional[str] = None
