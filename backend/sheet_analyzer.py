import re
from typing import Dict, List, Any, Optional

DATE_PATTERNS = [
    r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}',
    r'^\d{1,2}[/-]\d{1,2}[-/]\d{4}',
    r'^\d{4}\.\d{1,2}\.\d{1,2}'
]

SPECIAL_LITERALS = {"NA", "-", "N/A", "N.A."}

AMOUNT_KEYWORDS = [
    "amount", "total amount", "total cost", "total price", "line total", 
    "cost total", "ext price", "extended price", "val", "value"
]

UNIT_PRICE_KEYWORDS = [
    "unit price", "unit cost", "rate", "price", "price/unit", "unit_price", "rate (rs)", "rate/unit"
]

PRODUCT_KEY_KEYWORDS = [
    "product id", "product_id", "product code", "part no", "part_no", "item code", "item no", "sku", "code"
]

STOCK_KEYWORDS = [
    "stock", "current stock", "balance", "qty", "quantity", "closing stock", 
    "opening stock", "in_qty", "out_qty", "inward", "outward", "received", "issued"
]

class SheetAnalyzer:
    def __init__(self, sheets_client):
        self.client = sheets_client

    def analyze_all_sheets(
        self,
        metadata: Optional[Dict[str, Any]] = None,
        raw_values: Optional[Dict[str, List[List[Any]]]] = None,
        raw_formulas: Optional[Dict[str, List[List[Any]]]] = None
    ) -> Dict[str, Any]:
        """Analyze all worksheets in the connected Google Spreadsheet or demo provider."""
        metadata = metadata if metadata is not None else self.client.get_spreadsheet_metadata()
        sheets_info = metadata.get("sheets", [])
        sheet_names = [
            sheet.get("properties", {}).get("title", "")
            for sheet in sheets_info
            if sheet.get("properties", {}).get("title")
        ]
        raw_values = raw_values if raw_values is not None else self.client.get_batch_sheet_values(sheet_names)
        raw_formulas = raw_formulas if raw_formulas is not None else self.client.get_batch_sheet_formulas(sheet_names)

        analysis_report = {
            "title": metadata.get("properties", {}).get("title", "Stock Master"),
            "is_configured": self.client.is_configured(),
            "last_error": self.client.get_last_error(),
            "sheets_count": len(sheets_info),
            "sheets": {},
            "relationships": []
        }

        all_product_keys = {}

        for s in sheets_info:
            props = s.get("properties", {})
            sheet_name = props.get("title", "")
            sheet_values = raw_values.get(sheet_name, [])
            sheet_formulas = raw_formulas.get(sheet_name, [])
            
            sheet_analysis = self._analyze_single_sheet(sheet_name, sheet_values, sheet_formulas, props)
            analysis_report["sheets"][sheet_name] = sheet_analysis

            # Collect product keys for cross-sheet relationships
            if sheet_analysis["product_key_candidates"]:
                primary_key_col = sheet_analysis["product_key_candidates"][0]
                keys_found = sheet_analysis.get("sample_keys", [])
                all_product_keys[sheet_name] = {
                    "column": primary_key_col,
                    "keys": keys_found
                }

        # Analyze relationships (e.g. Inward/Outward registers referencing product master sheets)
        relationships = []
        for src_sheet, src_data in all_product_keys.items():
            for target_sheet, target_data in all_product_keys.items():
                if src_sheet == target_sheet:
                    continue
                intersection = set(src_data["keys"]).intersection(set(target_data["keys"]))
                if intersection:
                    relationships.append({
                        "from_sheet": src_sheet,
                        "to_sheet": target_sheet,
                        "key_column_from": src_data["column"],
                        "key_column_to": target_data["column"],
                        "matched_sample_count": len(intersection)
                    })
        analysis_report["relationships"] = relationships

        return analysis_report

    def _analyze_single_sheet(self, sheet_name: str, values: List[List[Any]], formulas: List[List[Any]], props: Dict[str, Any]) -> Dict[str, Any]:
        total_rows = len(values)
        total_cols = max((len(r) for r in values), default=0)

        result = {
            "sheet_name": sheet_name,
            "headers": [],
            "header_rows": [],
            "data_start_row": None,
            "row_count": total_rows,
            "column_count": total_cols,
            "merged_ranges": [],
            "formula_columns": [],
            "date_columns": [],
            "product_key_candidates": [],
            "unit_price_candidates": [],
            "amount_columns": [],
            "stock_columns": [],
            "special_values": [],
            "sample_keys": [],
            "issues": []
        }

        if total_rows == 0:
            result["issues"].append("Sheet is completely empty")
            return result

        # Detect Header Row:
        # In inventory sheets, row 0 often has high-level group dates, while row 1 has detailed column headers:
        # e.g. ["Sl No", "Description", "Part No", "Category", "UOM", "Opening Stock", "Unit Price", "Amount"]
        header_row_idx = None
        for i in range(min(5, total_rows)):
            row = values[i]
            row_str = " ".join([str(c).lower() for c in row if c is not None])
            # If row contains description or part no or sl no, it is the primary header row!
            if any(term in row_str for term in ["description", "part no", "part_no", "item code", "particulars", "sl no", "sl.no"]):
                header_row_idx = i
                break

        if header_row_idx is None:
            # Fallback: search for row with most text entries
            best_count = 0
            for i in range(min(5, total_rows)):
                count = sum(1 for c in values[i] if isinstance(c, str) and len(c.strip()) > 1)
                if count > best_count:
                    best_count = count
                    header_row_idx = i

        if header_row_idx is None:
            header_row_idx = 0

        result["header_rows"] = [header_row_idx + 1]
        headers = [str(c).strip() for c in values[header_row_idx]]
        result["headers"] = headers
        result["data_start_row"] = header_row_idx + 2

        data_rows = values[header_row_idx + 1:]

        # Column-by-column classification
        for col_idx, header in enumerate(headers):
            h_clean = header.lower().strip()
            
            # 1. Amount Detection (CRITICAL: must never be shown to frontend)
            if any(kw in h_clean for kw in AMOUNT_KEYWORDS) and not any(kw in h_clean for kw in ["unit", "rate"]):
                result["amount_columns"].append(header)

            # 2. Unit Price Detection (Separate from amount)
            elif any(kw in h_clean for kw in UNIT_PRICE_KEYWORDS):
                result["unit_price_candidates"].append(header)

            # 3. Product Key Candidates
            if any(kw in h_clean for kw in PRODUCT_KEY_KEYWORDS):
                result["product_key_candidates"].append(header)

            # 4. Stock / Quantity Columns
            if any(kw in h_clean for kw in STOCK_KEYWORDS):
                result["stock_columns"].append(header)

            # 5. Check cell values in this column for date, special values, and duplicates
            col_cells = []
            for row in data_rows:
                if col_idx < len(row):
                    col_cells.append(row[col_idx])
                else:
                    col_cells.append(None)

            # Date check
            date_matches = 0
            for val in col_cells:
                val_str = str(val).strip() if val is not None else ""
                if any(re.match(pat, val_str) for pat in DATE_PATTERNS):
                    date_matches += 1
            if date_matches > 0 and date_matches >= len(col_cells) * 0.4:
                result["date_columns"].append(header)

            # Special values check
            for val in col_cells:
                val_str = str(val).strip()
                if val_str in SPECIAL_LITERALS:
                    if val_str not in result["special_values"]:
                        result["special_values"].append(val_str)

        # Check for formula columns
        if formulas:
            for r_idx, row in enumerate(formulas):
                for c_idx, cell in enumerate(row):
                    if isinstance(cell, str) and cell.startswith("="):
                        if c_idx < len(headers):
                            h_name = headers[c_idx]
                            if h_name not in result["formula_columns"]:
                                result["formula_columns"].append(h_name)

        # Extract sample product keys & check duplicates
        if result["product_key_candidates"]:
            pk_col = result["product_key_candidates"][0]
            pk_idx = headers.index(pk_col)
            keys = []
            seen = set()
            duplicates = set()
            for r in data_rows:
                if pk_idx < len(r):
                    key = str(r[pk_idx]).strip()
                    if key and key not in SPECIAL_LITERALS:
                        keys.append(key)
                        if key in seen:
                            duplicates.add(key)
                        seen.add(key)
            result["sample_keys"] = keys[:10]
            if duplicates:
                result["issues"].append(f"Duplicate product keys found in column '{pk_col}': {list(duplicates)[:5]}")

        # Check for empty headers
        for idx, h in enumerate(headers):
            if not h:
                result["issues"].append(f"Column at index {idx + 1} has an empty header name")

        return result
