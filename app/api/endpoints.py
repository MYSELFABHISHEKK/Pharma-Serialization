import logging
import uuid
from fastapi import APIRouter, HTTPException, Depends, Header, status, Response
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text, desc

from app.models.product import ProductCreate, ProductResponse
from app.models.batch import BatchCreate, BatchResponse, BatchMasterCreate
from app.models.serial import SerialResponse, SerialStatusUpdate
from app.models.sgtin import SGTINGenerateRequest
from app.models.gtin_store import GTINStoreCreate, GTINStoreResponse
from app.models.audit_log import AuditLogResponse

from app.repositories.product_repository import ProductRepository
from app.repositories.batch_repository import BatchRepository
from app.repositories.serial_repository import SerialRepository
from app.repositories.sgtin_repository import SGTINRepository
from app.repositories.gtin_repository import GTINRepository
from app.models.db_models import AuditLog

from app.services.serialization_service import SerializationService
from app.services.sgtin_service import SGTINService
from app.core.database import get_db
from app.core.config import settings

logger = logging.getLogger("bt_sn_portal")
router = APIRouter(prefix="/api/v1")

# Simple API Key Authorization dependency
def verify_api_key(x_api_key: str = Header(default="")):
    if x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header"
        )
    return x_api_key

# Validation Helpers
def validate_product_master(product: ProductCreate):
    is_legacy = (
        product.manufacturer is None and
        product.plant is None and
        product.marketing_level is None and
        product.regulatory_authority is None
    )
    if is_legacy:
        return

    if not product.manufacturer:
        raise HTTPException(status_code=400, detail="Please Select Manufacturer")
    if not product.plant:
        raise HTTPException(status_code=400, detail="Please Select Plant.")
    if not product.marketing_level:
        raise HTTPException(status_code=400, detail="Please Select Marketing Level.")
    if not product.product_code:
        raise HTTPException(status_code=400, detail="Please enter product code")
    if not product.name:
        raise HTTPException(status_code=400, detail="Please enter Product Name.")
    
    if product.regulatory_authority == "DSCSA":
        if not product.ndc:
            raise HTTPException(status_code=400, detail="Please enter NDC")
        if not product.ndc_type:
            raise HTTPException(status_code=400, detail="Please select NDC Type")
    elif product.regulatory_authority == "EUFMD":
        if not product.country_drug_code_type or not product.country_drug_code:
            raise HTTPException(status_code=400, detail="Please enter Country Drug Code")
        if not product.country_drug_code_type:
            raise HTTPException(status_code=400, detail="Please enter Internal Material Number")
            
    if not product.item_code_type:
        raise HTTPException(status_code=400, detail="Please select Item Code Type")
    if not product.item_code:
        raise HTTPException(status_code=400, detail="Please enter Item Code")
    if not product.product_image:
        raise HTTPException(status_code=400, detail="Please enter image")
    
    # Decoded base64 size check (limit 3kb)
    image_str = product.product_image
    if image_str.startswith("data:image"):
        if "," in image_str:
            image_str = image_str.split(",")[1]
    
    padding = image_str.count("=")
    decoded_size = (len(image_str) * 3 // 4) - padding
    if decoded_size > 3072:
        raise HTTPException(status_code=400, detail="Image size should be less than 3kb.")

def validate_gtin_master(gtin: GTINStoreCreate):
    if not gtin.manufacturer:
        raise HTTPException(status_code=400, detail="Please Select Manufacturer")
    if not gtin.plant:
        raise HTTPException(status_code=400, detail="Please Select Plant.")
    if not gtin.product_id:
        raise HTTPException(status_code=400, detail="Please enter Product.")
    if not gtin.packaging_level:
        raise HTTPException(status_code=400, detail="Please enter Packaging Level.")
    if not gtin.packing_size:
        raise HTTPException(status_code=400, detail="Please enter Packaging Size.")
    if not gtin.gtin:
        raise HTTPException(status_code=400, detail="Please Select GTIN.")
    if gtin.packaging_level.upper() == "PRIMARY":
        if not gtin.case_quantity or gtin.case_quantity == 0:
            raise HTTPException(status_code=400, detail="Please enter Case Quantity.")
    if not gtin.limit:
        raise HTTPException(status_code=400, detail="Please enter Limit.")
    if not gtin.code_length:
        raise HTTPException(status_code=400, detail="Please enter code length.")

def validate_batch_master(batch: BatchMasterCreate):
    if not batch.manufacturer:
        raise HTTPException(status_code=400, detail="Please Select Manufacturer")
    if not batch.plant:
        raise HTTPException(status_code=400, detail="Please Select Plant.")
    if not batch.packaging_level:
        raise HTTPException(status_code=400, detail="Please select Packaging Level.")
    if not batch.product_id:
        raise HTTPException(status_code=400, detail="Please select Product.")
    if not batch.packaging_size:
        raise HTTPException(status_code=400, detail="Please enter Packaging Size.")
    if not batch.work_order_no:
        raise HTTPException(status_code=400, detail="Please enter Work Order No.")
    if not batch.batch_lot:
        raise HTTPException(status_code=400, detail="Please enter Batch Number.")
    if not batch.gtin:
        raise HTTPException(status_code=400, detail="Please enter GTIN.")
    if not batch.mfg_date:
        raise HTTPException(status_code=400, detail="Please enter Manufacturing Date.")
    if not batch.expiry_date:
        raise HTTPException(status_code=400, detail="Please enter Expiry Date.")
    if not batch.quantity or batch.quantity <= 0:
        raise HTTPException(status_code=400, detail="Please enter valid Quantity.")

# ----------------- Health Endpoint -----------------
@router.get("/health", tags=["System"])
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
    raise HTTPException(status_code=503, detail="Database connection failed")

# ----------------- Product Endpoints -----------------
@router.post("/products", response_model=ProductResponse, tags=["Products"])
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    validate_product_master(product)
    
    existing = ProductRepository.get_by_id(db, product.product_id)
    if existing:
        raise HTTPException(status_code=400, detail="Product ID already exists.")
    
    existing_gtin = ProductRepository.get_by_gtin(db, product.gtin)
    if existing_gtin:
        raise HTTPException(status_code=400, detail="GTIN already registered.")
        
    try:
        return ProductRepository.create(db, product)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/products/{product_id}", response_model=ProductResponse, tags=["Products"])
def update_product(product_id: str, product: ProductCreate, db: Session = Depends(get_db)):
    validate_product_master(product)
    
    # check if updated GTIN collides with another product
    existing_gtin = ProductRepository.get_by_gtin(db, product.gtin)
    if existing_gtin and existing_gtin.product_id != product_id:
        raise HTTPException(status_code=400, detail="GTIN already registered to another product.")
        
    updated = ProductRepository.update(db, product_id, product)
    if not updated:
        raise HTTPException(status_code=404, detail="Product not found.")
    return updated

@router.get("/products", response_model=List[ProductResponse], tags=["Products"])
def list_products(db: Session = Depends(get_db)):
    return ProductRepository.list_all(db)

# ----------------- GTIN Store Endpoints -----------------
@router.post("/gtin-store", response_model=GTINStoreResponse, tags=["GTIN Store"])
def create_gtin_store(gtin: GTINStoreCreate, db: Session = Depends(get_db)):
    validate_gtin_master(gtin)
    
    existing = GTINRepository.get_by_gtin(db, gtin.gtin)
    if existing:
        raise HTTPException(status_code=400, detail="GTIN already registered in store.")
        
    try:
        return GTINRepository.create(db, gtin)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/gtin-store/{gtin_id}", response_model=GTINStoreResponse, tags=["GTIN Store"])
def update_gtin_store(gtin_id: int, gtin: GTINStoreCreate, db: Session = Depends(get_db)):
    validate_gtin_master(gtin)
    
    existing = GTINRepository.get_by_gtin(db, gtin.gtin)
    if existing and existing.id != gtin_id:
        raise HTTPException(status_code=400, detail="GTIN already registered in store.")
        
    updated = GTINRepository.update(db, gtin_id, gtin)
    if not updated:
        raise HTTPException(status_code=404, detail="GTIN Store record not found.")
    return updated

@router.get("/gtin-store", response_model=List[GTINStoreResponse], tags=["GTIN Store"])
def list_gtin_store(db: Session = Depends(get_db)):
    return GTINRepository.list_all(db)

@router.get("/gtin-store/product/{product_id}", response_model=List[GTINStoreResponse], tags=["GTIN Store"])
def get_gtins_by_product(product_id: str, db: Session = Depends(get_db)):
    return GTINRepository.get_by_product(db, product_id)

# ----------------- Serialization Endpoints -----------------
@router.post("/serialization/generate", response_model=BatchResponse, tags=["Serialization"])
def generate_serials(batch: BatchCreate, db: Session = Depends(get_db)):
    try:
        result = SerializationService.generate_batch(
            db=db,
            product_id=batch.product_id,
            quantity=batch.quantity,
            batch_lot=batch.batch_lot,
            expiry_date=batch.expiry_date,
            idempotency_key=batch.idempotency_key
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

# ----------------- Batch Master Endpoints -----------------
@router.post("/batches", response_model=BatchResponse, tags=["Batches"])
def create_batch_master(batch: BatchMasterCreate, db: Session = Depends(get_db)):
    validate_batch_master(batch)
    
    try:
        result = SerializationService.generate_batch(
            db=db,
            product_id=batch.product_id,
            quantity=batch.quantity,
            batch_lot=batch.batch_lot,
            expiry_date=batch.expiry_date,
            idempotency_key=batch.idempotency_key or f"KEY-{uuid.uuid4().hex[:10].upper()}",
            manufacturer=batch.manufacturer,
            plant=batch.plant,
            packaging_level=batch.packaging_level,
            packaging_size=batch.packaging_size,
            work_order_no=batch.work_order_no,
            mfg_date=batch.mfg_date,
            is_enabled=batch.is_enabled,
            package_aggregation=batch.package_aggregation,
            parent_code_required=batch.parent_code_required,
            aggregated_batch=batch.aggregated_batch
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch master generation failed: {str(e)}")

@router.put("/batches/{batch_id}", response_model=BatchResponse, tags=["Batches"])
def update_batch_master(batch_id: str, batch: BatchMasterCreate, db: Session = Depends(get_db)):
    validate_batch_master(batch)
    
    batch_dict = {
        "manufacturer": batch.manufacturer,
        "plant": batch.plant,
        "packaging_level": batch.packaging_level,
        "packaging_size": batch.packaging_size,
        "work_order_no": batch.work_order_no,
        "batch_lot": batch.batch_lot,
        "expiry_date": batch.expiry_date,
        "mfg_date": batch.mfg_date,
        "is_enabled": batch.is_enabled,
        "package_aggregation": batch.package_aggregation,
        "parent_code_required": batch.parent_code_required,
        "aggregated_batch": batch.aggregated_batch
    }
    
    updated = BatchRepository.update(db, batch_id, batch_dict)
    if not updated:
        raise HTTPException(status_code=404, detail="Batch not found.")
    return updated

@router.get("/serialization/batches", response_model=List[BatchResponse], tags=["Serialization"])
def list_batches(db: Session = Depends(get_db)):
    return BatchRepository.list_all(db)

@router.get("/serialization/batches/{batch_id}", response_model=BatchResponse, tags=["Serialization"])
def get_batch(batch_id: str, db: Session = Depends(get_db)):
    batch = BatchRepository.get_by_id(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch

@router.get("/serialization/batches/{batch_id}/serials", response_model=List[SerialResponse], tags=["Serialization"])
def get_batch_serials(batch_id: str, db: Session = Depends(get_db)):
    batch = BatchRepository.get_by_id(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return SerialRepository.get_by_batch(db, batch_id)

# ----------------- SGTIN CSV Generation -----------------
@router.post("/sgtin/generate-csv", tags=["SGTIN"])
def generate_sgtin_csv(request: SGTINGenerateRequest, db: Session = Depends(get_db)):
    try:
        checked_existing = set()
        while True:
            rows = SGTINService.generate_rows_excluding_serials(
                gtin=request.gtin,
                quantity=request.quantity,
                existing_serials=checked_existing,
                start_sequence=request.start_sequence,
                length=request.length,
                alphabet=request.alphabet,
                require_alpha=request.require_alpha,
                require_numeric=request.require_numeric
            )
            candidates = [str(row["Serial Number"]) for row in rows]
            
            chunk_size = 50000
            collisions = []
            for i in range(0, len(candidates), chunk_size):
                chunk = candidates[i:i+chunk_size]
                chunk_collisions = SGTINRepository.check_serial_collisions(db, request.gtin, chunk)
                if chunk_collisions:
                    collisions.extend(chunk_collisions)
            
            if not collisions:
                break
            checked_existing.update(collisions)

        SGTINRepository.bulk_insert(db, rows)
        csv_content = SGTINService.to_csv(rows)
        filename = f"sgtin_{request.gtin}_{request.quantity}.csv"
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ----------------- Serial Validation & Management -----------------
@router.get("/serials/{serial_number}", tags=["Serials"])
def get_serial(serial_number: str, db: Session = Depends(get_db)):
    serial = SerialRepository.get_by_number(db, serial_number)
    if not serial:
        raise HTTPException(status_code=404, detail="Serial number not found")
    
    # Enrich with Product and Batch data
    product = ProductRepository.get_by_id(db, serial.product_id)
    batch = BatchRepository.get_by_id(db, serial.batch_id)
    
    # Also fetch all batch serials
    batch_serials = []
    if batch:
        raw_serials = SerialRepository.get_by_batch(db, batch.batch_id)
        batch_serials = [
            {
                "serial_number": s.serial_number,
                "sequence_number": s.sequence_number,
                "status": s.status,
                "created_at": s.created_at
            }
            for s in raw_serials
        ]
    
    gtin_val = product.gtin if product else None
    if not gtin_val and batch:
        gtin_val = getattr(batch, 'gtin', None)
        
    gtin_rec = GTINRepository.get_by_gtin(db, gtin_val) if gtin_val else None
    serial_no_type_val = (gtin_rec.serial_no_type if gtin_rec and gtin_rec.serial_no_type else ("SSCC" if (batch and batch.packaging_level == "Tertiary") else "SGTIN"))
    packaging_cat_val = (gtin_rec.packaging_category if gtin_rec and gtin_rec.packaging_category else (batch.packaging_level if batch else "Primary"))

    return {
        "serial_number": serial.serial_number,
        "sequence_number": serial.sequence_number,
        "product_id": serial.product_id,
        "product_name": product.name if product else serial.product_id,
        "gtin": gtin_val or "08901234567892",
        "serial_no_type": serial_no_type_val,
        "packaging_category": packaging_cat_val,
        "batch_id": serial.batch_id,
        "batch_lot": serial.batch_lot,
        "expiry_date": serial.expiry_date,
        "mfg_date": batch.mfg_date if batch else None,
        "manufacturer": batch.manufacturer if (batch and batch.manufacturer) else (product.manufacturer if product else "N/A"),
        "plant": batch.plant if (batch and batch.plant) else (product.plant if product else "N/A"),
        "packaging_level": batch.packaging_level if batch else "Primary",
        "packaging_size": batch.packaging_size if batch else "Standard",
        "work_order_no": batch.work_order_no if batch else "N/A",
        "requested_quantity": batch.requested_quantity if batch else 1,
        "aggregated_batch": getattr(batch, "aggregated_batch", False) if batch else False,
        "status": serial.status,
        "created_at": serial.created_at,
        "history": serial.history or [],
        "batch_serials": batch_serials
    }

@router.patch("/serials/{serial_number}/status", response_model=SerialResponse, tags=["Serials"])
def update_serial_status(serial_number: str, update: SerialStatusUpdate, db: Session = Depends(get_db)):
    serial = SerialRepository.get_by_number(db, serial_number)
    if not serial:
        raise HTTPException(status_code=404, detail="Serial number not found")
    
    allowed_transitions = {
        "GENERATED": ["ALLOCATED", "DECOMMISSIONED"],
        "ALLOCATED": ["SHIPPED", "DECOMMISSIONED"],
        "SHIPPED": ["SOLD", "DECOMMISSIONED"],
        "SOLD": ["ACTIVATED", "DECOMMISSIONED"],
        "ACTIVATED": ["DECOMMISSIONED"],
        "DECOMMISSIONED": []
    }
    
    current_status = serial.status if hasattr(serial, 'status') else serial.get("status", "GENERATED")
    target_status = update.status.upper()
    
    if target_status not in allowed_transitions.get(current_status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid state transition from {current_status} to {target_status}."
        )
        
    try:
        updated = SerialRepository.update_status(
            db=db,
            serial_number=serial_number,
            status=target_status,
            updated_by=update.updated_by,
            notes=update.notes
        )
        return updated
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ----------------- Audit Trail Endpoint -----------------
@router.get("/audit-logs", response_model=List[AuditLogResponse], tags=["Audit Logs"])
def get_audit_logs(db: Session = Depends(get_db)):
    return db.query(AuditLog).order_by(desc(AuditLog.timestamp)).all()
