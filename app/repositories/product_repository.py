from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.db_models import Product
from app.models.product import ProductCreate
from app.repositories.audit_log_repository import AuditLogRepository

class ProductRepository:
    @staticmethod
    def get_by_id(db: Session, product_id: str) -> Optional[Product]:
        if not product_id:
            return None
        prod = db.query(Product).filter(Product.product_id == product_id).first()
        if not prod:
            prod = db.query(Product).filter(Product.product_code == product_id).first()
        if not prod:
            prod = db.query(Product).filter(Product.name.ilike(product_id)).first()
        if not prod:
            prod = db.query(Product).filter(Product.gtin == product_id).first()
        return prod

    @staticmethod
    def get_by_gtin(db: Session, gtin: str) -> Optional[Product]:
        return db.query(Product).filter(Product.gtin == gtin).first()

    @staticmethod
    def serialize_product(p: Product) -> dict:
        return {
            "product_id": p.product_id,
            "name": p.name,
            "gtin": p.gtin,
            "status": p.status,
            "profile_len": p.profile_len,
            "profile_alphabet": p.profile_alphabet,
            "profile_require_alpha": p.profile_require_alpha,
            "profile_require_numeric": p.profile_require_numeric,
            "profile_allow_duplicate_chars": p.profile_allow_duplicate_chars,
            "regulatory_authority": p.regulatory_authority,
            "code_provider": p.code_provider,
            "manufacturer": p.manufacturer,
            "plant": p.plant,
            "marketing_level": p.marketing_level,
            "product_code": p.product_code,
            "product_name_2": p.product_name_2,
            "product_name_3": p.product_name_3,
            "stk": p.stk,
            "manufactured_by": p.manufactured_by,
            "distributed_by": p.distributed_by,
            "storage_condition": p.storage_condition,
            "license": p.license,
            "generic_name": p.generic_name,
            "composition": p.composition,
            "usage_dose": p.usage_dose,
            "remark": p.remark,
            "product_image": p.product_image,
            "unit_price": p.unit_price,
            "ndc": p.ndc,
            "ndc_type": p.ndc_type,
            "country_drug_code_type": p.country_drug_code_type,
            "country_drug_code": p.country_drug_code,
            "internal_material_number": p.internal_material_number,
            "nnhrn": p.nnhrn,
            "nhrn_ai_type": p.nhrn_ai_type,
            "item_code_type": p.item_code_type,
            "item_code": p.item_code,
            "is_active": p.is_active,
            "additional_field_1": p.additional_field_1,
            "additional_field_2": p.additional_field_2,
        }

    @staticmethod
    def create(db: Session, product: ProductCreate) -> Product:
        db_product = Product(
            product_id=product.product_id,
            name=product.name,
            gtin=product.gtin,
            status=product.status,
            profile_len=product.profile.length,
            profile_alphabet=product.profile.alphabet,
            profile_require_alpha=product.profile.require_alpha,
            profile_require_numeric=product.profile.require_numeric,
            profile_allow_duplicate_chars=product.profile.allow_duplicate_characters,
            created_at=datetime.now(timezone.utc).isoformat(),
            regulatory_authority=product.regulatory_authority,
            code_provider=product.code_provider,
            manufacturer=product.manufacturer,
            plant=product.plant,
            marketing_level=product.marketing_level,
            product_code=product.product_code,
            product_name_2=product.product_name_2,
            product_name_3=product.product_name_3,
            stk=product.stk,
            manufactured_by=product.manufactured_by,
            distributed_by=product.distributed_by,
            storage_condition=product.storage_condition,
            license=product.license,
            generic_name=product.generic_name,
            composition=product.composition,
            usage_dose=product.usage_dose,
            remark=product.remark,
            product_image=product.product_image,
            unit_price=product.unit_price,
            ndc=product.ndc,
            ndc_type=product.ndc_type,
            country_drug_code_type=product.country_drug_code_type,
            country_drug_code=product.country_drug_code,
            internal_material_number=product.internal_material_number,
            nnhrn=product.nnhrn,
            nhrn_ai_type=product.nhrn_ai_type,
            item_code_type=product.item_code_type,
            item_code=product.item_code,
            is_active=product.is_active,
            additional_field_1=product.additional_field_1,
            additional_field_2=product.additional_field_2
        )
        db.add(db_product)
        db.commit()
        db.refresh(db_product)

        # Log creation
        AuditLogRepository.log(
            db,
            event_type="CREATE_PRODUCT",
            table_name="products",
            record_id=db_product.product_id,
            previous_value=None,
            updated_value=ProductRepository.serialize_product(db_product)
        )
        db.commit()

        return db_product

    @staticmethod
    def update(db: Session, product_id: str, product: ProductCreate) -> Optional[Product]:
        db_product = ProductRepository.get_by_id(db, product_id)
        if not db_product:
            return None

        prev_val = ProductRepository.serialize_product(db_product)

        # Update properties
        db_product.name = product.name
        db_product.gtin = product.gtin
        db_product.status = product.status
        db_product.profile_len = product.profile.length
        db_product.profile_alphabet = product.profile.alphabet
        db_product.profile_require_alpha = product.profile.require_alpha
        db_product.profile_require_numeric = product.profile.require_numeric
        db_product.profile_allow_duplicate_chars = product.profile.allow_duplicate_characters
        
        db_product.regulatory_authority = product.regulatory_authority
        db_product.code_provider = product.code_provider
        db_product.manufacturer = product.manufacturer
        db_product.plant = product.plant
        db_product.marketing_level = product.marketing_level
        db_product.product_code = product.product_code
        db_product.product_name_2 = product.product_name_2
        db_product.product_name_3 = product.product_name_3
        db_product.stk = product.stk
        db_product.manufactured_by = product.manufactured_by
        db_product.distributed_by = product.distributed_by
        db_product.storage_condition = product.storage_condition
        db_product.license = product.license
        db_product.generic_name = product.generic_name
        db_product.composition = product.composition
        db_product.usage_dose = product.usage_dose
        db_product.remark = product.remark
        db_product.product_image = product.product_image
        db_product.unit_price = product.unit_price
        db_product.ndc = product.ndc
        db_product.ndc_type = product.ndc_type
        db_product.country_drug_code_type = product.country_drug_code_type
        db_product.country_drug_code = product.country_drug_code
        db_product.internal_material_number = product.internal_material_number
        db_product.nnhrn = product.nnhrn
        db_product.nhrn_ai_type = product.nhrn_ai_type
        db_product.item_code_type = product.item_code_type
        db_product.item_code = product.item_code
        db_product.is_active = product.is_active
        db_product.additional_field_1 = product.additional_field_1
        db_product.additional_field_2 = product.additional_field_2

        db.commit()
        db.refresh(db_product)

        new_val = ProductRepository.serialize_product(db_product)

        # Log change
        AuditLogRepository.log(
            db,
            event_type="UPDATE_PRODUCT",
            table_name="products",
            record_id=db_product.product_id,
            previous_value=prev_val,
            updated_value=new_val
        )
        db.commit()

        return db_product

    @staticmethod
    def list_all(db: Session) -> List[Product]:
        return db.query(Product).all()
