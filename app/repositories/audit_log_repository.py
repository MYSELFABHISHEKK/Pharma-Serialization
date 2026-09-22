from datetime import datetime, timezone
import json
from typing import Optional
from sqlalchemy.orm import Session
from app.models.db_models import AuditLog

class AuditLogRepository:
    @staticmethod
    def log(
        db: Session,
        event_type: str,
        table_name: str,
        record_id: str,
        previous_value: Optional[dict] = None,
        updated_value: Optional[dict] = None,
        performed_by: str = "system"
    ):
        prev_json = json.dumps(previous_value) if previous_value is not None else None
        upd_json = json.dumps(updated_value) if updated_value is not None else None
        
        log_entry = AuditLog(
            event_type=event_type,
            table_name=table_name,
            record_id=str(record_id),
            previous_value=prev_json,
            updated_value=upd_json,
            performed_by=performed_by,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        db.add(log_entry)
        db.flush()
