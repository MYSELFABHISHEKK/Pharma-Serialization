from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.db_models import Serial

class SerialRepository:
    @staticmethod
    def get_by_number(db: Session, serial_number: str) -> Optional[Serial]:
        if not serial_number:
            return None
        clean_num = serial_number.strip().upper()
        # 1. Direct lookup by Serial Number
        serial = db.query(Serial).filter(Serial.serial_number == clean_num).first()
        if serial:
            return serial
        
        # 2. Lookup by Batch ID (e.g. SER-20260831-2D549A)
        serial_by_batch = db.query(Serial).filter(Serial.batch_id == clean_num).order_by(Serial.sequence_number.asc()).first()
        if serial_by_batch:
            return serial_by_batch
            
        # 3. Lookup by Batch Lot (e.g. BATCH-PARA-001)
        serial_by_lot = db.query(Serial).filter(Serial.batch_lot == clean_num).order_by(Serial.sequence_number.asc()).first()
        if serial_by_lot:
            return serial_by_lot
            
        return None

    @staticmethod
    def bulk_insert(db: Session, serial_docs: List[dict]):
        if not serial_docs:
            return
            
        if db.bind.dialect.name == "sqlite":
            # Test suite SQLite fallback (chunked inserts)
            chunk_size = 5000
            for i in range(0, len(serial_docs), chunk_size):
                db.bulk_insert_mappings(Serial, serial_docs[i:i+chunk_size])
            db.commit()
        else:
            try:
                # High-speed PostgreSQL COPY command (handles both psycopg2 and psycopg 3)
                import io
                import json
                buffer = io.StringIO()
                for doc in serial_docs:
                    history_json = json.dumps(doc["history"])
                    buffer.write(
                        f"{doc['serial_number']}\t{doc['sequence_number']}\t{doc['product_id']}\t"
                        f"{doc['batch_id']}\t{doc['batch_lot']}\t{doc['expiry_date']}\t"
                        f"{doc['status']}\t{doc['created_at']}\t{history_json}\n"
                    )
                buffer.seek(0)
                raw_conn = db.connection().connection.driver_connection
                with raw_conn.cursor() as cursor:
                    if hasattr(cursor, "copy_from"):
                        # psycopg2 driver
                        cursor.copy_from(
                            buffer, 'serials',
                            columns=('serial_number', 'sequence_number', 'product_id', 'batch_id', 'batch_lot', 'expiry_date', 'status', 'created_at', 'history')
                        )
                    elif hasattr(cursor, "copy"):
                        # psycopg 3 driver
                        with cursor.copy(
                            "COPY serials (serial_number, sequence_number, product_id, batch_id, batch_lot, expiry_date, status, created_at, history) FROM STDIN"
                        ) as copy:
                            copy.write(buffer.getvalue())
                    else:
                        raise AttributeError("No bulk COPY method available on cursor")
                db.commit()
            except Exception:
                db.rollback()
                # Universal fallback using SQLAlchemy bulk insert
                chunk_size = 5000
                for i in range(0, len(serial_docs), chunk_size):
                    db.bulk_insert_mappings(Serial, serial_docs[i:i+chunk_size])
                db.commit()

    @staticmethod
    def update_status(db: Session, serial_number: str, status: str, updated_by: str, notes: Optional[str] = None) -> Optional[Serial]:
        serial = db.query(Serial).filter(Serial.serial_number == serial_number.upper().strip()).first()
        if not serial:
            return None
        
        timestamp = datetime.now(timezone.utc).isoformat()
        history_entry = {
            "status": status,
            "updated_by": updated_by,
            "timestamp": timestamp,
            "notes": notes
        }
        
        # SQLAlchemy requires assigning a new list object for JSON mutations to register cleanly
        history = list(serial.history) if serial.history else []
        history.append(history_entry)
        serial.history = history
        serial.status = status
        
        db.commit()
        db.refresh(serial)
        return serial

    @staticmethod
    def get_by_batch(db: Session, batch_id: str) -> List[Serial]:
        return db.query(Serial).filter(Serial.batch_id == batch_id).all()

    @staticmethod
    def check_collisions(db: Session, serial_candidates: List[str]) -> List[str]:
        existing = db.query(Serial.serial_number).filter(Serial.serial_number.in_(serial_candidates)).all()
        return [row[0] for row in existing]
