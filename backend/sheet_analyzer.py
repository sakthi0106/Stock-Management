import re
from typing import Dict, List, Any, Optional

DATE_PATTERNS = [
    r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}',
    r'^\d{1,2}[-/]\d{1,2}[-/]\d{4}',
    r'^\d{4}\.\d{1,2}\.\d{1,2}'
]

SPECIAL_LITERALS = {'N/A', '-', 'NA', 'N.A.'}

AMOUNT_KEYWORDS = [
    'amount', 'total amount', 'total cost', 'total price', 'line total',
    'cost total', 'ext price', 'extended price', 'val', 'value'
]

UNIT_PRICE_KEYWORDS = [
    'unit price', 'unit cost', 'rate', 'price', 'price/unit',
    'unit_price', 'rate (rs)', 'rate/unit'
]

PRODUCT_KEY_KEYWORDS = [
    'product id', 'product_id', 'product code', 'part no', 'part_no',
    'item code', 'item no', 'sku', 'code'
]

STOCK_KEYWORDS = [
    'stock', 'current stock', 'balance', 'qty', 'quantity',
    'closing stock', 'opening stock', 'in_qty', 'out_qty', 'inward',
    'outward', 'received', 'issued'
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
        if metadata is None:
            metadata = self.client.get_spreadsheet_metadata()

        sheets_info = metadata.get('sheets', [])
        sheet_names = [
            s.get('properties', {}).get('title', '')
            for s in sheets_info
            if s.get('properties', {}).get('title')
        ]

        if raw_values is None:
            raw_values = self.client.get_batch_sheet_values(sheet_names)

        if raw_formulas is None:
            raw_formulas = {s: [] for s in sheet_names}

        analyzed_sheets = {}
        for s in sheets_info:
            props = s.get('properties', {})
            sname = props.get('title', '')
            if not sname:
                continue
            vals = raw_values.get(sname, [])
            forms = raw_formulas.get(sname, [])
            analyzed_sheets[sname] = self._analyze_single_sheet(sname, vals, forms, props)

        return {
            "spreadsheet_title": metadata.get('properties', {}).get('title', 'Untitled Spreadsheet'),
            "total_sheets": len(analyzed_sheets),
            "sheets_count": len(analyzed_sheets),
            "sheets": analyzed_sheets
        }

    def _analyze_single_sheet(
        self,
        sheet_name: str,
        values: List[List[Any]],
        formulas: Optional[List[List[Any]]] = None,
        props: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        total_rows = len(values)
        total_cols = max((len(r) for r in values), default=0)

        result: Dict[str, Any] = {
            "sheet_name": sheet_name,
            "headers": [],
            "header_rows": [2],
            "data_start_row": 3,
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

        # Detect best header row
        best_count = 0
        header_row_idx = 1 if total_rows > 1 else 0
        for i in range(min(4, total_rows)):
            row = values[i]
            count = sum(1 for c in row if str(c).strip())
            if count > best_count:
                best_count = count
                header_row_idx = i

        result["header_rows"] = [header_row_idx + 1]
        result["data_start_row"] = header_row_idx + 2

        headers = [str(c).strip() if c is not None else "" for c in values[header_row_idx]]
        while len(headers) < total_cols:
            headers.append(f"Column_{len(headers) + 1}")
        result["headers"] = headers

        data_rows = values[result["data_start_row"] - 1:]

        for col_idx, header in enumerate(headers):
            h_lower = header.lower()
            if not header and col_idx < len(headers) - 1:
                result["issues"].append(f"Column at index {col_idx} has an empty header name")

            col_cells = [r[col_idx] for r in data_rows if len(r) > col_idx]

            # Date check
            date_matches = 0
            for val in col_cells[:15]:
                val_str = str(val).strip()
                if any(re.search(p, val_str) for p in DATE_PATTERNS):
                    date_matches += 1
            if date_matches >= 2 or any(w in h_lower for w in ['date', 'day']):
                result["date_columns"].append(header or f"Col_{col_idx}")

            # Amount check
            if any(k in h_lower for k in AMOUNT_KEYWORDS):
                result["amount_columns"].append(header)

            # Unit price check
            if any(k in h_lower for k in UNIT_PRICE_KEYWORDS):
                result["unit_price_candidates"].append(header)

            # Product key check
            if any(k in h_lower for k in PRODUCT_KEY_KEYWORDS):
                result["product_key_candidates"].append(header)

            # Stock check
            if any(k in h_lower for k in STOCK_KEYWORDS):
                result["stock_columns"].append(header)

        # Fallback for product key candidate
        if not result["product_key_candidates"] and len(headers) > 0:
            result["product_key_candidates"].append(headers[0])

        # Check duplicate keys in primary product key column
        pk_col = result["product_key_candidates"][0] if result["product_key_candidates"] else ""
        if pk_col and pk_col in headers:
            pk_idx = headers.index(pk_col)
            keys = [str(r[pk_idx]).strip() for r in data_rows if len(r) > pk_idx and str(r[pk_idx]).strip()]
            seen = set()
            duplicates = set()
            for k in keys:
                if k in seen:
                    duplicates.add(k)
                seen.add(k)
            if duplicates:
                result["issues"].append(f"Duplicate product keys found in column '{pk_col}': {list(duplicates)[:5]}")
            result["sample_keys"] = keys[:5]

        # Collect special literal values (NA, -, etc.)
        special_vals = set()
        for r in data_rows:
            for c in r:
                c_str = str(c).strip() if c is not None else ""
                if c_str in SPECIAL_LITERALS:
                    special_vals.add(c_str)
        result["special_values"] = list(special_vals)

        return result
