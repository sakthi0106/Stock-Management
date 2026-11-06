import pytest
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from inventory_service import InventoryService, parse_num_or_preserve

def test_parse_num_preserves_literals():
    assert parse_num_or_preserve("NA") == "NA"
    assert parse_num_or_preserve("-") == "-"
    assert parse_num_or_preserve("0") == 0
    assert parse_num_or_preserve("125.50") == 125.5
    assert parse_num_or_preserve("$1,250.00") == 1250.0

def test_inventory_service_amount_exclusion():
    analysis = {
        "sheets": {
            "Sheet1": {
                "header_rows": [2],
                "data_start_row": 3,
                "amount_columns": ["AMOUNT", "TOTAL COST"],
                "categories": ["CatA"],
                "units": ["NOS"]
            }
        }
    }
    raw_data = {
        "Sheet1": [
            ["", "", "", "", "", "", ""],
            ["Sl No", "Description", "Part No", "Category", "UOM", "AMOUNT", "OPENING STOCK"],
            [1, "Product 1", "P-101", "CatA", "NOS", 500, 10],
            [2, "Product 2", "P-102", "CatA", "NOS", 1200, 20]
        ]
    }
    service = InventoryService(analysis, raw_data)

    for p in service.products:
        assert "amount" not in p
        assert "total_amount" not in p
        for extra_k in p.get("extra_fields", {}).keys():
            assert "amount" not in extra_k.lower()
            assert "total cost" not in extra_k.lower()

def test_inventory_service_uom_grouping():
    analysis = {
        "sheets": {
            "Sheet1": {
                "header_rows": [2],
                "data_start_row": 3,
                "amount_columns": [],
                "categories": ["CatA"],
                "units": ["NOS", "MTR"]
            }
        }
    }
    raw_data = {
        "Sheet1": [
            ["", "", "", "", "", ""],
            ["Sl No", "Description", "Part No", "Category", "UOM", "OPENING STOCK"],
            [1, "Product 1", "P-101", "CatA", "NOS", 10],
            [2, "Product 2", "P-102", "CatA", "MTR", 25]
        ]
    }
    service = InventoryService(analysis, raw_data)
    summary = service.get_dashboard_summary()
    assert "uom_quantities" in summary
    assert isinstance(summary["uom_quantities"], dict)
    assert "NOS" in summary["uom_quantities"]
    assert "MTR" in summary["uom_quantities"]

def test_stock_calculations_formula():
    analysis = {
        "sheets": {
            "Sheet1": {
                "header_rows": [2],
                "data_start_row": 3,
                "amount_columns": [],
                "categories": ["CatA"],
                "units": ["NOS"]
            }
        }
    }
    raw_data = {
        "Sheet1": [
            ["", "", "", "", "", ""],
            ["Sl No", "Description", "Part No", "Category", "UOM", "OPENING STOCK"],
            [1, "Product 1", "P-101", "CatA", "NOS", 50]
        ]
    }
    service = InventoryService(analysis, raw_data)
    assert len(service.products) == 1
    assert service.products[0]["current_stock"] == 50
