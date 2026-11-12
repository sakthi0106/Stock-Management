import pytest
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from spreadsheet_parser import UniversalParser, parse_numeric, parse_date_string
from inventory_store import InventoryDataStore, extract_spreadsheet_id
from app import create_app


def test_extract_spreadsheet_id():
    url = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit#gid=0"
    assert extract_spreadsheet_id(url) == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
    assert extract_spreadsheet_id("my_raw_id_123") == "my_raw_id_123"


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
    assert parse_date_string("5 IN", default_year_month="2026-10") == "2026-10-05"
    assert parse_date_string("22 OUT", default_year_month="2026-10") == "2026-10-22"


def test_inventory_data_store_dynamic_columns_and_movements():
    store = InventoryDataStore(source_id="test_src", name="Test Sheet")
    raw_sheets = {
        "October 2026": [
            ["Item Code", "Description", "Supplier", "Custom_Spec", "01-10-2026", "01-10-2026", "02-10-2026", "02-10-2026"],
            ["", "", "", "", "IN", "OUT", "IN", "OUT"],
            ["PART-001", "Ball Bearing 6204", "SKF", "20mm", 50, 10, 20, 5],
            ["PART-002", "Hex Bolt M8x30", "TVS", "SS304", 100, 0, 50, 30]
        ]
    }

    store.update_from_raw_sheets(raw_sheets, period="2026-10")

    assert len(store.products) == 2
    assert len(store.movements) > 0
    assert store.products[0]["extra_fields"]["Supplier"] == "SKF"
    assert store.products[0]["extra_fields"]["Custom_Spec"] == "20mm"
    assert len(store.dynamic_columns["October 2026"]) == 8
    assert len(store.dynamic_records["October 2026"]) == 2

    summary = store.get_dashboard_summary()
    assert summary["total_products"] == 2
    assert summary["total_movements_count"] == 7
    assert summary["inward_by_uom"]["NOS"] == 220
    assert summary["outward_by_uom"]["NOS"] == 45


def test_api_endpoints():
    app = create_app()
    client = app.test_client()

    assert client.get('/api/health').status_code == 200
    assert client.get('/api/sources').status_code == 200
    assert client.get('/api/dashboard').status_code == 200
    assert client.get('/api/inventory').status_code == 200
    assert client.get('/api/movements').status_code == 200
    assert client.get('/api/spreadsheet-intelligence/sources').status_code == 200


def test_unit_price_extraction_and_sorting():
    store = InventoryDataStore(source_id="price_src", name="Price Sheet")
    raw_sheets = {
        "Stock": [
            ["Part No", "Description", "Unit Price", "Opening Stock", "Closing Stock"],
            ["P-100", "Copper Cable", "₹1,250.50", 10, 15],
            ["P-200", "MCB Switch", 450, 20, 18],
            ["P-300", "Control Panel", "NA", 5, 5],
            ["P-400", "Fuse Link", "-", 12, 12],
        ]
    }
    store.update_from_raw_sheets(raw_sheets)

    by_part = {p["part_no"]: p for p in store.products}
    assert by_part["P-100"]["unit_price"] == 1250.5
    assert by_part["P-200"]["unit_price"] == 450
    assert by_part["P-300"]["unit_price"] == "NA"
    assert by_part["P-400"]["unit_price"] == "-"
    # Ensure unit price did not leak into stock quantities
    assert by_part["P-100"]["current_stock"] == 15
    assert by_part["P-200"]["opening_stock"] == 20
