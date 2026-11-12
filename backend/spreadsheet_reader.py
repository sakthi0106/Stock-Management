import os
import openpyxl
from typing import Dict, List, Any
from spreadsheet_parser import UniversalParser


class UniversalSpreadsheetReader:
    """Reads raw 2D cell grids from Excel files and normalizes them identically to Google Sheets."""

    def extract_from_excel(self, file_path: str) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Excel file not found at: {file_path}")

        wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
        sheets_dict: Dict[str, Any] = {}

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            values: List[List[Any]] = []
            for row in ws.iter_rows(values_only=True):
                # Only keep rows that have at least one non-empty cell
                if any(cell is not None and str(cell).strip() != "" for cell in row):
                    cleaned_row = [cell if cell is not None else "" for cell in row]
                    values.append(cleaned_row)

            sheets_dict[sheet_name] = {
                "values": values,
                "row_count": len(values)
            }

        wb.close()
        return {
            "source_type": "excel",
            "file_name": os.path.basename(file_path),
            "sheets": sheets_dict
        }
