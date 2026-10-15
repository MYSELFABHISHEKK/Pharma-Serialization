from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import text
from app.api.endpoints import router as api_router
from app.core.database import Base, engine, SessionLocal
from app.models import db_models

# Configure system logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bt_sn_portal")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create all relational database tables (DDL)
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text('''
            ALTER TABLE products ADD COLUMN IF NOT EXISTS regulatory_authority VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS code_provider VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS manufacturer VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS plant VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS marketing_level VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS product_code VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS product_name_2 VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS product_name_3 VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS stk VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS manufactured_by VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS distributed_by VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS storage_condition VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS license VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS generic_name VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS composition VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS usage_dose VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS remark VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS product_image TEXT;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS unit_price VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS ndc VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS ndc_type VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS country_drug_code_type VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS country_drug_code VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS internal_material_number VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS nnhrn VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS nhrn_ai_type VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS item_code_type VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS item_code VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS additional_field_1 VARCHAR;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS additional_field_2 VARCHAR;

            ALTER TABLE batches ADD COLUMN IF NOT EXISTS manufacturer VARCHAR;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS plant VARCHAR;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS packaging_level VARCHAR;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS packaging_size VARCHAR;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS work_order_no VARCHAR;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS mfg_date VARCHAR;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS is_enabled BOOLEAN DEFAULT TRUE;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS package_aggregation BOOLEAN DEFAULT FALSE;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS parent_code_required BOOLEAN DEFAULT FALSE;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS aggregated_batch BOOLEAN DEFAULT FALSE;

            ALTER TABLE gtin_store ADD COLUMN IF NOT EXISTS serial_no_type VARCHAR DEFAULT 'SGTIN';
            ALTER TABLE gtin_store ADD COLUMN IF NOT EXISTS packaging_category VARCHAR DEFAULT 'Primary';

            ALTER TABLE batches ADD COLUMN IF NOT EXISTS line_id VARCHAR;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS secondary_ratio INTEGER DEFAULT 1;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS tertiary_ratio INTEGER DEFAULT 1;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS primary_quantity INTEGER DEFAULT 0;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS secondary_quantity INTEGER DEFAULT 0;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS tertiary_quantity INTEGER DEFAULT 0;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS reconciled_good_count INTEGER DEFAULT 0;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS reconciled_rejected_count INTEGER DEFAULT 0;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS reconciled_unused_count INTEGER DEFAULT 0;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS yield_percentage FLOAT DEFAULT 0.0;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS is_locked BOOLEAN DEFAULT FALSE;
            ALTER TABLE batches ADD COLUMN IF NOT EXISTS io_channel VARCHAR DEFAULT 'DIRECT_API';

            ALTER TABLE serials ADD COLUMN IF NOT EXISTS packaging_tier VARCHAR DEFAULT 'Primary';
        '''))

    # Seed default lines if none exist
    from app.models.db_models import PackagingLine
    db = SessionLocal()
    try:
        line_count = db.query(PackagingLine).count()
        if line_count == 0:
            default_lines = [
                PackagingLine(
                    line_id="LINE-01",
                    name="Blister Line 1",
                    plant="TESTPLANT",
                    io_protocol="DIRECT_API",
                    api_endpoint="http://127.0.0.1:8000/api/v1/l2/mock-controller/line-01",
                    shared_folder_path="l2_io/shared_folder/line_01",
                    sftp_host="sftp.pharma.local",
                    sftp_port=22,
                    sftp_user="line01_op",
                    sftp_drop_folder="/var/drop/line_01/outbound",
                    sftp_inbound_folder="/var/drop/line_01/inbound",
                    is_active=True,
                    created_at="2026-01-01T00:00:00Z"
                ),
                PackagingLine(
                    line_id="LINE-02",
                    name="Bottle Line 2",
                    plant="TESTPLANT",
                    io_protocol="SHARED_FOLDER",
                    shared_folder_path="l2_io/shared_folder/line_02",
                    sftp_host="sftp.pharma.local",
                    sftp_port=22,
                    sftp_user="line02_op",
                    sftp_drop_folder="/var/drop/line_02/outbound",
                    sftp_inbound_folder="/var/drop/line_02/inbound",
                    is_active=True,
                    created_at="2026-01-01T00:00:00Z"
                ),
                PackagingLine(
                    line_id="LINE-03",
                    name="Packaging Line 01",
                    plant="TESTPLANT_DGFT",
                    io_protocol="SFTP",
                    shared_folder_path="l2_io/shared_folder/line_03",
                    sftp_host="sftp.pharma.local",
                    sftp_port=22,
                    sftp_user="line03_op",
                    sftp_drop_folder="/var/drop/line_03/outbound",
                    sftp_inbound_folder="/var/drop/line_03/inbound",
                    is_active=True,
                    created_at="2026-01-01T00:00:00Z"
                )
            ]
            db.add_all(default_lines)
        # Seed default users if none exist
        from app.services.auth_service import AuthService
        AuthService.seed_default_users(db)
    finally:
        db.close()
    logger.info("Database tables initialized.")
    yield

app = FastAPI(
    title="BT SN Portal - Track & Trace",
    description="Product Serialization and Track-and-Trace API and Management Console",
    version="1.0",
    lifespan=lifespan
)

# Enable CORS for developer access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route to serve main UI HTML on root /
@app.get("/")
def get_portal():
    return FileResponse("app/static/index.html")

# Route to serve favicon or static folder assets
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Register API Router
app.include_router(api_router)
