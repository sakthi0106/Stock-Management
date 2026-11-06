import pytest
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
import database

@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_sources_api_crud(client):
    # 1. List initial sources (must not contain unprovided/unregistered sources)
    res = client.get("/api/sources")
    assert res.status_code == 200
    data = res.get_json()
    assert "sources" in data
    initial_count = len(data["sources"])

    # 2. Register a new source
    new_src = {
        "name": "November 2026 Test Stock",
        "spreadsheet_url_or_id": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
        "period": "2026-11",
        "description": "Test registration for November",
        "status": "active",
        "is_active": False
    }
    create_res = client.post("/api/sources", json=new_src)
    assert create_res.status_code == 201
    created_data = create_res.get_json()
    assert "source" in created_data
    created_id = created_data["source"]["source_id"]
    assert created_data["source"]["name"] == "November 2026 Test Stock"
    assert created_data["source"]["period"] == "2026-11"
    # Verify ID was extracted correctly from URL
    assert created_data["source"]["spreadsheet_id"] == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

    # 3. Get single source
    get_res = client.get(f"/api/sources/{created_id}")
    assert get_res.status_code == 200
    assert get_res.get_json()["source"]["source_id"] == created_id

    # 4. Activate the source
    act_res = client.post(f"/api/sources/{created_id}/activate")
    assert act_res.status_code == 200

    active_src = database.get_active_source()
    assert active_src is not None
    assert active_src["source_id"] == created_id

    # 5. Archive the source
    arch_res = client.post(f"/api/sources/{created_id}/archive")
    assert arch_res.status_code == 200
    arch_data = client.get(f"/api/sources/{created_id}").get_json()
    assert arch_data["source"]["status"] == "archived"

    # 6. Re-activate default October source
    client.post("/api/sources/october-2026-master/activate")

    # 7. Delete the test source
    del_res = client.delete(f"/api/sources/{created_id}")
    assert del_res.status_code == 200

    # Verify deleted
    get_del = client.get(f"/api/sources/{created_id}")
    assert get_del.status_code == 404

def test_inventory_source_filtering(client):
    # Query with non-existent source - must return 0 items
    res1 = client.get("/api/inventory?source=non_existent_source")
    assert res1.status_code == 200
    data1 = res1.get_json()
    assert "items" in data1
    assert data1["total"] == 0

    # Query with all sources when empty
    res2 = client.get("/api/inventory?source=all")
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert "items" in data2

def test_dashboard_source_filtering(client):
    res = client.get("/api/dashboard?source=active")
    assert res.status_code == 200
    data = res.get_json()
    assert "total_products" in data
    assert "uom_quantities" in data
    assert data["source_filter"] == "active"

def test_delete_individual_worksheet(client):
    # Test worksheet deletion endpoint
    res = client.delete("/api/sources/october-2026-master/sheets/DummyNonExistent")
    assert res.status_code == 200

