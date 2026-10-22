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
            try:
                # High-speed PostgreSQL COPY command (handles both psycopg2 and psycopg 3)
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
                    if hasattr(cursor, "copy_from"):
                        # psycopg2 driver
                        cursor.copy_from(
                            buffer, 'sgtin_codes',
                            columns=('sequence', 'gtin', 'serial_number', 'sgtin', 'created_at')
                        )
                    elif hasattr(cursor, "copy"):
                        # psycopg 3 driver
                        with cursor.copy(
                            "COPY sgtin_codes (sequence, gtin, serial_number, sgtin, created_at) FROM STDIN"
                        ) as copy:
                            copy.write(buffer.getvalue())
                    else:
                        raise AttributeError("No bulk COPY method available on cursor")
                db.commit()
            except Exception:
                db.rollback()
                # Universal fallback using SQLAlchemy bulk insert
                chunk_size = 5000
                for i in range(0, len(docs), chunk_size):
                    db.bulk_insert_mappings(SGTINCode, docs[i:i+chunk_size])
                db.commit()
