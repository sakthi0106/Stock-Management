import os
import re
import logging
from typing import Dict, List, Any, Optional, Tuple
import openpyxl

logger = logging.getLogger(__name__)

DATE_PATTERNS = [
    r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}',
    r'^\d{1,2}[-/]\d{1,2}[-/]\d{4}',
    r'^\d{4}\.\d{1,2}\.\d{1,2}',
    r'^\d{1,2}\.\d{1,2}\.\d{4}',
]

SPECIAL_LITERALS = {'N/A', '-', 'NA', 'N.A.', 'nil', 'none', 'null'}


class UniversalSpreadsheetReader:
    """Universal spreadsheet reader supporting Excel (.xlsx, .xls) and Google Sheets.
    
    Extracts raw values, discovers multi-row/merged headers, detects populated ranges,
    preserves literal 'NA' and '-' values, and handles unknown/custom columns dynamically.
    """

    def __init__(self, google_sheets_client=None):
        self.google_sheets_client = google_sheets_client

    def extract_from_excel(self, file_path: str) -> Dict[str, Any]:
        """Extract all worksheets, raw values, formulas, and merged ranges from an Excel file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Excel file not found at: {file_path}")

        workbook = openpyxl.load_workbook(file_path, data_only=True)
        workbook_formulas = None
        try:
            workbook_formulas = openpyxl.load_workbook(file_path, data_only=False)
        except Exception as e:
            logger.warning(f"Could not load formula view for {file_path}: {e}")

        sheets_data = {}
        for sheet_name in workbook.sheetnames:
            ws = workbook[sheet_name]
            ws_formulas = workbook_formulas[sheet_name] if workbook_formulas and sheet_name in workbook_formulas.sheetnames else None

            merged_ranges = [str(m) for m in ws.merged_cells.ranges]

            raw_values: List[List[Any]] = []
            for row in ws.iter_rows(values_only=True):
                # Clean row and preserve literals
                cleaned_row = []
                for val in row:
                    if val is None:
                        cleaned_row.append("")
                    else:
                        cleaned_row.append(str(val).strip() if isinstance(val, str) else val)
                raw_values.append(cleaned_row)

            # Strip trailing completely empty rows
            while raw_values and all(c == "" or c is None for c in raw_values[-1]):
                raw_values.pop()

            sheets_data[sheet_name] = {
                "sheet_name": sheet_name,
                "values": raw_values,
                "merged_ranges": merged_ranges,
                "row_count": len(raw_values),
                "col_count": max((len(r) for r in raw_values), default=0)
            }

        return {
            "source_type": "excel_upload",
            "file_path": file_path,
            "sheets": sheets_data
        }

    def extract_from_google_sheets(self, spreadsheet_id: str) -> Dict[str, Any]:
        """Extract all worksheets and raw values from Google Sheets."""
        from sheets_client import GoogleSheetsClient
        client = self.google_sheets_client
        if client is None or getattr(client, 'spreadsheet_id', '') != spreadsheet_id:
            client = GoogleSheetsClient(spreadsheet_id=spreadsheet_id)

        metadata = client.get_spreadsheet_metadata()
        sheet_titles = [
            s.get("properties", {}).get("title")
            for s in metadata.get("sheets", [])
            if s.get("properties", {}).get("title")
        ]

        raw_values_map = client.get_batch_sheet_values(sheet_titles)

        sheets_data = {}
        for s in metadata.get("sheets", []):
            title = s.get("properties", {}).get("title", "")
            if not title:
                continue

            vals = raw_values_map.get(title, [])
            # Normalize rows
            normalized_vals = []
            for row in vals:
                cleaned_row = [str(c).strip() if c is not None else "" for c in row]
                normalized_vals.append(cleaned_row)

            # Strip trailing empty rows
            while normalized_vals and all(c == "" for c in normalized_vals[-1]):
                normalized_vals.pop()

            # Merged ranges from Google Sheets metadata if present
            merged_ranges = []
            for mr in s.get("merges", []):
                start_r = mr.get("startRowIndex", 0) + 1
                end_r = mr.get("endRowIndex", 0)
                start_c = chr(65 + mr.get("startColumnIndex", 0))
                end_c = chr(65 + mr.get("endColumnIndex", 1) - 1)
                merged_ranges.append(f"{start_c}{start_r}:{end_c}{end_r}")

            sheets_data[title] = {
                "sheet_name": title,
                "values": normalized_vals,
                "merged_ranges": merged_ranges,
                "row_count": len(normalized_vals),
                "col_count": max((len(r) for r in normalized_vals), default=0)
            }

        return {
            "source_type": "google_sheets",
            "spreadsheet_id": spreadsheet_id,
            "title": metadata.get("properties", {}).get("title", "Untitled Google Sheet"),
            "sheets": sheets_data
        }

    @staticmethod
    def detect_header_rows(values: List[List[Any]]) -> Tuple[List[int], List[str], int]:
        """Dynamically detect header rows (single or multi-row) and return:
        (header_row_indices_1_based, combined_headers, data_start_row_1_based).
        """
        if not values:
            return ([1], [], 1)

        total_rows = len(values)
        if total_rows == 1:
            headers = [str(c).strip() if c is not None else f"Col_{i+1}" for i, c in enumerate(values[0])]
            return ([1], headers, 2)

        # Scan initial rows (up to 8 rows) to find header candidate
        max_scan = min(8, total_rows)
        row_scores = []

        for idx in range(max_scan):
            row = values[idx]
            non_empty = [c for c in row if c is not None and str(c).strip() != ""]
            non_empty_count = len(non_empty)
            if non_empty_count == 0:
                row_scores.append((idx, 0, 0, 0))
                continue

            # Check text vs numeric ratio: headers are mostly text strings, not floats
            text_count = 0
            for c in non_empty:
                s = str(c).strip()
                # Check if it parses as a float
                try:
                    float(s.replace(',', ''))
                except ValueError:
                    text_count += 1

            text_ratio = text_count / non_empty_count if non_empty_count > 0 else 0
            unique_count = len(set(str(c).strip().lower() for c in non_empty))

            # Composite score: high non_empty count, high text ratio, high unique count
            score = (non_empty_count * 2.0) + (text_ratio * 5.0) + (unique_count * 1.5)
            row_scores.append((idx, score, non_empty_count, text_ratio))

        # Pick best scoring row as the primary header row
        best_row_idx = max(row_scores, key=lambda x: x[1])[0]

        # Check for multi-row header (e.g. Row 1 has dates, Row 2 has IN / OUT)
        header_rows = [best_row_idx + 1]
        data_start_row = best_row_idx + 2

        # Check if next row also looks like a sub-header (e.g. contains IN, OUT, QTY, UOM, or short labels)
        if best_row_idx + 1 < total_rows:
            next_row = values[best_row_idx + 1]
            sub_header_indicators = {'in', 'out', 'qty', 'opening', 'closing', 'bal', 'uom', 'rate', 'unit', 'desc', 'amt'}
            next_non_empty = [str(c).strip().lower() for c in next_row if c is not None and str(c).strip() != ""]
            if next_non_empty and any(ind in c for c in next_non_empty for ind in sub_header_indicators):
                header_rows.append(best_row_idx + 2)
                data_start_row = best_row_idx + 3

        # Combine headers across rows, scanning ALL rows to ensure newly added columns are captured
        combined_headers = []
        max_cols = max((len(r) for r in values), default=0)

        if len(header_rows) == 1:
            primary_row = values[header_rows[0] - 1]
            for col_i in range(max_cols):
                val = str(primary_row[col_i]).strip() if col_i < len(primary_row) and primary_row[col_i] is not None else ""
                combined_headers.append(val or f"Column_{col_i + 1}")
        else:
            # Multi-row: propagate top header across sub-headers if top header was merged/empty
            top_row = values[header_rows[0] - 1] if header_rows[0] - 1 < len(values) else []
            sub_row = values[header_rows[1] - 1] if header_rows[1] - 1 < len(values) else []
            current_top = ""
            for col_i in range(max_cols):
                top_val = str(top_row[col_i]).strip() if col_i < len(top_row) and top_row[col_i] is not None else ""
                sub_val = str(sub_row[col_i]).strip() if col_i < len(sub_row) and sub_row[col_i] is not None else ""

                if top_val:
                    current_top = top_val

                if current_top and sub_val:
                    combined_headers.append(f"{current_top} {sub_val}".strip())
                elif sub_val:
                    combined_headers.append(sub_val)
                elif top_val:
                    combined_headers.append(top_val)
                else:
                    combined_headers.append(f"Column_{col_i + 1}")

        # Deduplicate headers if needed
        seen_headers: Dict[str, int] = {}
        unique_headers = []
        for h in combined_headers:
            base_h = h.strip() or "Unnamed"
            if base_h in seen_headers:
                seen_headers[base_h] += 1
                unique_headers.append(f"{base_h}_{seen_headers[base_h]}")
            else:
                seen_headers[base_h] = 0
                unique_headers.append(base_h)

        return (header_rows, unique_headers, data_start_row)
