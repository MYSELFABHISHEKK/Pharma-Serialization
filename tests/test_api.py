import pytest
import csv
import io
from fastapi.testclient import TestClient
from app.main import app
from app.models.db_models import SGTINCode

client = TestClient(app)

@pytest.fixture
def register_test_product():
    # Helper to register product
    payload = {
        "product_id": "TEST-PROD",
        "name": "Test Meds 50mg",
        "gtin": "12345678901234",
        "status": "ACTIVE",
        "profile": {
            "length": 15,
            "allow_duplicate_characters": False
        }
    }
    # Call endpoint
    res = client.post("/api/v1/products", json=payload)
    return res.json()

def test_create_and_list_products(register_test_product):
    # Verify product was registered
    assert register_test_product["product_id"] == "TEST-PROD"
    assert register_test_product["gtin"] == "12345678901234"
    
    # List products
    res = client.get("/api/v1/products")
    assert res.status_code == 200
    products = res.json()
    assert len(products) > 0
    assert any(p["product_id"] == "TEST-PROD" for p in products)

def test_generate_serialization_batch(register_test_product):
    payload = {
        "product_id": "TEST-PROD",
        "quantity": 10,
        "batch_lot": "LOT-999",
        "expiry_date": "301231",
        "idempotency_key": "IDEM-KEY-UNIQUE-1"
    }
    
    res = client.post("/api/v1/serialization/generate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["requested_quantity"] == 10
    assert data["generated_quantity"] == 10
    assert data["start_sequence"] == 1
    assert data["end_sequence"] == 10

    serials_res = client.get(f"/api/v1/serialization/batches/{data['batch_id']}/serials")
    assert serials_res.status_code == 200
    serials = serials_res.json()
    assert len(serials) == 10

    lookalikes = {"0", "1", "I", "L", "O", "U"}
    for index, serial_doc in enumerate(serials):
        serial_number = serial_doc["serial_number"]
        assert serial_doc["sequence_number"] == data["start_sequence"] + index
        assert len(serial_number) == 15
        assert len(set(serial_number)) == 15
        assert not set(serial_number).intersection(lookalikes)
        assert any(char.isalpha() for char in serial_number)
        assert any(char.isdigit() for char in serial_number)

def test_generate_sgtin_csv_endpoint(db_session):
    payload = {
        "gtin": "08901234567890",
        "quantity": 5,
        "start_sequence": 10
    }

    res = client.post("/api/v1/sgtin/generate-csv", json=payload)

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers["content-disposition"]

    reader = csv.DictReader(io.StringIO(res.text))
    rows = list(reader)
    assert reader.fieldnames == ["Sequence", "GTIN", "Serial Number", "SGTIN"]
    assert len(rows) == 5
    assert [int(row["Sequence"]) for row in rows] == [10, 11, 12, 13, 14]

    for row in rows:
        serial_number = row["Serial Number"]
        assert row["GTIN"] == "08901234567890"
        assert len(serial_number) == 20
        assert len(set(serial_number)) == 20
        assert not set(serial_number).intersection({"0", "1", "I", "L", "O", "U"})
        assert any(char.isalpha() for char in serial_number)
        assert any(char.isdigit() for char in serial_number)
        assert row["SGTIN"] == f"{row['GTIN']}{serial_number}"

    assert db_session.query(SGTINCode).filter(SGTINCode.gtin == "08901234567890").count() == 5

def test_idempotency_key_enforcement(register_test_product):
    payload = {
        "product_id": "TEST-PROD",
        "quantity": 5,
        "batch_lot": "LOT-ABC",
        "expiry_date": "301231",
        "idempotency_key": "SAME-KEY-123"
    }
    
    # First request
    res1 = client.post("/api/v1/serialization/generate", json=payload)
    assert res1.status_code == 200
    data1 = res1.json()
    batch_id_1 = data1["batch_id"]
    
    # Second request with the same idempotency key
    res2 = client.post("/api/v1/serialization/generate", json=payload)
    assert res2.status_code == 200
    data2 = res2.json()
    batch_id_2 = data2["batch_id"]
    
    # Batch IDs must be identical
    assert batch_id_1 == batch_id_2

def test_serial_lookup_and_status_transitions(register_test_product):
    # 1. Generate serials
    payload = {
        "product_id": "TEST-PROD",
        "quantity": 2,
        "batch_lot": "LOT-XYZ",
        "expiry_date": "291030",
        "idempotency_key": "IDEM-KEY-UNIQUE-2"
    }
    client.post("/api/v1/serialization/generate", json=payload)
    
    # 2. Get batch serial numbers
    res_batches = client.get("/api/v1/serialization/batches")
    last_batch = res_batches.json()[0]
    batch_id = last_batch["batch_id"]
    
    res_serials = client.get(f"/api/v1/serialization/batches/{batch_id}/serials")
    serials = res_serials.json()
    assert len(serials) == 2
    
    serial_number = serials[0]["serial_number"]
    
    # 3. Lookup individual serial
    res_lookup = client.get(f"/api/v1/serials/{serial_number}")
    assert res_lookup.status_code == 200
    assert res_lookup.json()["serial_number"] == serial_number
    assert res_lookup.json()["status"] == "GENERATED"
    
    # 4. Valid status transition: GENERATED -> ALLOCATED
    res_update1 = client.patch(
        f"/api/v1/serials/{serial_number}/status",
        json={"status": "ALLOCATED", "notes": "Test Allocation"}
    )
    assert res_update1.status_code == 200
    assert res_update1.json()["status"] == "ALLOCATED"
    
    # 5. Invalid status transition: ALLOCATED -> SOLD (must go through SHIPPED first)
    res_update2 = client.patch(
        f"/api/v1/serials/{serial_number}/status",
        json={"status": "SOLD", "notes": "Direct Sale Attempt"}
    )
    assert res_update2.status_code == 400
    assert "Invalid state transition" in res_update2.json()["detail"]
    
    # 6. Valid transition sequence: ALLOCATED -> SHIPPED -> SOLD
    res_update3 = client.patch(
        f"/api/v1/serials/{serial_number}/status",
        json={"status": "SHIPPED"}
    )
    assert res_update3.status_code == 200
    
    res_update4 = client.patch(
        f"/api/v1/serials/{serial_number}/status",
        json={"status": "SOLD"}
    )
    assert res_update4.status_code == 200
    assert res_update4.json()["status"] == "SOLD"

def test_create_batch_master_aggregated_batch(register_test_product):
    payload = {
        "manufacturer": "TEST PHARMA",
        "plant": "TESTPLANT",
        "packaging_level": "Secondary",
        "product_id": "TEST-PROD",
        "packaging_size": "10x10 Tablets",
        "work_order_no": "WO-AGG-001",
        "batch_lot": "BATCH-AGG-1",
        "gtin": "12345678901234",
        "mfg_date": "01/01/2026",
        "expiry_date": "281231",
        "quantity": 5,
        "is_enabled": True,
        "package_aggregation": True,
        "parent_code_required": True,
        "aggregated_batch": True,
        "idempotency_key": "IDEM-AGG-1"
    }
    res = client.post("/api/v1/batches", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["aggregated_batch"] is True
    assert data["batch_lot"] == "BATCH-AGG-1"

    # Verify lookup includes aggregated_batch
    batch_id = data["batch_id"]
    serials_res = client.get(f"/api/v1/serialization/batches/{batch_id}/serials")
    first_serial = serials_res.json()[0]["serial_number"]
    lookup_res = client.get(f"/api/v1/serials/{first_serial}")
    assert lookup_res.status_code == 200
    assert lookup_res.json()["aggregated_batch"] is True

def test_gtin_store_serial_no_type_and_packaging_category(register_test_product):
    # 1. Create SGTIN Primary GTIN
    payload_sgtin = {
        "manufacturer": "TEST PHARMA",
        "plant": "TESTPLANT",
        "packaging_level": "Primary",
        "product_id": "TEST-PROD",
        "product_code": "TEST-PROD",
        "packing_size": "10x10 Tablets",
        "gtin": "89012345678901",
        "enable_gtin": True,
        "case_quantity": 50,
        "limit": 1000,
        "code_length": 20,
        "serial_no_type": "SGTIN",
        "packaging_category": "Primary"
    }
    res_sgtin = client.post("/api/v1/gtin-store", json=payload_sgtin)
    assert res_sgtin.status_code == 200
    data_sgtin = res_sgtin.json()
    assert data_sgtin["serial_no_type"] == "SGTIN"
    assert data_sgtin["packaging_category"] == "Primary"
    gtin_id = data_sgtin["id"]

    # 2. Create SSCC Tertiary GTIN
    payload_sscc = {
        "manufacturer": "TEST PHARMA",
        "plant": "TESTPLANT",
        "packaging_level": "Tertiary",
        "product_id": "TEST-PROD",
        "product_code": "TEST-PROD",
        "packing_size": "Shipper 100",
        "gtin": "89012345678902",
        "enable_gtin": True,
        "case_quantity": 10,
        "limit": 500,
        "code_length": 20,
        "serial_no_type": "SSCC",
        "packaging_category": "Tertiary"
    }
    res_sscc = client.post("/api/v1/gtin-store", json=payload_sscc)
    assert res_sscc.status_code == 200
    data_sscc = res_sscc.json()
    assert data_sscc["serial_no_type"] == "SSCC"
    assert data_sscc["packaging_category"] == "Tertiary"

    # 3. Update GTIN store record
    payload_update = dict(payload_sgtin)
    payload_update["packing_size"] = "10x15 Tablets"
    payload_update["packaging_category"] = "Secondary"
    res_up = client.put(f"/api/v1/gtin-store/{gtin_id}", json=payload_update)
    assert res_up.status_code == 200
    assert res_up.json()["packing_size"] == "10x15 Tablets"
    assert res_up.json()["packaging_category"] == "Secondary"

    # 4. Get by product
    res_prod = client.get("/api/v1/gtin-store/product/TEST-PROD")
    assert res_prod.status_code == 200
    records = res_prod.json()
    assert len(records) >= 2
    assert any(r["serial_no_type"] == "SSCC" for r in records)
    assert any(r["serial_no_type"] == "SGTIN" for r in records)

