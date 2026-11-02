import pytest
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sheets_client import GoogleSheetsClient
from sheet_analyzer import SheetAnalyzer

def test_sheet_analyzer_uses_prefetched_sheet_data():
    class ClientWithoutReads:
        def is_configured(self):
            return True

        def get_last_error(self):
            return None

        def get_sheet_values(self, sheet_name):
            raise AssertionError("Expected prefetched values to be used")

        def get_sheet_formulas(self, sheet_name):
            raise AssertionError("Expected prefetched formulas to be used")

    analyzer = SheetAnalyzer(ClientWithoutReads())
    report = analyzer.analyze_all_sheets(
        metadata={"sheets": [{"properties": {"title": "Inventory"}}]},
        raw_values={"Inventory": [["Part No", "Description"], ["P-1", "Widget"]]},
        raw_formulas={"Inventory": [["Part No", "Description"], ["P-1", "Widget"]]},
    )

    assert report["sheets"]["Inventory"]["row_count"] == 2
    assert report["sheets"]["Inventory"]["headers"]

def test_sheet_analyzer_batches_sheet_reads():
    class BatchClient:
        def is_configured(self):
            return True

        def get_last_error(self):
            return None

        def get_spreadsheet_metadata(self):
            return {"sheets": [{"properties": {"title": "Inventory"}}]}

        def get_batch_sheet_values(self, sheet_names):
            assert sheet_names == ["Inventory"]
            return {"Inventory": [["Part No", "Description"], ["P-1", "Widget"]]}

        def get_batch_sheet_formulas(self, sheet_names):
            assert sheet_names == ["Inventory"]
            return {"Inventory": [["Part No", "Description"], ["P-1", "Widget"]]}

        def get_sheet_values(self, sheet_name):
            raise AssertionError("Expected batched values to be used")

        def get_sheet_formulas(self, sheet_name):
            raise AssertionError("Expected batched formulas to be used")

    report = SheetAnalyzer(BatchClient()).analyze_all_sheets()

    assert report["sheets"]["Inventory"]["row_count"] == 2
    assert report["sheets"]["Inventory"]["headers"]

def test_sheet_analyzer_identifies_all_six_sheets():
    client = GoogleSheetsClient(local_only=True)
    analyzer = SheetAnalyzer(client)
    report = analyzer.analyze_all_sheets()

    assert report["sheets_count"] == 6
    expected_sheets = [
        "Busbar", "ACCESORIES", "Cable,Lug,Lamp,TB,Truff",
        "SLEEVE ", "Fab Sheets", "Fasteners"
    ]
    for s_name in expected_sheets:
        assert s_name in report["sheets"]
        s_data = report["sheets"][s_name]
        assert s_data["row_count"] > 0
        assert len(s_data["headers"]) > 0

def test_amount_columns_strictly_detected():
    client = GoogleSheetsClient(local_only=True)
    analyzer = SheetAnalyzer(client)
    report = analyzer.analyze_all_sheets()

    for s_name in ["Busbar", "ACCESORIES", "Fasteners"]:
        s_data = report["sheets"][s_name]
        assert any("amount" in col.lower() for col in s_data["amount_columns"])

def test_special_values_preserved():
    client = GoogleSheetsClient(local_only=True)
    analyzer = SheetAnalyzer(client)
    report = analyzer.analyze_all_sheets()

    busbars = report["sheets"]["Busbar"]
    assert len(busbars["special_values"]) > 0 or any("NA" in v or "-" in v for v in busbars["special_values"])
