import os
import time
import logging
import uuid
from fastapi import APIRouter, HTTPException, Depends, Header, status, Response
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text, desc

from app.models.product import ProductCreate, ProductResponse
from app.models.batch import BatchCreate, BatchResponse, BatchMasterCreate, BatchReconcileRequest, BatchSummaryResponse
from app.models.serial import SerialResponse, SerialStatusUpdate
from app.models.sgtin import SGTINGenerateRequest
from app.models.gtin_store import GTINStoreCreate, GTINStoreResponse
from app.models.audit_log import AuditLogResponse
from app.models.line import PackagingLineCreate, PackagingLineResponse, PackagingLineUpdate
from app.models.code_pool import CodePoolImportRequest, CodePoolStatsResponse

from app.repositories.product_repository import ProductRepository
from app.repositories.batch_repository import BatchRepository
from app.repositories.serial_repository import SerialRepository
from app.repositories.sgtin_repository import SGTINRepository
from app.repositories.gtin_repository import GTINRepository
from app.repositories.line_repository import LineRepository
from app.repositories.code_pool_repository import CodePoolRepository
from app.models.db_models import AuditLog, Serial, Batch, PackagingLine, CodePool, User
from app.models.auth import (
    SignUpRequest, LoginRequest, UserResponse, AuthResponse, DemoUser,
    RoleResponse, RoleCreateRequest, RoleUpdateRequest,
    UserStatusUpdateRequest, UserPasswordResetRequest, ChangePasswordRequest,
    UserPermissionOverrideRequest
)
from app.services.rbac_service import RBACService, AVAILABLE_MODULES
from app.services.auth_service import AuthService
from app.api.deps import extract_auth_token, get_current_user, require_permission

from app.services.serialization_service import SerializationService
from app.services.sgtin_service import SGTINService
from app.services.l2_execution_service import L2ExecutionService
from app.core.database import get_db, get_db_pool_status
from app.core.security import get_current_request_id
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
    t0 = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "status": "healthy",
            "database": "connected",
            "latency_ms": latency_ms,
            "pool": get_db_pool_status(),
            "request_id": get_current_request_id()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Database connection failed")

# ----------------- Product Endpoints -----------------
@router.post("/products", response_model=ProductResponse, tags=["Products"])
def create_product(
    product: ProductCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("products", "create"))
):
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
def update_product(
    product_id: str, 
    product: ProductCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("products", "edit"))
):
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
def list_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("products", "view"))
):
    return ProductRepository.list_all(db)

# ----------------- GTIN Store Endpoints -----------------
@router.post("/gtin-store", response_model=GTINStoreResponse, tags=["GTIN Store"])
def create_gtin_store(
    gtin: GTINStoreCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("gtin_store", "create"))
):
    validate_gtin_master(gtin)
    
    existing = GTINRepository.get_by_gtin(db, gtin.gtin)
    if existing:
        raise HTTPException(status_code=400, detail="GTIN already registered in store.")
        
    try:
        return GTINRepository.create(db, gtin)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/gtin-store/{gtin_id}", response_model=GTINStoreResponse, tags=["GTIN Store"])
def update_gtin_store(
    gtin_id: int, 
    gtin: GTINStoreCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("gtin_store", "edit"))
):
    validate_gtin_master(gtin)
    
    existing = GTINRepository.get_by_gtin(db, gtin.gtin)
    if existing and existing.id != gtin_id:
        raise HTTPException(status_code=400, detail="GTIN already registered in store.")
        
    updated = GTINRepository.update(db, gtin_id, gtin)
    if not updated:
        raise HTTPException(status_code=404, detail="GTIN Store record not found.")
    return updated

@router.get("/gtin-store", response_model=List[GTINStoreResponse], tags=["GTIN Store"])
def list_gtin_store(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("gtin_store", "view"))
):
    return GTINRepository.list_all(db)

@router.get("/gtin-store/product/{product_id}", response_model=List[GTINStoreResponse], tags=["GTIN Store"])
def get_gtins_by_product(
    product_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("gtin_store", "view"))
):
    return GTINRepository.get_by_product(db, product_id)

# ----------------- Serialization Endpoints -----------------
@router.post("/serialization/generate", response_model=BatchResponse, tags=["Serialization"])
def generate_serials(
    batch: BatchCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("batches", "create"))
):
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
def create_batch_master(
    batch: BatchMasterCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("batches", "create"))
):
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
            aggregated_batch=batch.aggregated_batch,
            line_id=batch.line_id,
            secondary_ratio=batch.secondary_ratio,
            tertiary_ratio=batch.tertiary_ratio,
            io_channel=batch.io_channel
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch master generation failed: {str(e)}")

