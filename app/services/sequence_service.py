import logging
from sqlalchemy.orm import Session
from app.models.db_models import ProductSequence

logger = logging.getLogger("bt_sn_portal")

class SequenceService:
    @staticmethod
    def reserve_range(db: Session, product_id: str, quantity: int) -> tuple[int, int]:
        """
        Locks the sequence record for 'product_id', increments it by 'quantity',
        and returns the (start_sequence, end_sequence) range.
        This blocks concurrent updates on the same product, preventing race conditions.
        """
        # query with_for_update() locks the row until the transaction is committed or rolled back
        seq = db.query(ProductSequence).filter_by(product_id=product_id).with_for_update().first()
        
        if not seq:
            # First generation request: initialize sequence sequence
            seq = ProductSequence(product_id=product_id, next_sequence=1)
            db.add(seq)
            db.flush()
            
        start_sequence = seq.next_sequence
        seq.next_sequence += quantity
        end_sequence = seq.next_sequence - 1
        
        # Commit to save sequence consumption and release the row lock
        db.commit()
        
        logger.info(f"Reserved sequence range [{start_sequence} - {end_sequence}] for Product: {product_id}")
        return start_sequence, end_sequence
