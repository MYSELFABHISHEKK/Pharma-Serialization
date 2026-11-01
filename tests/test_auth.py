import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.auth_service import AuthService
from app.models.db_models import User, UserSession, AuditLog

client = TestClient(app)

def test_demo_users_endpoint():
    response = client.get("/api/v1/auth/demo-users")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    usernames = [u["username"] for u in data]
    assert "admin" in usernames
    assert "operator" in usernames

def test_auth_lifecycle(db_session):
    # 1. Seed default users
    AuthService.seed_default_users(db_session)

    # 2. Test login with seeded admin
    login_payload = {
        "username": "admin",
        "password": "Admin@1234"
    }
    resp = client.post("/api/v1/auth/login", json=login_payload)
    assert resp.status_code == 200
    login_data = resp.json()
    assert "access_token" in login_data
    assert login_data["user"]["username"] == "admin"
    assert "Qualified Person" in login_data["user"]["role"]
    token = login_data["access_token"]

    # 3. Test /auth/me with Bearer token
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["username"] == "admin"
    assert me_data["plant"] == "TESTPLANT"

    # 4. Test login with bad password
    bad_resp = client.post("/api/v1/auth/login", json={
        "username": "admin",
        "password": "WrongPassword!"
    })
    assert bad_resp.status_code == 401

    # 5. Test sign up new QA user
    signup_payload = {
        "username": "auditor_elena",
        "email": "elena.r@pharma-corp.local",
        "full_name": "Elena Rostova",
        "password": "SecretPassword123!",
        "role": "Regulatory Affairs Specialist",
        "plant": "TESTPLANT_DGFT"
    }
    signup_resp = client.post("/api/v1/auth/signup", json=signup_payload)
    assert signup_resp.status_code == 200
    signup_data = signup_resp.json()
    assert signup_data["user"]["username"] == "auditor_elena"
    assert signup_data["user"]["plant"] == "TESTPLANT_DGFT"
    elena_token = signup_data["access_token"]

    # Test duplicate username signup fails
    dup_resp = client.post("/api/v1/auth/signup", json=signup_payload)
    assert dup_resp.status_code == 400
    assert "already registered" in dup_resp.json()["detail"]

    # 6. Test logout
    logout_resp = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {elena_token}"}
    )
    assert logout_resp.status_code == 200

    # 7. Verification: token revoked
    revoked_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {elena_token}"}
    )
    assert revoked_resp.status_code == 401

    # 8. Check 21 CFR Part 11 Audit Trail Entries
    audit_events = db_session.query(AuditLog.event_type).all()
    event_names = [e[0] for e in audit_events]
    assert "USER_LOGIN" in event_names
    assert "USER_SIGNUP" in event_names
    assert "USER_LOGOUT" in event_names

def test_admin_user_provisioning_flow(db_session):
    AuthService.seed_default_users(db_session)
    
    # 1. Admin logs in
    admin_login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@1234"})
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]
    
    # 2. Admin provisions a new operator
    new_user_payload = {
        "username": "line_supervisor_raj",
        "email": "raj.k@pharma-corp.local",
        "full_name": "Rajesh Kumar",
        "password": "RajeshPassword@123",
        "role": "Packaging Line Supervisor",
        "plant": "PLANT-HYDERABAD-01"
    }
    create_resp = client.post(
        "/api/v1/auth/users",
        json=new_user_payload,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert create_resp.status_code == 200
    created_user = create_resp.json()
    assert created_user["username"] == "line_supervisor_raj"
    assert created_user["full_name"] == "Rajesh Kumar"
    
    # 3. Verify user is in list
    users_resp = client.get("/api/v1/auth/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert users_resp.status_code == 200
    users_list = users_resp.json()
    assert any(u["username"] == "line_supervisor_raj" for u in users_list)
    
    # 4. New user logs in using provisioned credentials
    raj_login = client.post("/api/v1/auth/login", json={
        "username": "line_supervisor_raj",
        "password": "RajeshPassword@123"
    })
    assert raj_login.status_code == 200
    assert raj_login.json()["user"]["username"] == "line_supervisor_raj"
    assert "access_token" in raj_login.json()