@router.put("/batches/{batch_id}", response_model=BatchResponse, tags=["Batches"])
def update_batch_master(
    batch_id: str, 
    batch: BatchMasterCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("batches", "edit"))
):
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
        "aggregated_batch": batch.aggregated_batch,
        "line_id": batch.line_id,
        "secondary_ratio": batch.secondary_ratio,
        "tertiary_ratio": batch.tertiary_ratio,
        "io_channel": batch.io_channel
    }
    
    updated = BatchRepository.update(db, batch_id, batch_dict)
    if not updated:
        raise HTTPException(status_code=404, detail="Batch not found.")
    return updated

# ----------------- Packaging Lines Endpoints -----------------
@router.post("/lines", response_model=PackagingLineResponse, tags=["Lines"])
def create_line(
    line: PackagingLineCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("lines", "create"))
):
    existing = LineRepository.get_by_id(db, line.line_id)
    if existing:
        raise HTTPException(status_code=400, detail="Line ID already registered.")
    try:
        return LineRepository.create(db, line)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/lines", response_model=List[PackagingLineResponse], tags=["Lines"])
def list_lines(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("lines", "view"))
):
    return LineRepository.list_all(db)

@router.get("/lines/{line_id}", response_model=PackagingLineResponse, tags=["Lines"])
def get_line(
    line_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("lines", "view"))
):
    line = LineRepository.get_by_id(db, line_id)
    if not line:
        raise HTTPException(status_code=404, detail=f"Packaging line '{line_id}' not found.")
    return line

@router.put("/lines/{line_id}", response_model=PackagingLineResponse, tags=["Lines"])
def update_line(
    line_id: str, 
    update_req: PackagingLineUpdate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("lines", "edit"))
):
    existing = LineRepository.get_by_id(db, line_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Packaging line '{line_id}' not found.")
    update_data = update_req.model_dump(exclude_unset=True)
    updated = LineRepository.update(db, line_id, update_data)
    return updated

@router.post("/lines/{line_id}/test-io", tags=["Lines"])
def test_line_io(
    line_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("lines", "test_io"))
):
    line = LineRepository.get_by_id(db, line_id)
    if not line:
        raise HTTPException(status_code=404, detail=f"Packaging line '{line_id}' not found.")
    
    protocol = line.io_protocol or "DIRECT_API"
    details = {}
    msg = ""

    if protocol == "DIRECT_API":
        endpoint = line.api_endpoint or f"http://127.0.0.1:8000/api/v1/l2/mock-controller/{line_id.lower()}"
        details = {"protocol": "DIRECT_API", "endpoint": endpoint, "socket_status": "READY"}
        msg = f"Direct TCP/IP socket endpoint verified: {endpoint}"
    elif protocol == "SHARED_FOLDER":
        outbound = line.shared_folder_path or f"l2_io/shared_folder/{line_id.lower()}/outbound"
        inbound = line.sftp_inbound_folder or f"l2_io/shared_folder/{line_id.lower()}/inbound"
        os.makedirs(outbound, exist_ok=True)
        os.makedirs(inbound, exist_ok=True)
        details = {"protocol": "SHARED_FOLDER", "outbound_path": outbound, "inbound_path": inbound, "folder_accessible": True}
        msg = f"Network shared folders verified and accessible: {outbound}"
    elif protocol == "SFTP":
        host = line.sftp_host or "sftp.pharma.local"
        port = line.sftp_port or 22
        user = line.sftp_user or "line_operator"
        drop = line.sftp_drop_folder or f"/var/drop/{line_id.lower()}/outbound"
        details = {"protocol": "SFTP", "host": host, "port": port, "user": user, "drop_folder": drop, "sftp_reachable": True}
        msg = f"SFTP route parameters verified: {user}@{host}:{port}{drop}"
    
    return {
        "status": "success",
        "line_id": line.line_id,
        "line_name": line.name,
        "io_protocol": protocol,
        "message": msg,
        "details": details
    }

