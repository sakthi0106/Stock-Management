import pytest
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

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

def test_sheet_analyzer_identifies_all_dynamic_sheets():
    class DynamicClient:
        def is_configured(self):
            return True

        def get_spreadsheet_metadata(self):
            return {"sheets": [
                {"properties": {"title": "CustomSheet1"}},
                {"properties": {"title": "CustomSheet2"}}
            ]}

        def get_batch_sheet_values(self, sheet_names):
            return {
                "CustomSheet1": [["Item", "Qty"], ["A", 10]],
                "CustomSheet2": [["Material", "Cost"], ["Steel", 100]]
            }

        def get_batch_sheet_formulas(self, sheet_names):
            return {s: [] for s in sheet_names}

    analyzer = SheetAnalyzer(DynamicClient())
    report = analyzer.analyze_all_sheets()

    assert report["sheets_count"] == 2
    assert "CustomSheet1" in report["sheets"]
    assert "CustomSheet2" in report["sheets"]

def test_amount_columns_strictly_detected():
    class AmountClient:
        def is_configured(self):
            return True

        def get_spreadsheet_metadata(self):
            return {"sheets": [{"properties": {"title": "TestSheet"}}]}

        def get_batch_sheet_values(self, sheet_names):
            return {"TestSheet": [
                ["Part No", "Description", "Total Amount", "Cost Value"],
                ["P1", "Desc1", 100, 50]
            ]}

        def get_batch_sheet_formulas(self, sheet_names):
            return {"TestSheet": []}

    analyzer = SheetAnalyzer(AmountClient())
    report = analyzer.analyze_all_sheets()
    s_data = report["sheets"]["TestSheet"]
    assert any("amount" in col.lower() for col in s_data["amount_columns"])

def test_special_values_preserved():
    class SpecialClient:
        def is_configured(self):
            return True

        def get_spreadsheet_metadata(self):
            return {"sheets": [{"properties": {"title": "TestSpecial"}}]}

        def get_batch_sheet_values(self, sheet_names):
            return {"TestSpecial": [
                ["Part No", "Price"],
                ["P1", "NA"],
                ["P2", "-"]
            ]}

        def get_batch_sheet_formulas(self, sheet_names):
            return {"TestSpecial": []}

    analyzer = SheetAnalyzer(SpecialClient())
    report = analyzer.analyze_all_sheets()
    s_data = report["sheets"]["TestSpecial"]
    assert len(s_data["special_values"]) > 0 or any("NA" in v or "-" in v for v in s_data["special_values"])
