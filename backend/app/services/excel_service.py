"""
Excel Workbook Inspection and Parsing Service
Uses openpyxl in read-only and data-only mode to prevent file locks and read calculated formulas.
"""
import os
import hashlib
import io
import re
from typing import Dict, List, Any, Optional, Tuple
import openpyxl
from datetime import date, datetime

class ExcelService:
    @staticmethod
    def _normalize_header(value: Any) -> str:
        if value is None:
            return ""
        return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())

    @staticmethod
    def _parse_date(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        if isinstance(value, str):
            for date_format in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"):
                try:
                    return datetime.strptime(value.strip(), date_format)
                except ValueError:
                    continue
        return None

    @staticmethod
    def detect_daily_stock_layout(
        header_row: Tuple[Any, ...],
        date_row: Tuple[Any, ...]
    ) -> Optional[Dict[str, Any]]:
        """Detect the row-per-material, date-grouped stock register layout."""
        normalized_headers = [ExcelService._normalize_header(value) for value in header_row]
        normalized_dates = [ExcelService._normalize_header(value) for value in date_row]

        def find_column(aliases: set[str]) -> Optional[int]:
            return next(
                (index for index, value in enumerate(normalized_headers) if value in aliases),
                None
            )

        product_name_col = find_column({"description", "productname", "itemname", "material"})
        product_code_col = find_column({
            "partno", "partnumber", "productcode", "itemcode", "sku", "p"
        })
        category_col = find_column({"category"})
        unit_col = find_column({"uom", "unit", "unitofmeasure"})
        if any(col is None for col in (product_name_col, product_code_col, category_col, unit_col)):
            return None

        dated_groups = []
        for index, value in enumerate(date_row):
            parsed_date = ExcelService._parse_date(value)
            if parsed_date is None or index + 2 >= len(normalized_headers):
                continue
            group_headers = normalized_headers[index:index + 3]
            if group_headers[0].startswith("openingstock") and group_headers[1:] == ["in", "out"]:
                dated_groups.append({
                    "date": parsed_date,
                    "opening_col": index,
                    "inward_col": index + 1,
                    "outward_col": index + 2,
                })

        first_date_col = min((group["opening_col"] for group in dated_groups), default=len(header_row))
        opening_stock_col = next(
            (
                index for index, value in enumerate(normalized_headers[:first_date_col])
                if value == "openingstock" and normalized_dates[index] == "openingstock"
            ),
            None
        )
        unit_cost_col = find_column({"unitprice", "unitcost", "price", "rate"})
        if opening_stock_col is None or not dated_groups:
            return None

        current_date = date.today()
        dated_groups = [
            group for group in dated_groups
            if group["date"].date() <= current_date
        ]
        if not dated_groups:
            return None

        return {
            "header_row_index": 2,
            "product_name_col": product_name_col,
            "product_code_col": product_code_col,
            "category_col": category_col,
            "unit_col": unit_col,
            "opening_stock_col": opening_stock_col,
            "unit_cost_col": unit_cost_col,
            "dated_groups": sorted(dated_groups, key=lambda group: group["date"]),
        }

    @staticmethod
    def parse_daily_stock_sheet(
        file_bytes: bytes,
        sheet_name: str
    ) -> Optional[Dict[str, Any]]:
        """Parse a daily stock register with material rows and dated IN/OUT columns."""
        file_obj = io.BytesIO(file_bytes)
        wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
        worksheet_names = [worksheet.title for worksheet in wb.worksheets]
        if sheet_name not in worksheet_names:
            wb.close()
            raise ValueError(f"Worksheet '{sheet_name}' not found in workbook. Available: {worksheet_names}")

        ws = wb[sheet_name]
        header_row = next(ws.iter_rows(min_row=2, max_row=2, values_only=True), ())
        date_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
        layout = ExcelService.detect_daily_stock_layout(header_row, date_row)
        if layout is None:
            wb.close()
            return None

        products = []
        errors = []
        def read_number(value: Any, row_index: int, field: str, default: Optional[float] = 0.0) -> Optional[float]:
            if value is None or value == "":
                return default
            try:
                number = float(str(value).replace(",", "").replace("$", "").strip())
                if number != number or number in (float("inf"), float("-inf")):
                    raise ValueError("not finite")
                return number
            except (TypeError, ValueError):
                errors.append({
                    "sheet_name": sheet_name,
                    "row_index": row_index,
                    "field": field,
                    "reason": f"Invalid numeric value '{value}'",
                })
                return default

        for row_index, row in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
            if not any(value is not None for value in row):
                continue

            code_value = row[layout["product_code_col"]] if layout["product_code_col"] < len(row) else None
            if code_value is None or not str(code_value).strip():
                continue

            def cell(column: int) -> Any:
                return row[column] if column < len(row) else None

            stock_errors_before = len(errors)
            opening = read_number(cell(layout["opening_stock_col"]), row_index, "opening_stock") or 0.0
            dated_rows = []
            total_inward = 0.0
            total_outward = 0.0
            for group in layout["dated_groups"]:
                day_opening = read_number(cell(group["opening_col"]), row_index, "daily_opening_stock") or 0.0
                inward = read_number(cell(group["inward_col"]), row_index, "inward_qty") or 0.0
                outward = read_number(cell(group["outward_col"]), row_index, "outward_qty") or 0.0
                total_inward += inward
                total_outward += outward
                dated_rows.append({
                    "date": group["date"],
                    "opening_stock": day_opening,
                    "inward_qty": inward,
                    "outward_qty": outward,
                    "balance": day_opening + inward - outward,
                })

            if len(errors) > stock_errors_before:
                continue

            unit_cost = (
                read_number(cell(layout["unit_cost_col"]), row_index, "unit_cost", None)
                if layout["unit_cost_col"] is not None else None
            )

            latest_day = dated_rows[-1]
            movements = []
            last_movement_date = None
            for day in dated_rows:
                if day["inward_qty"] != 0:
                    movements.append({
                        "row_index": row_index,
                        "product_code": str(code_value).strip(),
                        "transaction_date": day["date"],
                        "transaction_type": "INWARD",
                        "quantity": day["inward_qty"],
                        "balance_after": day["opening_stock"] + day["inward_qty"],
                    })
                    last_movement_date = day["date"]
                if day["outward_qty"] != 0:
                    movements.append({
                        "row_index": row_index,
                        "product_code": str(code_value).strip(),
                        "transaction_date": day["date"],
                        "transaction_type": "OUTWARD",
                        "quantity": day["outward_qty"],
                        "balance_after": day["balance"],
                    })
                    last_movement_date = day["date"]

            products.append({
                "row_index": row_index,
                "product_code": str(code_value).strip(),
                "product_name": str(cell(layout["product_name_col"]) or str(code_value)).strip(),
                "category": str(cell(layout["category_col"]) or sheet_name).strip(),
                "unit": str(cell(layout["unit_col"]) or "PCS").strip().upper(),
                "opening_stock": opening,
                "total_inward": total_inward,
                "total_outward": total_outward,
                "current_balance": latest_day["balance"],
                "unit_cost": unit_cost,
                "last_movement_date": last_movement_date,
                "movements": movements,
            })

        wb.close()
        return {
            "layout": layout,
            "products": products,
            "errors": errors,
        }

    @staticmethod
    def calculate_file_hash(file_bytes: bytes) -> str:
        """Calculate SHA-256 hash of workbook content."""
        return hashlib.sha256(file_bytes).hexdigest()

    @staticmethod
    def inspect_workbook(file_bytes: bytes, file_name: str) -> Dict[str, Any]:
        """Inspect sheet names, headers, and sample data without modifying anything."""
        file_hash = ExcelService.calculate_file_hash(file_bytes)
        file_obj = io.BytesIO(file_bytes)
        wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
        
        sheet_inspections = []
        recommendations = {}
        for ws in wb.worksheets:
            name = ws.title
            sample_rows = []
            headers = []
            row_one = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
            row_two = next(ws.iter_rows(min_row=2, max_row=2, values_only=True), ())
            daily_layout = ExcelService.detect_daily_stock_layout(row_two, row_one)

            row_count = 0
            for r_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
                row_count += 1
                row_values = [str(v) if v is not None else "" for v in row]
                header_row_index = daily_layout["header_row_index"] if daily_layout else 1
                if r_idx == header_row_index:
                    headers = [str(v).strip() if v is not None else f"Column_{i+1}" for i, v in enumerate(row)]
                elif header_row_index < r_idx <= header_row_index + 4:
                    sample_rows.append(row_values)

            sheet_inspections.append({
                "sheet_name": name,
                "total_rows": row_count,
                "total_cols": len(headers),
                "sample_headers": headers,
                "sample_rows": sample_rows,
                "header_row_index": daily_layout["header_row_index"] if daily_layout else 1,
            })

            if daily_layout:
                recommendations[name] = {
                    "likely_sheet_type": "DAILY_STOCK_REGISTER",
                    "header_row_index": daily_layout["header_row_index"],
                    "mappings": {
                        "product_name_col": headers[daily_layout["product_name_col"]],
                        "product_code_col": headers[daily_layout["product_code_col"]],
                        "category_col": headers[daily_layout["category_col"]],
                        "unit_col": headers[daily_layout["unit_col"]],
                        "opening_stock_col": headers[daily_layout["opening_stock_col"]],
                    },
                }
            
        wb.close()
        
        # Intelligent column recommendations
        recommendations.update(ExcelService.auto_detect_mapping([
            sheet for sheet in sheet_inspections
            if sheet["sheet_name"] not in recommendations
        ]))
        
        return {
            "file_name": file_name,
            "file_hash": file_hash,
            "sheets": sheet_inspections,
            "detected_recommendations": recommendations
        }

    @staticmethod
    def auto_detect_mapping(sheet_inspections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Auto-detect columns based on standard enterprise inventory terms."""
        mapping_rules = {
            "product_code_col": ["product code", "item code", "code", "sku", "part number", "part no", "product id", "item id"],
            "product_name_col": ["product name", "item name", "description", "product description", "item description", "material"],
            "category_col": ["category", "group", "product group", "item category", "type"],
            "unit_col": ["unit of measure", "unit", "uom", "measurement", "units"],
            "current_balance_col": ["current balance", "balance", "closing stock", "stock balance", "qty on hand", "balance quantity", "current stock"],
            "opening_stock_col": ["opening stock", "opening balance", "opening qty", "initial stock"],
            "inward_qty_col": ["total inward", "quantity received", "inward quantity", "qty received", "inward qty", "received qty", "inward", "receipt"],
            "outward_qty_col": ["total outward", "quantity issued", "outward quantity", "qty issued", "outward qty", "issued qty", "outward", "dispatch"],
            "min_threshold_col": ["min threshold", "minimum stock", "reorder level", "safety stock", "threshold", "min stock"],
            "unit_cost_col": ["unit cost", "cost", "unit price", "price", "rate"],
            "location_col": ["location / bin", "location", "bin", "storage location", "aisle", "rack"],
            "date_col": ["transaction date", "date", "movement date", "posting date", "entry date"],
            "ref_col": ["transaction id", "po number", "work order / project", "reference", "doc ref", "po no", "challan"],
            "party_col": ["supplier name", "issued to / department", "supplier", "department", "vendor", "customer"],
            "remarks_col": ["remarks", "notes", "comment", "reason"]
        }
        
        recommendations = {}
        for s in sheet_inspections:
            sheet_name = s["sheet_name"]
            headers_lower = [h.lower().strip() for h in s["sample_headers"]]
            detected_for_sheet = {}
            
            for field, aliases in mapping_rules.items():
                for alias in aliases:
                    for i, h in enumerate(headers_lower):
                        if alias == h or (alias in h and len(alias) > 3):
                            detected_for_sheet[field] = s["sample_headers"][i]
                            break
                    if field in detected_for_sheet:
                        break
                        
            # Determine likely sheet type
            sheet_type = "SUMMARY"
            lower_name = sheet_name.lower()
            if "inward" in lower_name or "receipt" in lower_name:
                sheet_type = "INWARD_REGISTER"
            elif "outward" in lower_name or "issue" in lower_name or "dispatch" in lower_name:
                sheet_type = "OUTWARD_REGISTER"
            elif "ledger" in lower_name or "movement" in lower_name or "transaction" in lower_name:
                sheet_type = "LEDGER"
            elif "summary" in lower_name or "master" in lower_name or "balance" in lower_name:
                sheet_type = "SUMMARY"
                
            recommendations[sheet_name] = {
                "likely_sheet_type": sheet_type,
                "mappings": detected_for_sheet
            }
            
        return recommendations

    @staticmethod
    def parse_sheet_rows(
        file_bytes: bytes,
        sheet_name: str,
        header_row_index: int,
        column_mapping: Dict[str, str]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Parses rows from specified sheet using column mappings.
        Returns: (valid_rows, validation_errors)
        """
        file_obj = io.BytesIO(file_bytes)
        wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
        worksheet_names = [worksheet.title for worksheet in wb.worksheets]
        if sheet_name not in worksheet_names:
            wb.close()
            raise ValueError(f"Worksheet '{sheet_name}' not found in workbook. Available: {worksheet_names}")
            
        ws = wb[sheet_name]
        headers = []
        valid_rows = []
        errors = []
        
        # Build inverted column map: header_name -> field_name
        col_to_field = {v.strip().lower(): k for k, v in column_mapping.items() if v}
        header_col_indices = {}
        
        for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if row_idx < header_row_index:
                continue
            if row_idx == header_row_index:
                headers = [str(c).strip() if c is not None else "" for c in row]
                for col_idx, h in enumerate(headers):
                    if h.lower() in col_to_field:
                        header_col_indices[col_to_field[h.lower()]] = col_idx
                continue
                
            # Row data processing
            if not any(row):
                # Skip empty row
                continue
                
            row_dict = {}
            for field, col_idx in header_col_indices.items():
                if col_idx < len(row):
                    val = row[col_idx]
                    row_dict[field] = val
                else:
                    row_dict[field] = None
                    
            product_code = row_dict.get("product_code_col")
            if not product_code or str(product_code).strip() == "":
                errors.append({
                    "row_index": row_idx,
                    "field": "product_code_col",
                    "reason": "Missing or blank Product Identifier/Code",
                    "raw_data": str(row[:6])
                })
                continue
                
            # Clean and sanitize values
            cleaned = {"row_index": row_idx, "product_code": str(product_code).strip()}
            
            # Numeric fields
            numeric_fields = [
                ("current_balance_col", "current_balance", 0.0),
                ("opening_stock_col", "opening_stock", 0.0),
                ("inward_qty_col", "inward_qty", 0.0),
                ("outward_qty_col", "outward_qty", 0.0),
                ("min_threshold_col", "min_threshold", 0.0),
                ("unit_cost_col", "unit_cost", None),
            ]
            
            for map_key, target_field, default_val in numeric_fields:
                raw_v = row_dict.get(map_key)
                if raw_v is None or raw_v == "":
                    cleaned[target_field] = default_val
                else:
                    try:
                        # Strip currency symbols, commas
                        cleaned_str = str(raw_v).replace("$", "").replace(",", "").strip()
                        cleaned[target_field] = float(cleaned_str)
                    except (ValueError, TypeError):
                        errors.append({
                            "row_index": row_idx,
                            "field": map_key,
                            "reason": f"Invalid numeric value '{raw_v}'",
                            "raw_data": str(raw_v)
                        })
                        cleaned[target_field] = default_val
                        
            # Text fields
            cleaned["product_name"] = str(row_dict.get("product_name_col") or cleaned["product_code"]).strip()
            cleaned["category"] = str(row_dict.get("category_col") or "General").strip()
            cleaned["unit"] = str(row_dict.get("unit_col") or "PCS").strip().upper()
            cleaned["bin_location"] = str(row_dict.get("location_col") or "").strip() or None
            cleaned["remarks"] = str(row_dict.get("remarks_col") or "").strip() or None
            cleaned["party"] = str(row_dict.get("party_col") or "").strip() or None
            cleaned["reference"] = str(row_dict.get("ref_col") or "").strip() or None
            
            # Date field handling
            raw_date = row_dict.get("date_col")
            if isinstance(raw_date, datetime):
                cleaned["date"] = raw_date
            elif raw_date:
                try:
                    cleaned["date"] = datetime.strptime(str(raw_date).strip(), "%Y-%m-%d")
                except Exception:
                    try:
                        cleaned["date"] = datetime.strptime(str(raw_date).strip(), "%d-%m-%Y")
                    except Exception:
                        cleaned["date"] = datetime.now()
            else:
                cleaned["date"] = datetime.now()
                
            valid_rows.append(cleaned)
            
        wb.close()
        return valid_rows, errors
