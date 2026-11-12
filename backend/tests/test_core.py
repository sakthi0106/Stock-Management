import pytest
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from spreadsheet_parser import UniversalParser, parse_numeric, parse_date_string
from inventory_store import InventoryDataStore
from app import create_app


def test_parse_numeric():
    assert parse_numeric("100") == 100
    assert parse_numeric(" 45.5 ") == 45.5
    assert parse_numeric("$1,250") == 1250
    assert parse_numeric("₹500") == 500
    assert parse_numeric("-") is None
    assert parse_numeric("NA") is None
    assert parse_numeric(None) is None


def test_parse_date_string():
    assert parse_date_string("2026-10-15") == "2026-10-15"
    assert parse_date_string("15-10-2026") == "2026-10-15"
    assert parse_date_string("15/10/2026") == "2026-10-15"
    # Day number with default period
    assert parse_date_string("5 IN", default_year_month="2026-10") == "2026-10-05"
    assert parse_date_string("22 OUT", default_year_month="2026-10") == "2026-10-22"


def test_inventory_data_store_paired_columns():
    store = InventoryDataStore()
    raw_sheets = {
        "October 2026": [
            ["Item Code", "Description", "01-10-2026", "01-10-2026", "02-10-2026", "02-10-2026"],
            ["", "", "IN", "OUT", "IN", "OUT"],
            ["PART-001", "Ball Bearing 6204", 50, 10, 20, 5],
            ["PART-002", "Hex Bolt M8x30", 100, 0, 50, 30]
        ]
    }

    store.update_from_raw_sheets(raw_sheets, period="2026-10")

    assert len(store.products) == 2
    assert len(store.movements) > 0

    # Test dashboard summary
    summary = store.get_dashboard_summary()
    assert summary["total_items"] == 2
    assert summary["total_in_qty"] == (50 + 20 + 100 + 50)
    assert summary["total_out_qty"] == (10 + 5 + 30)


def test_api_endpoints():
    app = create_app()
    client = app.test_client()

    res = client.get('/api/health')
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"

    res = client.get('/api/dashboard')
    assert res.status_code == 200

    res = client.get('/api/inventory')
    assert res.status_code == 200

    res = client.get('/api/movements')
    assert res.status_code == 200
