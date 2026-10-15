from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.db_models import Batch, Idempotency
from app.repositories.audit_log_repository import AuditLogRepository

class BatchRepository:
    @staticmethod
    def get_by_id(db: Session, batch_id: str) -> Optional[Batch]:
        return db.query(Batch).filter(Batch.batch_id == batch_id).first()

    @staticmethod
    def get_by_idempotency_key(db: Session, idempotency_key: str) -> Optional[str]:
        record = db.query(Idempotency).filter(Idempotency.idempotency_key == idempotency_key).first()
        return record.batch_id if record else None

    @staticmethod
    def register_idempotency(db: Session, idempotency_key: str, batch_id: str):
        record = Idempotency(
            idempotency_key=idempotency_key,
            batch_id=batch_id,
            created_at=datetime.now(timezone.utc)
        )
        db.add(record)
        db.commit()

    @staticmethod
    def serialize_batch(b: Batch) -> dict:
        return {
            "batch_id": b.batch_id,
            "product_id": b.product_id,
            "requested_quantity": b.requested_quantity,
            "generated_quantity": b.generated_quantity,
            "start_sequence": b.start_sequence,
            "end_sequence": b.end_sequence,
            "batch_lot": b.batch_lot,
            "expiry_date": b.expiry_date,
            "status": b.status,
            "created_at": b.created_at,
            "manufacturer": b.manufacturer,
            "plant": b.plant,
            "packaging_level": b.packaging_level,
            "packaging_size": b.packaging_size,
            "work_order_no": b.work_order_no,
            "mfg_date": b.mfg_date,
            "is_enabled": b.is_enabled,
            "package_aggregation": b.package_aggregation,
            "parent_code_required": b.parent_code_required,
            "aggregated_batch": getattr(b, "aggregated_batch", False),
            "line_id": getattr(b, "line_id", None),
            "secondary_ratio": getattr(b, "secondary_ratio", 1) or 1,
            "tertiary_ratio": getattr(b, "tertiary_ratio", 1) or 1,
            "primary_quantity": getattr(b, "primary_quantity", 0) or 0,
            "secondary_quantity": getattr(b, "secondary_quantity", 0) or 0,
            "tertiary_quantity": getattr(b, "tertiary_quantity", 0) or 0,
            "reconciled_good_count": getattr(b, "reconciled_good_count", 0) or 0,
            "reconciled_rejected_count": getattr(b, "reconciled_rejected_count", 0) or 0,
            "reconciled_unused_count": getattr(b, "reconciled_unused_count", 0) or 0,
            "yield_percentage": getattr(b, "yield_percentage", 0.0) or 0.0,
            "is_locked": getattr(b, "is_locked", False) or False,
            "io_channel": getattr(b, "io_channel", "DIRECT_API") or "DIRECT_API",
        }

    @staticmethod
    def create(db: Session, batch_dict: dict) -> Batch:
        db_batch = Batch(
            batch_id=batch_dict["batch_id"],
            product_id=batch_dict["product_id"],
            requested_quantity=batch_dict["requested_quantity"],
            generated_quantity=batch_dict["generated_quantity"],
            start_sequence=batch_dict["start_sequence"],
            end_sequence=batch_dict["end_sequence"],
            batch_lot=batch_dict["batch_lot"],
            expiry_date=batch_dict["expiry_date"],
            status=batch_dict["status"],
            created_at=datetime.now(timezone.utc).isoformat(),
            manufacturer=batch_dict.get("manufacturer"),
            plant=batch_dict.get("plant"),
            packaging_level=batch_dict.get("packaging_level"),
            packaging_size=batch_dict.get("packaging_size"),
            work_order_no=batch_dict.get("work_order_no"),
            mfg_date=batch_dict.get("mfg_date"),
            is_enabled=batch_dict.get("is_enabled", True),
            package_aggregation=batch_dict.get("package_aggregation", False),
            parent_code_required=batch_dict.get("parent_code_required", False),
            aggregated_batch=batch_dict.get("aggregated_batch", False),
            line_id=batch_dict.get("line_id"),
            secondary_ratio=batch_dict.get("secondary_ratio", 1),
            tertiary_ratio=batch_dict.get("tertiary_ratio", 1),
            primary_quantity=batch_dict.get("primary_quantity", 0),
            secondary_quantity=batch_dict.get("secondary_quantity", 0),
            tertiary_quantity=batch_dict.get("tertiary_quantity", 0),
            reconciled_good_count=batch_dict.get("reconciled_good_count", 0),
            reconciled_rejected_count=batch_dict.get("reconciled_rejected_count", 0),
            reconciled_unused_count=batch_dict.get("reconciled_unused_count", 0),
            yield_percentage=batch_dict.get("yield_percentage", 0.0),
            is_locked=batch_dict.get("is_locked", False),
            io_channel=batch_dict.get("io_channel", "DIRECT_API")
        )
        db.add(db_batch)
        db.commit()
        db.refresh(db_batch)

        # Log creation
        AuditLogRepository.log(
            db,
            event_type="CREATE_BATCH",
            table_name="batches",
            record_id=db_batch.batch_id,
            previous_value=None,
            updated_value=BatchRepository.serialize_batch(db_batch)
        )
        db.commit()

        return db_batch

    @staticmethod
    def update(db: Session, batch_id: str, batch_dict: dict) -> Optional[Batch]:
        db_batch = BatchRepository.get_by_id(db, batch_id)
        if not db_batch:
            return None

        prev_val = BatchRepository.serialize_batch(db_batch)

        for col in [
            "manufacturer", "plant", "packaging_level", "packaging_size", "work_order_no",
            "batch_lot", "expiry_date", "mfg_date", "is_enabled", "package_aggregation",
            "parent_code_required", "aggregated_batch", "status", "generated_quantity",
            "line_id", "secondary_ratio", "tertiary_ratio", "primary_quantity",
            "secondary_quantity", "tertiary_quantity", "reconciled_good_count",
            "reconciled_rejected_count", "reconciled_unused_count", "yield_percentage",
            "is_locked", "io_channel"
        ]:
            if col in batch_dict:
                setattr(db_batch, col, batch_dict[col])

        db.commit()
        db.refresh(db_batch)

        new_val = BatchRepository.serialize_batch(db_batch)

        # Log change
        AuditLogRepository.log(
            db,
            event_type="UPDATE_BATCH",
            table_name="batches",
            record_id=db_batch.batch_id,
            previous_value=prev_val,
            updated_value=new_val
        )
        db.commit()

        return db_batch

    @staticmethod
    def update_status(db: Session, batch_id: str, status: str, generated_quantity: int):
        # reuse update logic for consistency and logging
        BatchRepository.update(db, batch_id, {"status": status, "generated_quantity": generated_quantity})

    @staticmethod
    def list_all(db: Session) -> List[Batch]:
        return db.query(Batch).order_by(Batch.created_at.desc()).all()
