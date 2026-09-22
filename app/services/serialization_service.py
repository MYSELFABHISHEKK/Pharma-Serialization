import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from app.repositories.product_repository import ProductRepository
from app.repositories.batch_repository import BatchRepository
from app.repositories.serial_repository import SerialRepository
from app.services.sequence_service import SequenceService
from app.services.serial_generator import SerialGenerator
from app.models.product import SerializationProfile

logger = logging.getLogger("bt_sn_portal")

class SerializationService:
    @staticmethod
    def generate_batch(
        db: Session,
        product_id: str,
        quantity: int,
        batch_lot: str,
        expiry_date: str,
        idempotency_key: str,
        manufacturer: Optional[str] = None,
        plant: Optional[str] = None,
        packaging_level: Optional[str] = None,
        packaging_size: Optional[str] = None,
        work_order_no: Optional[str] = None,
        mfg_date: Optional[str] = None,
        is_enabled: bool = True,
        package_aggregation: bool = False,
        parent_code_required: bool = False,
        aggregated_batch: bool = False
    ) -> Dict:
        # 1. Idempotency Check
        existing_batch_id = BatchRepository.get_by_idempotency_key(db, idempotency_key) if idempotency_key else None
        if existing_batch_id:
            logger.info(f"Idempotency hit! Returning existing Batch: {existing_batch_id}")
            existing_batch = BatchRepository.get_by_id(db, existing_batch_id)
            if existing_batch:
                return BatchRepository.serialize_batch(existing_batch)

        # 2. Validate Product
        product = ProductRepository.get_by_id(db, product_id)
        if not product:
            raise ValueError(f"Product with ID '{product_id}' does not exist.")
        
        # Build profile settings from flat columns
        profile = SerializationProfile(
            length=product.profile_len,
            alphabet=product.profile_alphabet,
            require_alpha=product.profile_require_alpha,
            require_numeric=product.profile_require_numeric,
            allow_duplicate_characters=product.profile_allow_duplicate_chars
        )

        # 3. Reserve Sequence Range (Atomic)
        start_seq, end_seq = SequenceService.reserve_range(db, product_id, quantity)

        # 4. Generate Unique Serials
        batch_id = f"SER-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        
        batch_record = {
            "batch_id": batch_id,
            "product_id": product_id,
            "requested_quantity": quantity,
            "generated_quantity": 0,
            "start_sequence": start_seq,
            "end_sequence": end_seq,
            "batch_lot": batch_lot,
            "expiry_date": expiry_date,
            "status": "PROCESSING",
            "manufacturer": manufacturer,
            "plant": plant,
            "packaging_level": packaging_level,
            "packaging_size": packaging_size,
            "work_order_no": work_order_no,
            "mfg_date": mfg_date,
            "is_enabled": is_enabled,
            "package_aggregation": package_aggregation,
            "parent_code_required": parent_code_required,
            "aggregated_batch": aggregated_batch
        }
        BatchRepository.create(db, batch_record)
        if idempotency_key:
            BatchRepository.register_idempotency(db, idempotency_key, batch_id)

        try:
            generated_serials: List[str] = []
            checked_existing = set()
            
            while len(generated_serials) < quantity:
                needed = quantity - len(generated_serials)
                candidates = SerialGenerator.generate_batch(needed, profile, checked_existing)
                
                collisions = SerialRepository.check_collisions(db, candidates)
                if collisions:
                    checked_existing.update(collisions)
                    valid_candidates = [c for c in candidates if c not in collisions]
                    generated_serials.extend(valid_candidates)
                else:
                    generated_serials.extend(candidates)

            # 5. Populate Serial Documents
            serial_docs = []
            current_time = datetime.now(timezone.utc).isoformat()
            
            for idx, serial_num in enumerate(generated_serials):
                seq_num = start_seq + idx
                doc = {
                    "serial_number": serial_num,
                    "sequence_number": seq_num,
                    "product_id": product_id,
                    "batch_id": batch_id,
                    "batch_lot": batch_lot,
                    "expiry_date": expiry_date,
                    "status": "GENERATED",
                    "created_at": current_time,
                    "history": [
                        {
                            "status": "GENERATED",
                            "updated_by": "system",
                            "timestamp": current_time,
                            "notes": f"Generated in batch {batch_id}"
                        }
                    ]
                }
                serial_docs.append(doc)

            # 6. Bulk Insert
            SerialRepository.bulk_insert(db, serial_docs)

            # 7. Verify counts match exactly
            stored_count = len(serial_docs)
            if stored_count != quantity:
                raise RuntimeError(
                    f"Count mismatch: requested {quantity}, generated {stored_count}."
                )

            # 8. Complete Batch
            updated_batch = BatchRepository.update(db, batch_id, {
                "status": "COMPLETED",
                "generated_quantity": stored_count
            })
            
            return BatchRepository.serialize_batch(updated_batch)

        except Exception as e:
            logger.error(f"Batch generation failed for {batch_id}: {e}")
            BatchRepository.update_status(db, batch_id, "FAILED", 0)
            raise e
