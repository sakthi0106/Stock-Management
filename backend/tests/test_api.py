import pytest
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from sync_service import SyncService

@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_api_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"
    assert "mode" in data

def test_api_sheets(client):
    res = client.get("/api/sheets")
    assert res.status_code == 200
    data = res.get_json()
    assert "sheets" in data
    assert len(data["sheets"]) > 0

def test_api_inventory_strict_amount_exclusion(client):
    res = client.get("/api/inventory")
    assert res.status_code == 200
    data = res.get_json()
    assert "items" in data
    assert len(data["items"]) > 0

    for item in data["items"]:
        # Verify NO amount column leaks to frontend
        assert "amount" not in item
        assert "Amount" not in item
        for k in item.keys():
            assert "amount" not in k.lower()

def test_api_special_literals_preserved(client):
    from inventory_service import parse_num_or_preserve
    assert parse_num_or_preserve('NA') == 'NA'
    assert parse_num_or_preserve('-') == '-'
    assert parse_num_or_preserve('150.50') == 150.5

def test_api_dashboard(client):
    res = client.get("/api/dashboard")
    assert res.status_code == 200
    data = res.get_json()
    assert "total_products" in data
    assert "uom_quantities" in data
    assert "daily_trends" in data

def test_sync_service_loads_local_snapshot_without_remote_requests():
    class RemoteClient:
        def is_configured(self):
            return True

        def get_spreadsheet_metadata(self):
            raise AssertionError("Remote metadata should load in the background")

        def get_batch_sheet_values(self, _sheet_names):
            raise AssertionError("Remote values should load in the background")

        def get_batch_sheet_formulas(self, _sheet_names):
            raise AssertionError("Remote formulas should load in the background")

    service = SyncService(RemoteClient())

    assert service.get_service() is not None
    assert service.get_service().products
    assert service.get_status()["lastSuccess"] is None