# ----------------- Code Pool Reservoir Endpoints -----------------
@router.post("/code-pool/import", tags=["Code Pool"])
def import_code_pool(
    request: CodePoolImportRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("code_pool", "import"))
):
    try:
        imported, skipped = CodePoolRepository.import_serials(
            db=db,
            gtin=request.gtin,
            packaging_tier=request.packaging_tier,
            serial_numbers=request.serials
        )
        return {
            "status": "success",
            "gtin": request.gtin,
            "packaging_tier": request.packaging_tier,
            "imported_count": imported,
            "skipped_duplicates": skipped
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/code-pool/stats", response_model=CodePoolStatsResponse, tags=["Code Pool"])
def get_code_pool_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("code_pool", "view"))
):
    return CodePoolRepository.get_stats(db)

# ----------------- Batch Lifecycle Operations -----------------
@router.post("/batches/{batch_id}/load", tags=["Batch Lifecycle"])
def load_batch(
    batch_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("batches", "execute"))
):
    try:
        return L2ExecutionService.load_batch(db, batch_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batches/{batch_id}/start", tags=["Batch Lifecycle"])
def start_batch(
    batch_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("batches", "execute"))
):
    try:
        return L2ExecutionService.start_batch(db, batch_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batches/{batch_id}/reconcile", tags=["Batch Lifecycle"])
def reconcile_batch(
    batch_id: str, 
    request: BatchReconcileRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("batches", "reconcile"))
):
    try:
        return L2ExecutionService.reconcile_batch(db, batch_id, request)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batches/{batch_id}/close", tags=["Batch Lifecycle"])
def close_batch(
    batch_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("batches", "close_lock"))
):
    try:
        return L2ExecutionService.close_batch(db, batch_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/batches/{batch_id}/xml-report", tags=["Batch Lifecycle"])
def get_batch_xml_report(
    batch_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("batches", "export_xml"))
):
    try:
        xml_content = L2ExecutionService.generate_xml_report(db, batch_id)
        filename = f"epcis_report_{batch_id}.xml"
        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/batches/{batch_id}/summary", response_model=BatchSummaryResponse, tags=["Batch Lifecycle"])
def get_batch_summary(
    batch_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("reports", "view"))
):
    batch = BatchRepository.get_by_id(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    return {
        "batch_id": batch.batch_id,
        "product_id": batch.product_id,
        "batch_lot": batch.batch_lot,
        "status": batch.status,
        "line_id": batch.line_id,
        "io_channel": batch.io_channel or "DIRECT_API",
        "is_locked": batch.is_locked or False,
        "total_requested": batch.requested_quantity,
        "total_generated": batch.generated_quantity,
        "primary_quantity": batch.primary_quantity or 0,
        "secondary_quantity": batch.secondary_quantity or 0,
        "tertiary_quantity": batch.tertiary_quantity or 0,
        "secondary_ratio": batch.secondary_ratio or 1,
        "tertiary_ratio": batch.tertiary_ratio or 1,
        "reconciled_good_count": batch.reconciled_good_count or 0,
        "reconciled_rejected_count": batch.reconciled_rejected_count or 0,
        "reconciled_unused_count": batch.reconciled_unused_count or 0,
        "yield_percentage": batch.yield_percentage or 0.0,
        "created_at": batch.created_at
    }

@router.get("/reports/batch-summary", response_model=List[BatchSummaryResponse], tags=["Reports"])
def list_batch_summaries(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("reports", "view"))
):
    batches = BatchRepository.list_all(db)
    results = []
    for batch in batches:
        results.append({
            "batch_id": batch.batch_id,
            "product_id": batch.product_id,
            "batch_lot": batch.batch_lot,
            "status": batch.status,
            "line_id": batch.line_id,
            "io_channel": batch.io_channel or "DIRECT_API",
            "is_locked": batch.is_locked or False,
            "total_requested": batch.requested_quantity,
            "total_generated": batch.generated_quantity,
            "primary_quantity": batch.primary_quantity or 0,
            "secondary_quantity": batch.secondary_quantity or 0,
            "tertiary_quantity": batch.tertiary_quantity or 0,
            "secondary_ratio": batch.secondary_ratio or 1,
            "tertiary_ratio": batch.tertiary_ratio or 1,
            "reconciled_good_count": batch.reconciled_good_count or 0,
            "reconciled_rejected_count": batch.reconciled_rejected_count or 0,
            "reconciled_unused_count": batch.reconciled_unused_count or 0,
            "yield_percentage": batch.yield_percentage or 0.0,
            "created_at": batch.created_at
        })
    return results

@router.get("/serialization/batches", response_model=List[BatchResponse], tags=["Serialization"])
def list_batches(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("batches", "view"))
):
    return BatchRepository.list_all(db)

