from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.db_models import CodePool

class CodePoolRepository:
    @staticmethod
    def import_serials(db: Session, gtin: str, packaging_tier: str, serial_numbers: List[str]) -> Tuple[int, int]:
        now = datetime.now(timezone.utc).isoformat()
        clean_serials = [s.strip() for s in serial_numbers if s.strip()]
        if not clean_serials:
            return (0, 0)

        existing = set(
            row[0] for row in db.query(CodePool.serial_number)
            .filter(CodePool.serial_number.in_(clean_serials))
            .all()
        )

        to_insert = []
        for s in clean_serials:
            if s not in existing:
                to_insert.append(CodePool(
                    gtin=gtin,
                    serial_number=s,
                    packaging_tier=packaging_tier,
                    status="AVAILABLE",
                    batch_id=None,
                    imported_at=now
                ))
                existing.add(s)

        if to_insert:
            db.bulk_save_objects(to_insert)
            db.commit()

        imported_count = len(to_insert)
        skipped_count = len(clean_serials) - imported_count
        return (imported_count, skipped_count)

    @staticmethod
    def get_available_count(db: Session, gtin: str, packaging_tier: str) -> int:
        return db.query(CodePool).filter(
            CodePool.gtin == gtin,
            CodePool.packaging_tier == packaging_tier,
            CodePool.status == "AVAILABLE"
        ).count()

    @staticmethod
    def reserve_codes(db: Session, gtin: str, packaging_tier: str, quantity: int, batch_id: str) -> List[str]:
        if quantity <= 0:
            return []

        # Pull available codes sequentially
        available = (
            db.query(CodePool)
            .filter(
                CodePool.gtin == gtin,
                CodePool.packaging_tier == packaging_tier,
                CodePool.status == "AVAILABLE"
            )
            .order_by(CodePool.id.asc())
            .limit(quantity)
            .all()
        )

        reserved_serials = []
        for item in available:
            item.status = "RESERVED"
            item.batch_id = batch_id
            reserved_serials.append(item.serial_number)

        if available:
            db.commit()

        return reserved_serials

    @staticmethod
    def release_unused_codes(db: Session, batch_id: str, used_serials: List[str]) -> int:
        used_set = set(used_serials)
        reserved_items = db.query(CodePool).filter(
            CodePool.batch_id == batch_id,
            CodePool.status == "RESERVED"
        ).all()

        released_count = 0
        for item in reserved_items:
            if item.serial_number not in used_set:
                item.status = "AVAILABLE"
                item.batch_id = None
                released_count += 1

        if released_count > 0:
            db.commit()

        return released_count

    @staticmethod
    def get_stats(db: Session) -> Dict:
        total = db.query(CodePool).count()
        available = db.query(CodePool).filter(CodePool.status == "AVAILABLE").count()
        reserved = db.query(CodePool).filter(CodePool.status == "RESERVED").count()
        committed = db.query(CodePool).filter(CodePool.status == "COMMITTED").count()
        rejected = db.query(CodePool).filter(CodePool.status == "REJECTED").count()

        by_tier = {}
        tier_counts = (
            db.query(CodePool.packaging_tier, CodePool.status, func.count(CodePool.id))
            .group_by(CodePool.packaging_tier, CodePool.status)
            .all()
        )
        for tier, st, cnt in tier_counts:
            if tier not in by_tier:
                by_tier[tier] = {}
            by_tier[tier][st] = cnt

        return {
            "total_codes": total,
            "available_codes": available,
            "reserved_codes": reserved,
            "committed_codes": committed,
            "rejected_codes": rejected,
            "by_tier": by_tier
        }
