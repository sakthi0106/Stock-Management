import os
import gc
import logging
import openpyxl
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class UniversalSpreadsheetReader:
    """Reads raw 2D cell grids from Excel files safely and memory-efficiently for cloud hosting."""

    def extract_from_excel(self, file_path: str, max_rows_per_sheet: int = 15000) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Excel file not found at: {file_path}")

        # openpyxl only supports modern .xlsx / .xlsm formats
        lower_path = file_path.lower()
        if lower_path.endswith('.xls') and not lower_path.endswith('.xlsx'):
            raise ValueError(
                "Legacy .xls binary format is not supported directly. Please save or export your file as an Excel Workbook (.xlsx) before uploading."
            )

        wb = None
        sheets_dict: Dict[str, Any] = {}

        try:
            # read_only=True and data_only=True minimizes memory footprint
            wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)

            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                values: List[List[Any]] = []
                consecutive_empty = 0

                for row in ws.iter_rows(values_only=True):
                    # Check if the row contains any non-empty cell
                    has_content = any(cell is not None and str(cell).strip() != "" for cell in row)
                    if has_content:
                        # Clean cells and trim trailing empty cells in this row to conserve memory
                        cleaned_row = [cell if cell is not None else "" for cell in row]
                        while cleaned_row and cleaned_row[-1] == "":
                            cleaned_row.pop()

                        values.append(cleaned_row)
                        consecutive_empty = 0
                    else:
                        consecutive_empty += 1
                        # If we have already started reading data and encounter 30 consecutive empty rows,
                        # break to avoid scanning 1,000,000 blank formatted rows in Excel.
                        if consecutive_empty >= 30 and len(values) > 0:
                            break

                    if len(values) >= max_rows_per_sheet:
                        logger.warning(f"Sheet '{sheet_name}' reached safety limit of {max_rows_per_sheet} rows.")
                        break

                sheets_dict[sheet_name] = {
                    "values": values,
                    "row_count": len(values)
                }

        finally:
            if wb is not None:
                try:
                    wb.close()
                except Exception:
                    pass
            # Force garbage collection to free openpyxl memory back to the OS immediately
            gc.collect()

        return {
            "source_type": "excel",
            "file_name": os.path.basename(file_path),
            "sheets": sheets_dict
        }
