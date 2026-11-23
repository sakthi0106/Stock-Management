import pytest
import sys
import io
import openpyxl
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from spreadsheet_parser import UniversalParser, parse_numeric, parse_date_string
from inventory_store import InventoryDataStore, extract_spreadsheet_id
from sheets_client import to_a1_range
from sync_manager import SyncManager
from app import create_app


def test_to_a1_range():
    assert to_a1_range("Busbar") == "Busbar"
    assert to_a1_range("ACCESORIES") == "ACCESORIES"
    assert to_a1_range("SLEEVE ") == "'SLEEVE '"
    assert to_a1_range(" Cable,Lug,Lamp,TB,Truff") == "' Cable,Lug,Lamp,TB,Truff'"
    assert to_a1_range("Fab Sheets") == "'Fab Sheets'"
    assert to_a1_range("Fasteners") == "Fasteners"
    assert to_a1_range("Jane's Sheet") == "'Jane''s Sheet'"


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
    assert by_part["P-100"]["current_stock"] == 15
    assert by_part["P-200"]["opening_stock"] == 20


def test_multi_source_and_combined_view():
    sm = SyncManager()

    # Source 1: Sept Inventory
    s1 = sm.register_source(name="Sept Inventory", spreadsheet_url_or_id="s1_id", source_type="excel_upload", is_active=True)
    s1.update_from_raw_sheets({
        "Sept": [
            ["Part No", "Description", "Opening Stock", "Closing Stock"],
            ["ITEM-01", "Relay 12V", 10, 25]
        ]
    })

    # Source 2: Oct Inventory
    s2 = sm.register_source(name="Oct Inventory", spreadsheet_url_or_id="s2_id", source_type="excel_upload", is_active=True)
    s2.update_from_raw_sheets({
        "Oct": [
            ["Part No", "Description", "Opening Stock", "Closing Stock"],
            ["ITEM-02", "Contactor 24V", 5, 12]
        ]
    })

    # Both sources must exist simultaneously in SyncManager
    assert len(sm.sources) >= 2
    assert sm.get_store(s1.source_id) is not None
    assert sm.get_store(s2.source_id) is not None

    # 'all' must return combined store with products from BOTH sources
    combined = sm.get_store("all")
    assert combined is not None
    assert len(combined.products) >= 2
    part_numbers = [p["part_no"] for p in combined.products]
    assert "ITEM-01" in part_numbers
    assert "ITEM-02" in part_numbers

    # Dashboard summary of combined view
    summary = combined.get_dashboard_summary()
    assert summary["total_products"] >= 2


def test_latest_opening_stock_reflection():
    store = InventoryDataStore(source_id="latest_op_test", name="Latest Op Test")
    raw_sheets = {
        "November 2026": [
            ["Part No", "Description", "Opening Stock", "Closing Stock"],
            ["PART-A", "Capacitor 100uF", 50, 45],
            ["PART-A", "Capacitor 100uF", 90, 85],  # Later row with updated/latest opening stock
        ]
    }
    store.update_from_raw_sheets(raw_sheets)
    assert len(store.products) == 1
    prod = store.products[0]
    # Latest opening stock should be 90 (from later row)
    assert prod["opening_stock"] == 90
    assert prod["current_stock"] == 85


def test_delete_source_and_tombstones():
    sm = SyncManager()
    s = sm.register_source(name="Temp To Delete", spreadsheet_url_or_id="temp_sheet_999")
    sid = s.source_id
    assert sid in sm.sources

    # Delete source
    ok = sm.delete_source(sid)
    assert ok is True
    assert sid not in sm.sources
    assert sid in sm.deleted_source_ids
    assert "temp_sheet_999" in sm.deleted_source_ids

    # Deleting again is idempotent and returns True
    assert sm.delete_source(sid) is True


def test_active_source_not_mandatory_and_deactivate():
    sm = SyncManager()
    sm.sources.clear()
    sm.active_source_id = None

    # Register source with is_active=False
    s1 = sm.register_source(name="Source 1", spreadsheet_url_or_id="sheet_1", is_active=False)
    assert s1.is_active == 0
    assert sm.active_source_id is None

    # Register second source also inactive
    s2 = sm.register_source(name="Source 2", spreadsheet_url_or_id="sheet_2", is_active=False)
    assert s2.is_active == 0
    assert sm.active_source_id is None

    # get_store("active") returns combined store when no source is active
    store = sm.get_store("active")
    assert store is not None
    assert store.source_id == "all"

    # Activate s1
    assert sm.activate_source(s1.source_id) is True
    assert s1.is_active == 1
    assert sm.active_source_id == s1.source_id

    # Deactivate s1
    assert sm.deactivate_source(s1.source_id) is True
    assert s1.is_active == 0
    assert sm.active_source_id is None

    # Activating then deleting active source does NOT force another source active
    sm.activate_source(s2.source_id)
    assert sm.active_source_id == s2.source_id
    sm.delete_source(s2.source_id)
    assert sm.active_source_id is None
    assert s1.is_active == 0


def test_register_source_deduplication_and_isolated_delete():
    sm = SyncManager()
    sm.sources.clear()
    sm.active_source_id = None

    # Register initial sheet
    s1 = sm.register_source(name="Stock_Data", spreadsheet_url_or_id="https://docs.google.com/spreadsheets/d/abc123sheet/edit")
    assert len(sm.sources) == 1
    sid1 = s1.source_id

    # Registering the same spreadsheet again updates s1 and does NOT create a second source
    s2 = sm.register_source(name="Stock data", spreadsheet_url_or_id="abc123sheet", period="2026-10")
    assert len(sm.sources) == 1
    assert s2.source_id == sid1
    assert s2.period == "2026-10"

    # Register a different sheet
    s3 = sm.register_source(name="Different Sheet", spreadsheet_url_or_id="diff_sheet_456")
    assert len(sm.sources) == 2

    # Deleting s3 only deletes s3, and does not affect s1/s2
    sm.delete_source(s3.source_id)
    assert len(sm.sources) == 1
    assert sid1 in sm.sources
    assert s3.source_id not in sm.sources
