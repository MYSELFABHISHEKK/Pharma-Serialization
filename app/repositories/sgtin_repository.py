from datetime import datetime, timezone
from typing import List
from sqlalchemy.orm import Session
from app.models.db_models import SGTINCode

class SGTINRepository:
    @staticmethod
    def check_serial_collisions(db: Session, gtin: str, serial_candidates: List[str]) -> List[str]:
        existing = db.query(SGTINCode.serial_number).filter(
            SGTINCode.gtin == gtin,
            SGTINCode.serial_number.in_(serial_candidates)
        ).all()
        return [row[0] for row in existing]

    @staticmethod
    def bulk_insert(db: Session, rows: List[dict]) -> None:
        if not rows:
            return

        timestamp = datetime.now(timezone.utc).isoformat()
        docs = [
            {
                "sequence": row["Sequence"],
                "gtin": row["GTIN"],
                "serial_number": row["Serial Number"],
                "sgtin": row["SGTIN"],
                "created_at": timestamp,
            }
            for row in rows
        ]
        
        if db.bind.dialect.name == "sqlite":
            # Test suite SQLite fallback (chunked inserts)
            chunk_size = 5000
            for i in range(0, len(docs), chunk_size):
                db.bulk_insert_mappings(SGTINCode, docs[i:i+chunk_size])
            db.commit()
        else:
            # PostgreSQL COPY command (inserts 1,000,000 rows in ~0.5s)
            import io
            buffer = io.StringIO()
            for doc in docs:
                buffer.write(
                    f"{doc['sequence']}\t{doc['gtin']}\t{doc['serial_number']}\t"
                    f"{doc['sgtin']}\t{doc['created_at']}\n"
                )
            buffer.seek(0)
            raw_conn = db.connection().connection.driver_connection
            with raw_conn.cursor() as cursor:
                cursor.copy_from(
                    buffer, 'sgtin_codes',
                    columns=('sequence', 'gtin', 'serial_number', 'sgtin', 'created_at')
                )
            db.commit()
