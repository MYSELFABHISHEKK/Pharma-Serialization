import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture
def setup_l3_test_product():
    payload = {
        "product_id": "L3-TEST-PROD",
        "name": "L3 Oncology Vial 100mg",
        "gtin": "99012345678901",
        "status": "ACTIVE",
        "profile": {
            "length": 15,
            "allow_duplicate_characters": False
        }
    }
    res = client.post("/api/v1/products", json=payload)
    return res.json()

def test_packaging_lines_flow():
    # 1. List pre-seeded lines
    res = client.get("/api/v1/lines")
    assert res.status_code == 200
    lines = res.json()
    assert len(lines) >= 3
    assert any(l["name"] == "Blister Line 1" for l in lines)

    # 2. Create custom line
    custom_line = {
        "line_id": "LINE-99",
        "name": "High Speed Serialization Line 99",
        "plant": "TESTPLANT",
        "io_protocol": "SHARED_FOLDER",
        "shared_folder_path": "l2_io/shared_folder/line_99",
        "is_active": True
    }
    res_c = client.post("/api/v1/lines", json=custom_line)
    assert res_c.status_code == 200
    assert res_c.json()["line_id"] == "LINE-99"

def test_code_pool_import_and_stats():
    import_payload = {
        "gtin": "99012345678901",
        "packaging_tier": "Primary",
        "serials": ["SGTIN-POOLA-001", "SGTIN-POOLA-002", "SGTIN-POOLA-003"]
    }
    res = client.post("/api/v1/code-pool/import", json=import_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["imported_count"] == 3

    # Check stats
    res_stats = client.get("/api/v1/code-pool/stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert stats["total_codes"] >= 3
    assert stats["available_codes"] >= 3

def test_multi_tier_ratio_and_lifecycle_flow(setup_l3_test_product):
    # Register GTINs with limits
    gtin_pri = {
        "manufacturer": "TEST PHARMA",
        "plant": "TESTPLANT",
        "packaging_level": "Primary",
        "product_id": "L3-TEST-PROD",
        "product_code": "L3-TEST-PROD",
        "packing_size": "10x10 Tablets",
        "gtin": "99012345678901",
        "enable_gtin": True,
        "case_quantity": 50,
        "limit": 10000,
        "code_length": 20,
        "serial_no_type": "SGTIN",
        "packaging_category": "Primary"
    }
    client.post("/api/v1/gtin-store", json=gtin_pri)

    # Create Batch with multi-tier ratios: Q_pri = 10, R_sec = 2, R_ter = 2
    # Expected: Q_sec = 10/2 = 5, Q_ter = 5/2 = 3. Total = 10 + 5 + 3 = 18.
    batch_payload = {
        "manufacturer": "TEST PHARMA",
        "plant": "TESTPLANT",
        "packaging_level": "Primary",
        "product_id": "L3-TEST-PROD",
        "packaging_size": "10x10 Tablets",
        "work_order_no": "WO-L3-001",
        "batch_lot": "LOT-L3-100",
        "gtin": "99012345678901",
        "mfg_date": "07/10/2026",
        "expiry_date": "291007",
        "quantity": 10,
        "is_enabled": True,
        "package_aggregation": True,
        "parent_code_required": True,
        "aggregated_batch": True,
        "idempotency_key": "IDEM-L3-MULTI-1",
        "line_id": "LINE-01",
        "secondary_ratio": 2,
        "tertiary_ratio": 2,
        "io_channel": "SHARED_FOLDER"
    }
    res_b = client.post("/api/v1/batches", json=batch_payload)
    assert res_b.status_code == 200
    b_data = res_b.json()
    batch_id = b_data["batch_id"]

    assert b_data["primary_quantity"] == 10
    assert b_data["secondary_quantity"] == 5
    assert b_data["tertiary_quantity"] == 3
    assert b_data["generated_quantity"] == 18

    # 1. Load Batch
    res_load = client.post(f"/api/v1/batches/{batch_id}/load")
    assert res_load.status_code == 200
    assert res_load.json()["status"] == "LOADED"
    assert res_load.json()["total_records_transmitted"] == 18

    # 2. Start Batch
    res_start = client.post(f"/api/v1/batches/{batch_id}/start")
    assert res_start.status_code == 200
    assert res_start.json()["status"] == "STARTED"

    # 3. Reconcile Batch (Simulate 95% yield)
    reconcile_req = {
        "auto_simulate": True,
        "simulated_yield_pct": 95.0
    }
    res_rec = client.post(f"/api/v1/batches/{batch_id}/reconcile", json=reconcile_req)
    assert res_rec.status_code == 200
    rec_data = res_rec.json()
    assert rec_data["status"] == "RECONCILED"
    assert rec_data["reconciled_good_count"] > 0
    assert rec_data["yield_percentage"] > 0.0

    # 4. Close Batch
    res_close = client.post(f"/api/v1/batches/{batch_id}/close")
    assert res_close.status_code == 200
    close_data = res_close.json()
    assert close_data["status"] == "CLOSED"
    assert close_data["is_locked"] is True

    # 5. Regulatory XML Report
    res_xml = client.get(f"/api/v1/batches/{batch_id}/xml-report")
    assert res_xml.status_code == 200
    assert "application/xml" in res_xml.headers["content-type"]
    xml_text = res_xml.text
    assert "<epcis:EPCISDocument" in xml_text
    assert f"<cbvmda:lotNumber>{b_data['batch_lot']}</cbvmda:lotNumber>" in xml_text
    assert "urn:epc:id:sgtin:99012345678901." in xml_text

    # 6. Batch Summary
    res_sum = client.get(f"/api/v1/batches/{batch_id}/summary")
    assert res_sum.status_code == 200
    sum_data = res_sum.json()
    assert sum_data["batch_id"] == batch_id
    assert sum_data["status"] == "CLOSED"
    assert sum_data["is_locked"] is True
    assert sum_data["primary_quantity"] == 10
    assert sum_data["secondary_quantity"] == 5
    assert sum_data["tertiary_quantity"] == 3

    # 7. Reports Batch Summary Endpoint
    res_rep = client.get("/api/v1/reports/batch-summary")
    assert res_rep.status_code == 200
    rep_list = res_rep.json()
    assert len(rep_list) >= 1
    matched = next((item for item in rep_list if item["batch_id"] == batch_id), None)
    assert matched is not None
    assert matched["is_locked"] is True
    assert matched["total_generated"] == 18

def test_line_io_update_and_connectivity():
    # 1. Fetch single line
    res_get = client.get("/api/v1/lines/LINE-01")
    assert res_get.status_code == 200
    assert res_get.json()["line_id"] == "LINE-01"

    # 2. Update line I/O parameters
    update_payload = {
        "io_protocol": "SHARED_FOLDER",
        "shared_folder_path": "l2_io/shared_folder/line_01/outbound"
    }
    res_put = client.put("/api/v1/lines/LINE-01", json=update_payload)
    assert res_put.status_code == 200
    assert res_put.json()["io_protocol"] == "SHARED_FOLDER"
    assert res_put.json()["shared_folder_path"] == "l2_io/shared_folder/line_01/outbound"

    # 3. Test I/O connectivity route
    res_test = client.post("/api/v1/lines/LINE-01/test-io")
    assert res_test.status_code == 200
    test_data = res_test.json()
    assert test_data["status"] == "success"
    assert "SHARED_FOLDER" in test_data["io_protocol"]
    assert test_data["details"]["folder_accessible"] is True

