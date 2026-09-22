from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

class SerializationProfile(BaseModel):
    length: int = Field(default=20, ge=4, le=30)
    alphabet: str = Field(default="23456789ABCDEFGHJKMNPQRSTVWXYZ")
    require_alpha: bool = Field(default=True)
    require_numeric: bool = Field(default=True)
    allow_duplicate_characters: bool = Field(default=False)

class ProductBase(BaseModel):
    product_id: str = Field(..., min_length=2, max_length=50, description="Product identifier, e.g. ATOR-20")
    name: str = Field(..., min_length=2, max_length=100) # Product Name 1
    gtin: str = Field(..., min_length=14, max_length=14, pattern=r"^\d{14}$", description="14-digit Global Trade Item Number")
    status: str = Field(default="ACTIVE")
    profile: SerializationProfile = Field(default_factory=SerializationProfile)

    # Added Product Master properties
    regulatory_authority: Optional[str] = None
    code_provider: Optional[str] = None
    manufacturer: Optional[str] = None
    plant: Optional[str] = None
    marketing_level: Optional[str] = None
    product_code: Optional[str] = None
    product_name_2: Optional[str] = None
    product_name_3: Optional[str] = None
    stk: Optional[str] = None
    manufactured_by: Optional[str] = None
    distributed_by: Optional[str] = None
    storage_condition: Optional[str] = None
    license: Optional[str] = None
    generic_name: Optional[str] = None
    composition: Optional[str] = None
    usage_dose: Optional[str] = None
    remark: Optional[str] = None
    product_image: Optional[str] = None # base64 representation
    unit_price: Optional[str] = None
    ndc: Optional[str] = None
    ndc_type: Optional[str] = None
    country_drug_code_type: Optional[str] = None
    country_drug_code: Optional[str] = None
    internal_material_number: Optional[str] = None
    nnhrn: Optional[str] = None
    nhrn_ai_type: Optional[str] = None
    item_code_type: Optional[str] = None
    item_code: Optional[str] = None
    is_active: bool = True
    additional_field_1: Optional[str] = None
    additional_field_2: Optional[str] = None

class ProductCreate(ProductBase):
    pass

class ProductResponse(ProductBase):
    created_at: str
    model_config = ConfigDict(from_attributes=True)
