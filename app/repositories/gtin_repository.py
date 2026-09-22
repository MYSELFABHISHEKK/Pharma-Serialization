from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.db_models import GTINStore
from app.models.gtin_store import GTINStoreCreate
from app.repositories.audit_log_repository import AuditLogRepository

class GTINRepository:
    @staticmethod
    def get_by_id(db: Session, gtin_id: int) -> Optional[GTINStore]:
        return db.query(GTINStore).filter(GTINStore.id == gtin_id).first()

    @staticmethod
    def get_by_gtin(db: Session, gtin: str) -> Optional[GTINStore]:
        return db.query(GTINStore).filter(GTINStore.gtin == gtin).first()

    @staticmethod
    def serialize_gtin(g: GTINStore) -> dict:
        return {
            "id": g.id,
            "manufacturer": g.manufacturer,
            "plant": g.plant,
            "packaging_level": g.packaging_level,
            "product_id": g.product_id,
            "product_code": g.product_code,
            "packing_size": g.packing_size,
            "gtin": g.gtin,
            "enable_gtin": g.enable_gtin,
            "case_quantity": g.case_quantity,
            "limit": g.limit,
            "code_length": g.code_length,
            "serial_no_type": getattr(g, "serial_no_type", "SGTIN") or "SGTIN",
            "packaging_category": getattr(g, "packaging_category", "Primary") or "Primary",
            "created_at": g.created_at
        }

    @staticmethod
    def create(db: Session, gtin: GTINStoreCreate) -> GTINStore:
        db_gtin = GTINStore(
            manufacturer=gtin.manufacturer,
            plant=gtin.plant,
            packaging_level=gtin.packaging_level,
            product_id=gtin.product_id,
            product_code=gtin.product_code,
            packing_size=gtin.packing_size,
            gtin=gtin.gtin,
            enable_gtin=gtin.enable_gtin,
            case_quantity=gtin.case_quantity,
            limit=gtin.limit,
            code_length=gtin.code_length,
            serial_no_type=gtin.serial_no_type or "SGTIN",
            packaging_category=gtin.packaging_category or "Primary",
            created_at=datetime.now(timezone.utc).isoformat()
        )
        db.add(db_gtin)
        db.commit()
        db.refresh(db_gtin)

        # Log creation
        AuditLogRepository.log(
            db,
            event_type="CREATE_GTIN",
            table_name="gtin_store",
            record_id=str(db_gtin.id),
            previous_value=None,
            updated_value=GTINRepository.serialize_gtin(db_gtin)
        )
        db.commit()

        return db_gtin

    @staticmethod
    def update(db: Session, gtin_id: int, gtin: GTINStoreCreate) -> Optional[GTINStore]:
        db_gtin = GTINRepository.get_by_id(db, gtin_id)
        if not db_gtin:
            return None

        prev_val = GTINRepository.serialize_gtin(db_gtin)

        # Update properties
        db_gtin.manufacturer = gtin.manufacturer
        db_gtin.plant = gtin.plant
        db_gtin.packaging_level = gtin.packaging_level
        db_gtin.product_id = gtin.product_id
        db_gtin.product_code = gtin.product_code
        db_gtin.packing_size = gtin.packing_size
        db_gtin.gtin = gtin.gtin
        db_gtin.enable_gtin = gtin.enable_gtin
        db_gtin.case_quantity = gtin.case_quantity
        db_gtin.limit = gtin.limit
        db_gtin.code_length = gtin.code_length
        if hasattr(gtin, "serial_no_type") and gtin.serial_no_type:
            db_gtin.serial_no_type = gtin.serial_no_type
        if hasattr(gtin, "packaging_category") and gtin.packaging_category:
            db_gtin.packaging_category = gtin.packaging_category

        db.commit()
        db.refresh(db_gtin)

        new_val = GTINRepository.serialize_gtin(db_gtin)

        # Log change
        AuditLogRepository.log(
            db,
            event_type="UPDATE_GTIN",
            table_name="gtin_store",
            record_id=str(db_gtin.id),
            previous_value=prev_val,
            updated_value=new_val
        )
        db.commit()

        return db_gtin

    @staticmethod
    def list_all(db: Session) -> List[GTINStore]:
        return db.query(GTINStore).all()

    @staticmethod
    def get_by_product(db: Session, product_id: str) -> List[GTINStore]:
        return db.query(GTINStore).filter(GTINStore.product_id == product_id).all()