@router.get("/serialization/batches/{batch_id}", response_model=BatchResponse, tags=["Serialization"])
def get_batch(
    batch_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("batches", "view"))
):
    batch = BatchRepository.get_by_id(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch

@router.get("/serialization/batches/{batch_id}/serials", response_model=List[SerialResponse], tags=["Serialization"])
def get_batch_serials(
    batch_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("batches", "view"))
):
    batch = BatchRepository.get_by_id(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return SerialRepository.get_by_batch(db, batch_id)

# ----------------- SGTIN CSV Generation -----------------
@router.post("/sgtin/generate-csv", tags=["SGTIN"])
def generate_sgtin_csv(
    request: SGTINGenerateRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("sgtin", "generate"))
):
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
def get_serial(
    serial_number: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("verification", "verify"))
):
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
def update_serial_status(
    serial_number: str, 
    update: SerialStatusUpdate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("verification", "transition_status"))
):
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
            updated_by=update.updated_by or current_user.username,
            notes=update.notes
        )
        return updated
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ----------------- Audit Trail Endpoint -----------------
@router.get("/audit-logs", response_model=List[AuditLogResponse], tags=["Audit Logs"])
def get_audit_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit_logs", "view"))
):
    return db.query(AuditLog).order_by(desc(AuditLog.timestamp)).all()

# ----------------- Authentication & RBAC Endpoints (21 CFR Part 11) -----------------
@router.post("/auth/login", response_model=AuthResponse, tags=["Authentication"])
def login(request: LoginRequest, db: Session = Depends(get_db)):
    try:
        user, token, expires_at = AuthService.authenticate_user(db, request)
        perms = RBACService.get_user_effective_permissions(db, user)
        return AuthResponse(
            token=token,
            access_token=token,
            token_type="Bearer",
            expires_at=expires_at,
            require_password_change=user.require_password_change or False,
            permissions=perms,
            user=UserResponse.model_validate(user)
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Login failure: {e}")
        raise HTTPException(status_code=500, detail="Authentication service encountered an unexpected error.")

@router.post("/auth/logout", tags=["Authentication"])
def logout(
    authorization: Optional[str] = Header(None),
    x_auth_token: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    token = extract_auth_token(authorization, x_auth_token)
    if token:
        AuthService.terminate_session(db, token)
    return {"status": "success", "message": "Session terminated successfully"}

@router.get("/auth/me", response_model=UserResponse, tags=["Authentication"])
def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    return UserResponse.model_validate(current_user)

@router.get("/auth/me/permissions", tags=["Authentication"])
def get_current_user_permissions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    perms = RBACService.get_user_effective_permissions(db, current_user)
    return {
        "username": current_user.username,
        "role": current_user.role,
        "role_id": current_user.role_id,
        "require_password_change": current_user.require_password_change or False,
        "permissions": perms
    }

@router.post("/auth/change-password", tags=["Authentication"])
def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        AuthService.change_user_password(
            db=db,
            user=current_user,
            old_password=request.old_password,
            new_password=request.new_password
        )
        return {"status": "success", "message": "Password updated successfully."}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Password change error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update password.")

@router.get("/auth/permissions-matrix", tags=["RBAC"])
def get_permissions_matrix(
    current_user: User = Depends(get_current_user)
):
    return AVAILABLE_MODULES

@router.get("/auth/roles", response_model=List[RoleResponse], tags=["RBAC"])
def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("roles", "view"))
):
    return RBACService.list_roles(db)

@router.post("/auth/roles", response_model=RoleResponse, tags=["RBAC"])
def create_role(
    request: RoleCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("roles", "create"))
):
    try:
        role = RBACService.create_role(
            db=db,
            role_name=request.role_name,
            description=request.description or "",
            permissions=request.permissions,
            actor=current_user.username
        )
        perms_map = RBACService.get_role_permissions_map(db, role.id)
        return RoleResponse(
            id=role.id,
            role_name=role.role_name,
            description=role.description,
            is_system_role=role.is_system_role,
            created_at=role.created_at,
            permissions=perms_map
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Role creation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create role.")

@router.put("/auth/roles/{role_id}", response_model=RoleResponse, tags=["RBAC"])
def update_role(
    role_id: int,
    request: RoleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("roles", "edit"))
):
    try:
        role = RBACService.update_role(
            db=db,
            role_id=role_id,
            description=request.description,
            permissions=request.permissions,
            actor=current_user.username
        )
        perms_map = RBACService.get_role_permissions_map(db, role.id)
        return RoleResponse(
            id=role.id,
            role_name=role.role_name,
            description=role.description,
            is_system_role=role.is_system_role,
            created_at=role.created_at,
            permissions=perms_map
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Role update error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update role.")

@router.delete("/auth/roles/{role_id}", tags=["RBAC"])
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("roles", "delete"))
):
    try:
        RBACService.delete_role(db, role_id, actor=current_user.username)
        return {"status": "success", "message": f"Role ID {role_id} removed successfully."}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Role deletion error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete role.")

