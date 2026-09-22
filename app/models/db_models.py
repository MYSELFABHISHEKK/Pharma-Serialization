from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, JSON, DateTime, UniqueConstraint
from app.core.database import Base

class Product(Base):
    __tablename__ = "products"

    product_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False) # Maps to Product Name 1
    gtin = Column(String(14), unique=True, index=True, nullable=False)
    status = Column(String, default="ACTIVE")
    
    # Flat columns for serialization profile settings
    profile_len = Column(Integer, default=20)
    profile_alphabet = Column(String, default="23456789ABCDEFGHJKMNPQRSTVWXYZ")
    profile_require_alpha = Column(Boolean, default=True)
    profile_require_numeric = Column(Boolean, default=True)
    profile_allow_duplicate_chars = Column(Boolean, default=True)
    created_at = Column(String, nullable=False)

    # Added columns for Product Master
    regulatory_authority = Column(String, nullable=True)
    code_provider = Column(String, nullable=True)
    manufacturer = Column(String, nullable=True)
    plant = Column(String, nullable=True)
    marketing_level = Column(String, nullable=True)
    product_code = Column(String, nullable=True)
    product_name_2 = Column(String, nullable=True)
    product_name_3 = Column(String, nullable=True)
    stk = Column(String, nullable=True)
    manufactured_by = Column(String, nullable=True)
    distributed_by = Column(String, nullable=True)
    storage_condition = Column(String, nullable=True)
    license = Column(String, nullable=True)
    generic_name = Column(String, nullable=True)
    composition = Column(String, nullable=True)
    usage_dose = Column(String, nullable=True)
    remark = Column(String, nullable=True)
    product_image = Column(String, nullable=True) # base64 string
    unit_price = Column(String, nullable=True)
    ndc = Column(String, nullable=True)
    ndc_type = Column(String, nullable=True)
    country_drug_code_type = Column(String, nullable=True)
    country_drug_code = Column(String, nullable=True)
    internal_material_number = Column(String, nullable=True)
    nnhrn = Column(String, nullable=True)
    nhrn_ai_type = Column(String, nullable=True)
    item_code_type = Column(String, nullable=True)
    item_code = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    additional_field_1 = Column(String, nullable=True)
    additional_field_2 = Column(String, nullable=True)

    @property
    def profile(self):
        return {
            "length": self.profile_len,
            "alphabet": self.profile_alphabet,
            "require_alpha": self.profile_require_alpha,
            "require_numeric": self.profile_require_numeric,
            "allow_duplicate_characters": self.profile_allow_duplicate_chars
        }

class Batch(Base):
    __tablename__ = "batches"

    batch_id = Column(String, primary_key=True, index=True)
    product_id = Column(String, ForeignKey("products.product_id"), nullable=False)
    requested_quantity = Column(Integer, nullable=False)
    generated_quantity = Column(Integer, default=0)
    start_sequence = Column(Integer, nullable=False)
    end_sequence = Column(Integer, nullable=False)
    batch_lot = Column(String, nullable=False) # Mapped to Batch Number
    expiry_date = Column(String(6), nullable=False) # YYMMDD
    status = Column(String, default="PROCESSING")
    created_at = Column(String, nullable=False)

    # Added columns for Batch Master
    manufacturer = Column(String, nullable=True)
    plant = Column(String, nullable=True)
    packaging_level = Column(String, nullable=True)
    packaging_size = Column(String, nullable=True)
    work_order_no = Column(String, nullable=True)
    mfg_date = Column(String, nullable=True) # YYMMDD or DD/MM/YYYY
    is_enabled = Column(Boolean, default=True)
    package_aggregation = Column(Boolean, default=False)
    parent_code_required = Column(Boolean, default=False)
    aggregated_batch = Column(Boolean, default=False)

class Serial(Base):
    __tablename__ = "serials"

    serial_number = Column(String(30), primary_key=True, index=True)
    sequence_number = Column(Integer, nullable=False)
    product_id = Column(String, ForeignKey("products.product_id"), nullable=False)
    batch_id = Column(String, ForeignKey("batches.batch_id"), nullable=False)
    batch_lot = Column(String, nullable=False)
    expiry_date = Column(String(6), nullable=False)
    status = Column(String, default="GENERATED")
    created_at = Column(String, nullable=False)
    history = Column(JSON, default=list)

    __table_args__ = (
        UniqueConstraint('product_id', 'sequence_number', name='_product_sequence_uc'),
    )

class ProductSequence(Base):
    __tablename__ = "product_sequences"

    product_id = Column(String, primary_key=True)
    next_sequence = Column(Integer, default=1, nullable=False)

class SGTINCode(Base):
    __tablename__ = "sgtin_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sequence = Column(Integer, nullable=False)
    gtin = Column(String(14), nullable=False)
    serial_number = Column(String(20), unique=True, index=True, nullable=False)
    sgtin = Column(String(34), nullable=False)
    created_at = Column(String, nullable=False)

class Idempotency(Base):
    __tablename__ = "idempotency"

    idempotency_key = Column(String, primary_key=True, index=True)
    batch_id = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)

class GTINStore(Base):
    __tablename__ = "gtin_store"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manufacturer = Column(String, nullable=False)
    plant = Column(String, nullable=False)
    packaging_level = Column(String, nullable=False)
    product_id = Column(String, ForeignKey("products.product_id"), nullable=False)
    product_code = Column(String, nullable=False)
    packing_size = Column(String, nullable=False)
    gtin = Column(String(14), unique=True, index=True, nullable=False)
    enable_gtin = Column(Boolean, default=True)
    case_quantity = Column(Integer, nullable=True)
    limit = Column(Integer, nullable=False)
    code_length = Column(Integer, nullable=False)
    serial_no_type = Column(String, default="SGTIN", nullable=True)
    packaging_category = Column(String, default="Primary", nullable=True)
    created_at = Column(String, nullable=False)

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String, nullable=False)
    table_name = Column(String, nullable=False)
    record_id = Column(String, nullable=False)
    previous_value = Column(String, nullable=True) # JSON String
    updated_value = Column(String, nullable=True) # JSON String
    performed_by = Column(String, default="system")
    timestamp = Column(String, nullable=False)
