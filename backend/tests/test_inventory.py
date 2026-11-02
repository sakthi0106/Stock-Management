import pytest
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sheets_client import GoogleSheetsClient
from sheet_analyzer import SheetAnalyzer
from inventory_service import InventoryService, parse_num_or_preserve

def test_parse_num_preserves_literals():
    assert parse_num_or_preserve("NA") == "NA"
    assert parse_num_or_preserve("-") == "-"
    assert parse_num_or_preserve("0") == 0
    assert parse_num_or_preserve("125.50") == 125.5
    assert parse_num_or_preserve("$1,250.00") == 1250.0

def test_inventory_service_amount_exclusion():
    client = GoogleSheetsClient(local_only=True)
    analyzer = SheetAnalyzer(client)
    analysis = analyzer.analyze_all_sheets()
    
    raw_data = {s: client.get_sheet_values(s) for s in analysis["sheets"].keys()}
    service = InventoryService(analysis, raw_data)

    for p in service.products:
        # Assert Amount is NOT in product keys
        assert "amount" not in p
        assert "total_amount" not in p
        for extra_k in p.get("extra_fields", {}).keys():
            assert "amount" not in extra_k.lower()
            assert "total cost" not in extra_k.lower()

def test_inventory_service_uom_grouping():
    client = GoogleSheetsClient(local_only=True)
    analyzer = SheetAnalyzer(client)
    analysis = analyzer.analyze_all_sheets()
    raw_data = {s: client.get_sheet_values(s) for s in analysis["sheets"].keys()}
    service = InventoryService(analysis, raw_data)

    summary = service.get_dashboard_summary()
    assert "uom_quantities" in summary
    # Check that UOMs are separate keys (e.g. COIL, MTR, PCS, BOX)
    assert isinstance(summary["uom_quantities"], dict)
    assert len(summary["uom_quantities"]) > 1

def test_stock_calculations_formula():
    client = GoogleSheetsClient(local_only=True)
    analyzer = SheetAnalyzer(client)
    analysis = analyzer.analyze_all_sheets()
    raw_data = {s: client.get_sheet_values(s) for s in analysis["sheets"].keys()}
    service = InventoryService(analysis, raw_data)

    for m in service.movements:
        if m["opening_stock"] is not None and m["closing_stock"] is not None:
            # Closing = Opening + IN - OUT
            calc = m["opening_stock"] + (m["in_qty"] or 0) - (m["out_qty"] or 0)
            assert m["closing_stock"] == calc