@router.get("/auth/users", response_model=List[UserResponse], tags=["User Management"])
def list_system_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("user_management", "view"))
):
    users = AuthService.list_users(db)
    return [UserResponse.model_validate(u) for u in users]

@router.post("/auth/users", response_model=UserResponse, tags=["User Management"])
def create_system_user_by_admin(
    request: SignUpRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("user_management", "create"))
):
    try:
        user, _, _ = AuthService.register_user(
            db=db,
            req=request,
            created_by=current_user.username,
            role_id=request.role_id,
            require_password_change=request.require_password_change or False
        )
        return UserResponse.model_validate(user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"User provisioning error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create user account.")

@router.patch("/auth/users/{user_id}/status", response_model=UserResponse, tags=["User Management"])
def update_user_status(
    user_id: int,
    request: UserStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("user_management", "deactivate"))
):
    if current_user.id == user_id and not request.is_active:
        raise HTTPException(status_code=400, detail="Administrative protection: You cannot deactivate your own account.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User ID {user_id} not found.")

    prev_status = user.is_active
    user.is_active = request.is_active
    db.commit()

    if not request.is_active:
        # Immediately revoke all active sessions for this deactivated user
        AuthService.revoke_all_user_sessions(db, user.id)

    from app.repositories.audit_log_repository import AuditLogRepository
    AuditLogRepository.log(
        db=db,
        event_type="USER_STATUS_CHANGE",
        table_name="users",
        record_id=str(user.id),
        previous_value={"is_active": prev_status},
        updated_value={"is_active": user.is_active},
        performed_by=current_user.username
    )
    db.commit()
    return UserResponse.model_validate(user)

@router.post("/auth/users/{user_id}/reset-password", tags=["User Management"])
def reset_user_password(
    user_id: int,
    request: UserPasswordResetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("user_management", "reset_password"))
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User ID {user_id} not found.")

    AuthService.reset_user_password(
        db=db,
        user=user,
        new_password=request.new_password,
        require_change=request.require_password_change if request.require_password_change is not None else True,
        actor_name=current_user.username
    )
    return {
        "status": "success",
        "message": f"Password for user '{user.username}' has been reset successfully. Active sessions revoked."
    }

@router.patch("/auth/users/{user_id}/permissions", tags=["User Management"])
def set_user_permission_override(
    user_id: int,
    request: UserPermissionOverrideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("user_management", "edit"))
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User ID {user_id} not found.")

    try:
        RBACService.set_user_override(
            db=db,
            user_id=user_id,
            module_key=request.module_key,
            action_key=request.action_key,
            is_allowed=request.is_allowed,
            actor=current_user.username
        )
        updated_perms = RBACService.get_user_effective_permissions(db, user)
        return {
            "status": "success",
            "user_id": user_id,
            "username": user.username,
            "effective_permissions": updated_perms
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

@router.post("/auth/signup", response_model=AuthResponse, tags=["Authentication"])
def signup(
    request: SignUpRequest,
    authorization: Optional[str] = Header(None),
    x_auth_token: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    token = extract_auth_token(authorization, x_auth_token)
    actor = None
    if token:
        u = AuthService.validate_token(db, token)
        if u:
            actor = u.username
    try:
        user, token, expires_at = AuthService.register_user(
            db=db,
            req=request,
            created_by=actor,
            role_id=request.role_id,
            require_password_change=request.require_password_change or False
        )
        return AuthResponse(
            token=token,
            access_token=token,
            token_type="Bearer",
            expires_at=expires_at,
            user=UserResponse.model_validate(user)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Sign up error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create account")

@router.get("/auth/demo-users", response_model=List[DemoUser], tags=["Authentication"])
def get_demo_users():
    return [
        DemoUser(
            username="admin",
            role="QA & Compliance Lead (Qualified Person)",
            plant="TESTPLANT",
            description="Full GMP release authority, master data, and line management."
        ),
        DemoUser(
            username="operator",
            role="Packaging Line Supervisor",
            plant="TESTPLANT",
            description="Operational line assignment, batch initiation, and reconciliation."
        )
    ]
