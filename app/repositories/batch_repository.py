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
            aggregated_batch=batch_dict.get("aggregated_batch", False)
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

        if "manufacturer" in batch_dict:
            db_batch.manufacturer = batch_dict["manufacturer"]
        if "plant" in batch_dict:
            db_batch.plant = batch_dict["plant"]
        if "packaging_level" in batch_dict:
            db_batch.packaging_level = batch_dict["packaging_level"]
        if "packaging_size" in batch_dict:
            db_batch.packaging_size = batch_dict["packaging_size"]
        if "work_order_no" in batch_dict:
            db_batch.work_order_no = batch_dict["work_order_no"]
        if "batch_lot" in batch_dict:
            db_batch.batch_lot = batch_dict["batch_lot"]
        if "expiry_date" in batch_dict:
            db_batch.expiry_date = batch_dict["expiry_date"]
        if "mfg_date" in batch_dict:
            db_batch.mfg_date = batch_dict["mfg_date"]
        if "is_enabled" in batch_dict:
            db_batch.is_enabled = batch_dict["is_enabled"]
        if "package_aggregation" in batch_dict:
            db_batch.package_aggregation = batch_dict["package_aggregation"]
        if "parent_code_required" in batch_dict:
            db_batch.parent_code_required = batch_dict["parent_code_required"]
        if "aggregated_batch" in batch_dict:
            db_batch.aggregated_batch = batch_dict["aggregated_batch"]
        if "status" in batch_dict:
            db_batch.status = batch_dict["status"]
        if "generated_quantity" in batch_dict:
            db_batch.generated_quantity = batch_dict["generated_quantity"]

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
