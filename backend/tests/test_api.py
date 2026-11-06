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

def test_api_inventory_strict_amount_exclusion(client):
    import database
    from inventory_service import InventoryService
    # Test strict amount exclusion on simulated product dictionary
    raw_item = {
        "product_id": "P1",
        "description": "Item",
        "extra_fields": {"Total Cost": 100, "Normal Field": "Value", "Amount": 500}
    }
    from routes import is_amount_field
    clean_extra = {k: v for k, v in raw_item["extra_fields"].items() if not is_amount_field(k)}
    assert "Amount" not in clean_extra
    assert "Total Cost" not in clean_extra
    assert "Normal Field" in clean_extra

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
            return False

        def get_spreadsheet_metadata(self):
            raise AssertionError("Remote metadata should not be called")

    service = SyncService(RemoteClient())
    assert service.get_service() is not None
    assert service.get_status()["lastSuccess"] is None
