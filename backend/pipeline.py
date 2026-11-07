import re
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Set
import database
from spreadsheet_reader import UniversalSpreadsheetReader
from intelligence_engine import IntelligenceEngine, ROLE_SYNONYMS

logger = logging.getLogger(__name__)

FORBIDDEN_KEYWORDS = ['amount', 'total cost', 'total price', 'closing value', 'total value', 'closing stk val', 'amount (rs)']
SPECIAL_STRINGS = {'N/A', '-', 'NA', 'N.A.', 'nil', 'none', 'null'}

IN_KEYWORDS = [
    'in', 'inward', 'received', 'receipt', 'receipts', 'total in', 'in qty',
    'in_qty', 'incoming', 'purchase qty', 'inwards', 'qty in', 'quantity received',
    'total receipts', 'rec qty', 'rcvd', 'receipt qty'
]

OUT_KEYWORDS = [
    'out', 'outward', 'issued', 'issue', 'issues', 'total out', 'out qty',
    'out_qty', 'dispatch', 'outgoing', 'sales qty', 'outwards', 'qty out',
    'quantity issued', 'total issue', 'consumption qty', 'iss qty', 'dispatch qty'
]


class UnifiedDataPipeline:
    """End-to-End Dynamic Data Pipeline:
    Spreadsheet Source -> Dynamic Extraction -> Dynamic Schema Detection -> Data Validation -> Operational PostgreSQL/SQLite DB.
    
    Powers Dashboard, Inventory Master, and Stock Movements simultaneously from validated spreadsheet data.
    """

    def __init__(self, intelligence_engine: Optional[IntelligenceEngine] = None):
        self.engine = intelligence_engine or IntelligenceEngine()

    @staticmethod
    def is_amount_field(field_name: str) -> bool:
        fn = str(field_name).strip().lower()
        return any(k in fn for k in FORBIDDEN_KEYWORDS)

    @staticmethod
    def parse_number_or_preserve(val: Any) -> Any:
        if val is None:
            return None
        val_str = str(val).strip()
        if not val_str:
            return None
        if val_str.upper() in SPECIAL_STRINGS:
            return val_str
        cleaned = re.sub(r'[,\$ ]', '', val_str).replace('₹', '').replace('Rs.', '').replace('Rs', '')
        try:
            f = float(cleaned)
            if f.is_integer():
                return int(f)
            return f
        except ValueError:
            return val_str

    @staticmethod
    def parse_date_string(val: Any) -> Optional[str]:
        if val is None:
            return None
        s = str(val).strip()
        if not s or s.upper() in SPECIAL_STRINGS:
            return None

        # Matches YYYY-MM-DD or YYYY/MM/DD or YYYY.MM.DD
        m1 = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', s)
        if m1:
            y, m, d = m1.groups()
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

        # Matches DD-MM-YYYY or DD/MM/YYYY or DD.MM.YYYY
        m2 = re.search(r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})', s)
        if m2:
            d, m, y = m2.groups()
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

        # Matches DD-MMM, DD-MMM-YYYY, e.g. 01-Nov, 01-Nov-2026, 1-Oct
        m3 = re.search(r'(\d{1,2})[- ]([a-zA-Z]{3})(?:[- ](\d{2,4}))?', s)
        if m3:
            day, mon, yr = m3.groups()
            months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                      'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
            mon_lower = mon.lower()
            if mon_lower in months:
                m_num = months[mon_lower]
                y_num = int(yr) if yr else 2026
                if y_num < 100:
                    y_num += 2000
                return f"{y_num:04d}-{m_num:02d}-{int(day):02d}"

        return None

    def process_and_persist(
        self,
        source_id: str,
        raw_sheets_dict: Dict[str, List[List[Any]]],
        fingerprint: str = "",
        period: str = ""
    ) -> Dict[str, Any]:
        """Atomically processes spreadsheet data, runs dynamic schema detection,
        and synchronizes dynamic_records, inventory_records, and stock_movements.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        database.cleanup_deleted_worksheets(source_id, set(raw_sheets_dict.keys()))

        total_worksheets = len(raw_sheets_dict)
        total_dynamic_records = 0
        all_inventory_records: List[Dict[str, Any]] = []
        all_stock_movements: List[Dict[str, Any]] = []

        for sname, s_values in raw_sheets_dict.items():
            if not s_values:
                continue

            header_rows, headers, data_start_row = UniversalSpreadsheetReader.detect_header_rows(s_values)
            profile = self.engine.profile_worksheet(
                sheet_name=sname,
                values=s_values,
                header_rows=header_rows,
                headers=headers,
                data_start_row=data_start_row
            )

            # Persist worksheet analysis & dynamic columns
            database.save_worksheet_analysis(source_id, profile)

            data_rows = s_values[data_start_row - 1:] if len(s_values) >= data_start_row else []
            database.save_dynamic_records(source_id, sname, headers, data_rows)
            total_dynamic_records += len(data_rows)

            # Build semantic role lookup
            role_to_col: Dict[str, str] = {}
            col_to_role: Dict[str, str] = {}

            for col in profile.get("columns", []):
                col_name = col.get("original_name", "")
                role = col.get("inferred_role", "unknown")
                col_to_role[col_name] = role
                if role != "unknown" and role not in role_to_col:
                    role_to_col[role] = col_name

            # Transform raw records into operational inventory & movement records
            inv_items, mov_items = self._transform_worksheet_records(
                source_id=source_id,
                sheet_name=sname,
                headers=headers,
                data_rows=data_rows,
                role_to_col=role_to_col,
                col_to_role=col_to_role,
                period=period,
                now_iso=now_iso
            )

            all_inventory_records.extend(inv_items)
            all_stock_movements.extend(mov_items)

        # Atomically replace inventory_records and stock_movements
        database.replace_source_snapshot(
            source_id=source_id,
            period=period,
            products=all_inventory_records,
            movements=all_stock_movements,
            fingerprint=fingerprint
        )

        database.update_source_intelligence_status(
            source_id,
            status="completed",
            total_sheets=total_worksheets,
            total_records=total_dynamic_records
        )

        return {
            "source_id": source_id,
            "total_sheets": total_worksheets,
            "total_dynamic_records": total_dynamic_records,
            "total_inventory_records": len(all_inventory_records),
            "total_stock_movements": len(all_stock_movements),
            "fingerprint": fingerprint
        }

    def _transform_worksheet_records(
        self,
        source_id: str,
        sheet_name: str,
        headers: List[str],
        data_rows: List[List[Any]],
        role_to_col: Dict[str, str],
        col_to_role: Dict[str, str],
        period: str,
        now_iso: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Convert dynamic records into operational inventory records and stock movements supporting:
        - Structure A: Date-based stock columns (e.g. '01-Nov IN', '01-Nov OUT', '2026-10-01 IN', etc.)
        - Structure B: Transaction-based rows with date, type (IN/OUT), and quantity columns
        - Structure C: Summary rows with Inward / Outward columns
        """
        inventory_records = []
        stock_movements = []

        # Discover all date-based IN / OUT columns (Structure A)
        date_in_out_columns: List[Tuple[int, str, str, str]] = [] # (col_idx, header, date_str, 'IN'|'OUT')
        for c_idx, h in enumerate(headers):
            dt = self.parse_date_string(h)
            if not dt:
                continue
            hl = h.lower()
            # Must be an IN or OUT column without being an opening or closing stock column
            is_in = any(w in hl for w in IN_KEYWORDS) and not any(w in hl for w in ['open', 'closing', 'out', 'balance'])
            is_out = any(w in hl for w in OUT_KEYWORDS) and not any(w in hl for w in ['open', 'closing', 'inward', 'balance'])
            if is_in:
                date_in_out_columns.append((c_idx, h, dt, 'IN'))
            elif is_out:
                date_in_out_columns.append((c_idx, h, dt, 'OUT'))

        # Check for Transaction-based columns (Structure B)
        # 1. Date column
        date_col_name = role_to_col.get("date")
        if not date_col_name:
            for h in headers:
                hl = h.lower()
                if any(w in hl for w in ['date', 'txn date', 'transaction date', 'entry date']) and not any(w in hl for w in ['in', 'out', 'stock']):
                    date_col_name = h
                    break

        # 2. Movement Type column (IN/OUT)
        type_col_name = None
        for h in headers:
            hl = h.lower()
            if hl in ['type', 'movement type', 'movement_type', 'txn type', 'transaction type', 'in/out', 'in / out']:
                type_col_name = h
                break

        # 3. Transaction Qty column
        qty_col_name = None
        for h in headers:
            hl = h.lower()
            if hl in ['qty', 'quantity', 'movement qty', 'movement quantity', 'units']:
                qty_col_name = h
                break

        # 4. Inward Qty / Outward Qty individual columns
        in_col_name = role_to_col.get("in_qty")
        out_col_name = role_to_col.get("out_qty")
        if not in_col_name:
            for h in headers:
                hl = h.lower()
                if any(k == hl or f" {k}" in hl or f"{k} " in hl for k in IN_KEYWORDS) and not any(w in hl for w in ['open', 'closing', 'balance', 'out', 'date']):
                    in_col_name = h
                    break
        if not out_col_name:
            for h in headers:
                hl = h.lower()
                if any(k == hl or f" {k}" in hl or f"{k} " in hl for k in OUT_KEYWORDS) and not any(w in hl for w in ['open', 'closing', 'balance', 'in', 'date']):
                    out_col_name = h
                    break

        # 5. Reference number column
        ref_col_name = None
        for h in headers:
            hl = h.lower()
            if any(w in hl for w in ['ref', 'reference', 'po number', 'challan', 'invoice', 'voucher', 'work order']):
                ref_col_name = h
                break

        # 6. Party / Supplier / Customer column
        party_col_name = None
        for h in headers:
            hl = h.lower()
            if any(w in hl for w in ['supplier', 'vendor', 'party', 'customer', 'issued to', 'received from', 'department']):
                party_col_name = h
                break

        for row_idx, r in enumerate(data_rows, start=1):
            if not r or not any(str(c).strip() for c in r):
                continue

            raw_dict = {}
            for c_idx, h in enumerate(headers):
                val = r[c_idx] if c_idx < len(r) else ""
                raw_dict[h] = val

            # Semantic values
            part_no = str(raw_dict.get(role_to_col.get("product_id", ""), "")).strip()
            desc = str(raw_dict.get(role_to_col.get("description", ""), "")).strip()
            cat = str(raw_dict.get(role_to_col.get("category", ""), "")).strip() or sheet_name
            uom = str(raw_dict.get(role_to_col.get("uom", ""), "")).strip() or "NOS"
            unit_price_raw = raw_dict.get(role_to_col.get("unit_price", ""), "NA")
            opening_raw = raw_dict.get(role_to_col.get("opening_stock", ""), 0)
            closing_raw = raw_dict.get(role_to_col.get("closing_stock", ""), None)

            # Skip header repeats, totals or blank rows
            if not part_no and not desc:
                continue
            if part_no.upper() in ["TOTAL", "SUBTOTAL", "GRAND TOTAL"]:
                continue

            unit_price = self.parse_number_or_preserve(unit_price_raw) or "NA"
            opening_stock = self.parse_number_or_preserve(opening_raw) or 0
            current_stock = self.parse_number_or_preserve(closing_raw) if closing_raw is not None else opening_stock

            min_level = 10.0
            status = "In Stock"
            if isinstance(current_stock, (int, float)):
                if current_stock <= 0:
                    status = "Out of Stock"
                elif current_stock <= min_level:
                    status = "Low Stock"
            elif str(current_stock).strip().upper() in SPECIAL_STRINGS:
                status = "Unknown"

            # Dynamic extra fields: preserve every non-amount column
            extra_fields = {}
            for k, v in raw_dict.items():
                if not self.is_amount_field(k):
                    extra_fields[k] = self.parse_number_or_preserve(v)

            p_id = part_no if part_no and part_no not in SPECIAL_STRINGS else f"{sheet_name}_R{row_idx}"

            inv_item = {
                "source_id": source_id,
                "source_sheet": sheet_name,
                "source_row": row_idx,
                "product_id": p_id,
                "part_no": part_no or f"ITEM-{row_idx}",
                "description": desc or part_no or f"Product {row_idx}",
                "category": cat,
                "uom": uom,
                "unit_price": unit_price,
                "opening_stock": opening_stock,
                "current_stock": current_stock,
                "latest_date": now_iso[:10],
                "min_level": min_level,
                "stock_status": status,
                "period": period,
                "extra_fields": extra_fields,
                "validation_flags": []
            }
            inventory_records.append(inv_item)

            ref_no = str(raw_dict.get(ref_col_name, "")).strip() if ref_col_name else ""
            party_name = str(raw_dict.get(party_col_name, "")).strip() if party_col_name else ""

            # -------------------------------------------------------------
            # Stock Movements Extraction
            # -------------------------------------------------------------

            # Mode 1: Structure A — Date-based IN and OUT columns across headers
            if date_in_out_columns:
                for col_idx, col_header, col_date, col_mov_type in date_in_out_columns:
                    cell_val = raw_dict.get(col_header)
                    parsed_val = self.parse_number_or_preserve(cell_val)
                    if isinstance(parsed_val, (int, float)) and parsed_val > 0:
                        clean_col_id = re.sub(r'[^a-zA-Z0-9]+', '_', col_header)
                        mov_id = f"{source_id}_{sheet_name}_{row_idx}_{clean_col_id}"
                        stock_movements.append({
                            "movement_id": mov_id,
                            "source_id": source_id,
                            "source_sheet": sheet_name,
                            "source_row": row_idx,
                            "date": col_date,
                            "product_id": p_id,
                            "part_no": part_no,
                            "description": desc or part_no,
                            "category": cat,
                            "movement_type": col_mov_type,
                            "qty": float(parsed_val),
                            "uom": uom,
                            "opening_stock": float(opening_stock) if isinstance(opening_stock, (int, float)) else 0.0,
                            "in_qty": float(parsed_val) if col_mov_type == 'IN' else 0.0,
                            "out_qty": float(parsed_val) if col_mov_type == 'OUT' else 0.0,
                            "closing_stock": float(current_stock) if isinstance(current_stock, (int, float)) else 0.0,
                            "period": period,
                            "reference_no": ref_no,
                            "party_name": party_name,
                            "remarks": f"{col_header} movement",
                            "validation_flags": []
                        })

            # Mode 2: Structure B — Row-based transactions (Date column + Type / In / Out columns)
            row_date = self.parse_date_string(raw_dict.get(date_col_name)) if date_col_name else None

            # Check if row has an explicit Type column (e.g. Type = 'IN' or 'OUT', Qty = 10)
            if type_col_name and qty_col_name:
                row_type_str = str(raw_dict.get(type_col_name, "")).strip().upper()
                row_qty_val = self.parse_number_or_preserve(raw_dict.get(qty_col_name))
                if isinstance(row_qty_val, (int, float)) and row_qty_val > 0:
                    mov_type = 'IN' if any(w in row_type_str for w in ['IN', 'RECEIPT', 'INWARD']) else 'OUT' if any(w in row_type_str for w in ['OUT', 'ISSUE', 'OUTWARD']) else 'IN'
                    mov_date = row_date or now_iso[:10]
                    mov_id = f"{source_id}_{sheet_name}_{row_idx}_TXN"
                    stock_movements.append({
                        "movement_id": mov_id,
                        "source_id": source_id,
                        "source_sheet": sheet_name,
                        "source_row": row_idx,
                        "date": mov_date,
                        "product_id": p_id,
                        "part_no": part_no,
                        "description": desc or part_no,
                        "category": cat,
                        "movement_type": mov_type,
                        "qty": float(row_qty_val),
                        "uom": uom,
                        "opening_stock": float(opening_stock) if isinstance(opening_stock, (int, float)) else 0.0,
                        "in_qty": float(row_qty_val) if mov_type == 'IN' else 0.0,
                        "out_qty": float(row_qty_val) if mov_type == 'OUT' else 0.0,
                        "closing_stock": float(current_stock) if isinstance(current_stock, (int, float)) else 0.0,
                        "period": period,
                        "reference_no": ref_no,
                        "party_name": party_name,
                        "remarks": f"Row transaction {row_idx}",
                        "validation_flags": []
                    })

            # Check if row has dedicated Inward and/or Outward Quantity columns (and not already extracted via Structure A)
            elif not date_in_out_columns:
                in_val = self.parse_number_or_preserve(raw_dict.get(in_col_name)) if in_col_name else None
                out_val = self.parse_number_or_preserve(raw_dict.get(out_col_name)) if out_col_name else None

                in_float = float(in_val) if isinstance(in_val, (int, float)) else 0.0
                out_float = float(out_val) if isinstance(out_val, (int, float)) else 0.0
                mov_date = row_date or now_iso[:10]

                if in_float > 0:
                    stock_movements.append({
                        "movement_id": f"{source_id}_{sheet_name}_{row_idx}_IN",
                        "source_id": source_id,
                        "source_sheet": sheet_name,
                        "source_row": row_idx,
                        "date": mov_date,
                        "product_id": p_id,
                        "part_no": part_no,
                        "description": desc or part_no,
                        "category": cat,
                        "movement_type": "IN",
                        "qty": in_float,
                        "uom": uom,
                        "opening_stock": float(opening_stock) if isinstance(opening_stock, (int, float)) else 0.0,
                        "in_qty": in_float,
                        "out_qty": 0.0,
                        "closing_stock": float(current_stock) if isinstance(current_stock, (int, float)) else 0.0,
                        "period": period,
                        "reference_no": ref_no,
                        "party_name": party_name,
                        "remarks": f"Inward transaction row {row_idx}",
                        "validation_flags": []
                    })

                if out_float > 0:
                    stock_movements.append({
                        "movement_id": f"{source_id}_{sheet_name}_{row_idx}_OUT",
                        "source_id": source_id,
                        "source_sheet": sheet_name,
                        "source_row": row_idx,
                        "date": mov_date,
                        "product_id": p_id,
                        "part_no": part_no,
                        "description": desc or part_no,
                        "category": cat,
                        "movement_type": "OUT",
                        "qty": out_float,
                        "uom": uom,
                        "opening_stock": float(opening_stock) if isinstance(opening_stock, (int, float)) else 0.0,
                        "in_qty": 0.0,
                        "out_qty": out_float,
                        "closing_stock": float(current_stock) if isinstance(current_stock, (int, float)) else 0.0,
                        "period": period,
                        "reference_no": ref_no,
                        "party_name": party_name,
                        "remarks": f"Outward transaction row {row_idx}",
                        "validation_flags": []
                    })

        return inventory_records, stock_movements
