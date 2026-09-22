from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import text
from app.api.endpoints import router as api_router
from app.core.database import Base, engine
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
        '''))
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
