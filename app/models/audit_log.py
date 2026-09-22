from pydantic import BaseModel, ConfigDict
from typing import Optional

class AuditLogResponse(BaseModel):
    id: int
    event_type: str
    table_name: str
    record_id: str
    previous_value: Optional[str] = None
    updated_value: Optional[str] = None
    performed_by: str
    timestamp: str

    model_config = ConfigDict(from_attributes=True)
