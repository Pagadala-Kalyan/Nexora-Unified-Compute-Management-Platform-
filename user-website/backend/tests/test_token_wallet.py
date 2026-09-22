"""Focused integration checks for Nexora's persistent token ledger."""
import os
import tempfile

with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as database:
    os.environ["DATABASE_URL"] = f"sqlite:///{database.name}"

from fastapi.testclient import TestClient
from app.main import Base, app, engine

Base.metadata.create_all(engine)
client = TestClient(app)

def test_purchase_is_persistent_and_server_owned():
    response = client.post("/auth/register", json={"email":"ledger@example.test","password":"password123"})
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/billing", headers=headers).json()["token_balance"] == 1000
    purchase = client.post("/billing/purchase", headers=headers, json={"package_id":"standard"})
    assert purchase.json()["new_balance"] == 1300
    assert client.post("/billing/purchase", headers=headers, json={"package_id":"forged","tokens":999999}).status_code == 422
    entries = client.get("/billing/transactions", headers=headers).json()
    assert [(x["type"],x["amount"]) for x in entries][:2] == [("PURCHASE",300),("ADJUSTMENT",1000)]
