import re
import uuid
import datetime
import logging
from typing import Dict, List, Any, Optional
from spreadsheet_parser import UniversalParser, parse_numeric, parse_date_string, EXCLUDED_QTY_TERMS

logger = logging.getLogger(__name__)


def extract_spreadsheet_id(url_or_id: str) -> str:
    """Extracts a Google Spreadsheet ID from a full Google Sheets URL or returns the raw ID."""
    s = (url_or_id or "").strip()
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', s)
    if m:
        return m.group(1)
    return s


def infer_column_type(values: List[Any]) -> str:
    non_empty = [v for v in values if v is not None and str(v).strip() != ""]
    if not non_empty:
        return "text"
    num_count = sum(1 for v in non_empty if parse_numeric(v) is not None)
    if num_count >= len(non_empty) * 0.7:
        return "number"
    date_count = sum(1 for v in non_empty if parse_date_string(v) is not None)
    if date_count >= len(non_empty) * 0.7:
        return "date"
    return "text"


class InventoryDataStore:
    """Thread-safe In-Memory Data Store holding dynamic Google Sheets rows, columns, products, and movements."""

    def __init__(self, source_id: str = "default", name: str = "Primary Stock Sheet", spreadsheet_id: str = "", source_type: str = "google_sheets"):
        self.source_id = source_id
        self.name = name
        self.spreadsheet_id = spreadsheet_id
        self.source_type = source_type
        self.description = ""
        self.period = ""
        self.status = "active"
        self.is_active = 1
        self.poll_interval_seconds = 15

        self.products: List[Dict[str, Any]] = []
        self.movements: List[Dict[str, Any]] = []
        self.worksheets: List[Dict[str, Any]] = []
        self.dynamic_columns: Dict[str, List[Dict[str, Any]]] = {}  # sheet_name -> list of DynamicColumn
        self.dynamic_records: Dict[str, List[Dict[str, Any]]] = {}  # sheet_name -> list of DynamicRecord

        self.created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.updated_at = self.created_at
        self.last_sync_at: Optional[str] = None
        self.last_sync_status: str = "pending"
        self.last_sync_error: Optional[str] = None
        self.analysis_status: str = "idle"
        self.last_analyzed_at: Optional[str] = None

    def reset(self):
        self.products.clear()
        self.movements.clear()
        self.worksheets.clear()
        self.dynamic_columns.clear()
        self.dynamic_records.clear()

    def remove_worksheet(self, sheet_name: str):
        self.products = [p for p in self.products if p.get("source_sheet") != sheet_name]
        self.movements = [m for m in self.movements if m.get("source_sheet") != sheet_name]
        self.worksheets = [w for w in self.worksheets if w.get("sheet_name") != sheet_name]
        self.dynamic_columns.pop(sheet_name, None)
        self.dynamic_records.pop(sheet_name, None)

    def update_from_raw_sheets(self, raw_sheets: Dict[str, List[List[Any]]], period: Optional[str] = None):
        """Processes raw 2D grid from Google Sheets into dynamic columns/records, inventory items, and daily movements."""
        new_products = []
        new_movements = []
        new_worksheets = []
        new_dyn_cols: Dict[str, List[Dict[str, Any]]] = {}
        new_dyn_recs: Dict[str, List[Dict[str, Any]]] = {}

        seen_product_keys = set()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        use_period = period or self.period

        for sheet_idx, (sheet_name, rows) in enumerate(raw_sheets.items()):
            if not rows:
                continue

            headers, header_rows_consumed = UniversalParser.detect_header_rows(rows)
            # Ensure unique non-empty header names for dynamic dictionary keys
            unique_headers: List[str] = []
            seen_h: Dict[str, int] = {}
            for i, h in enumerate(headers):
                base_h = h.strip() if h and str(h).strip() else f"Column_{i + 1}"
                if base_h in seen_h:
                    seen_h[base_h] += 1
                    unique_headers.append(f"{base_h} ({seen_h[base_h]})")
                else:
                    seen_h[base_h] = 1
                    unique_headers.append(base_h)

            data_rows = rows[header_rows_consumed:] if len(rows) > header_rows_consumed else []
            roles = UniversalParser.classify_columns(unique_headers)

            p_idx = roles.get('part_no')
            d_idx = roles.get('description')
            c_idx = roles.get('category')
            u_idx = roles.get('uom')
            op_idx = roles.get('opening_stock')
            cl_idx = roles.get('closing_stock')
            in_idx = roles.get('in_qty')
            out_idx = roles.get('out_qty')
            price_idx = roles.get('unit_price')
            date_col_idx = roles.get('date')
            movement_pairs = roles.get('date_movement_pairs', [])

            # Build dynamic column metadata
            col_metas: List[Dict[str, Any]] = []
            for c_i, col_name in enumerate(unique_headers):
                col_vals = [r[c_i] for r in data_rows if c_i < len(r) and r[c_i] is not None and str(r[c_i]).strip() != ""]
                populated_pct = round((len(col_vals) / len(data_rows)) * 100, 1) if data_rows else 0.0
                inferred_role = "unknown"
                if c_i == p_idx:
                    inferred_role = "product_id"
                elif c_i == d_idx:
                    inferred_role = "description"
                elif c_i == c_idx:
                    inferred_role = "category"
                elif c_i == u_idx:
                    inferred_role = "uom"
                elif c_i == op_idx:
                    inferred_role = "opening_stock"
                elif c_i == cl_idx:
                    inferred_role = "closing_stock"
                elif c_i == in_idx or any(pair[0] == c_i and pair[2] == 'IN' for pair in movement_pairs):
                    inferred_role = "in_qty"
                elif c_i == out_idx or any(pair[0] == c_i and pair[2] == 'OUT' for pair in movement_pairs):
                    inferred_role = "out_qty"
                elif c_i == date_col_idx:
                    inferred_role = "date"
                elif c_i == price_idx or any(term in col_name.lower() for term in EXCLUDED_QTY_TERMS):
                    inferred_role = "unit_price"

                col_metas.append({
                    "id": c_i + 1,
                    "source_id": self.source_id,
                    "sheet_name": sheet_name,
                    "column_index": c_i,
                    "original_col": col_name,
                    "normalized_col": re.sub(r'[^a-z0-9]+', '_', col_name.lower()).strip('_'),
                    "inferred_role": inferred_role,
                    "inferred_type": infer_column_type(col_vals[:25]),
                    "confidence": 0.95 if inferred_role != "unknown" else 0.5,
                    "sample_values": [str(v) for v in col_vals[:5]],
                    "stats": {
                        "populated_pct": populated_pct,
                        "unique_count": len(set(str(v) for v in col_vals))
                    },
                    "mapping_status": "auto",
                    "requires_review": 0 if inferred_role != "unknown" else 1,
                    "reason": f"Detected as {inferred_role}" if inferred_role != "unknown" else "Custom dynamic column",
                    "updated_at": now_iso
                })

            new_dyn_cols[sheet_name] = col_metas

            structure_type = "date_grid" if movement_pairs else ("transaction_register" if date_col_idx is not None else "summary_table")
            classification = "stock_movement" if (movement_pairs or date_col_idx is not None) else "inventory_summary"

            new_worksheets.append({
                "id": sheet_idx + 1,
                "source_id": self.source_id,
                "sheet_name": sheet_name,
                "sheet_index": sheet_idx,
                "row_count": len(data_rows),
                "col_count": len(unique_headers),
                "header_row": header_rows_consumed,
                "headers": unique_headers,
                "structure_type": structure_type,
                "classification": classification,
                "quality_score": 100.0 if len(data_rows) > 0 else 50.0,
                "analysis_status": "completed",
                "status": "success",
                "last_sync_at": now_iso,
                "issues": [],
                "amount_columns": [c["original_col"] for c in col_metas if c["inferred_role"] == "unit_price"],
                "date_columns": [unique_headers[p[0]] for p in movement_pairs if p[0] < len(unique_headers)],
                "summary": {
                    "quality_issues": [],
                    "duplicate_candidates": [],
                    "header_rows": list(range(1, header_rows_consumed + 1)),
                    "data_start_row": header_rows_consumed + 1
                },
                "created_at": now_iso,
                "updated_at": now_iso
            })

            sheet_dyn_records: List[Dict[str, Any]] = []

            for r_idx, row in enumerate(data_rows):
                if not any(cell is not None and str(cell).strip() != "" for cell in row):
                    continue

                # Build dynamic raw_data preserving ALL columns of this row
                raw_data: Dict[str, Any] = {}
                extra_fields: Dict[str, Any] = {}
                for c_i, col_name in enumerate(unique_headers):
                    val = row[c_i] if c_i < len(row) else ""
                    raw_data[col_name] = val if val is not None else ""
                    if not any(term in col_name.lower() for term in EXCLUDED_QTY_TERMS):
                        extra_fields[col_name] = val if val is not None else ""

                part_no = str(row[p_idx]).strip() if p_idx is not None and p_idx < len(row) and row[p_idx] is not None else ""
                desc = str(row[d_idx]).strip() if d_idx is not None and d_idx < len(row) and row[d_idx] is not None else ""
                category = str(row[c_idx]).strip() if c_idx is not None and c_idx < len(row) and row[c_idx] is not None else "General"
                uom = str(row[u_idx]).strip().upper() if u_idx is not None and u_idx < len(row) and row[u_idx] is not None else "NOS"
                if not uom:
                    uom = "NOS"

                if not part_no and not desc:
                    # Still preserve the dynamic record so all rows are visible in Spreadsheet Intelligence
                    sheet_dyn_records.append({
                        "id": r_idx + 1,
                        "source_id": self.source_id,
                        "sheet_name": sheet_name,
                        "row_index": header_rows_consumed + r_idx + 1,
                        "raw_data": raw_data,
                        "inferred_data": raw_data,
                        "created_at": now_iso,
                        "updated_at": now_iso
                    })
                    continue

                if not part_no:
                    part_no = f"ITEM-{sheet_name}-{r_idx+1}"

                op_val = parse_numeric(row[op_idx]) if op_idx is not None and op_idx < len(row) else 0
                cl_val = parse_numeric(row[cl_idx]) if cl_idx is not None and cl_idx < len(row) else None
                in_val = parse_numeric(row[in_idx]) if in_idx is not None and in_idx < len(row) else 0
                out_val = parse_numeric(row[out_idx]) if out_idx is not None and out_idx < len(row) else 0

                unit_price = None
                if price_idx is not None and price_idx < len(row) and row[price_idx] is not None:
                    raw_price = str(row[price_idx]).strip()
                    parsed_price = parse_numeric(row[price_idx])
                    if parsed_price is not None:
                        unit_price = parsed_price
                    elif raw_price.upper() in ('NA', 'N/A', '-'):
                        unit_price = 'NA' if raw_price.upper() == 'N/A' else raw_price.upper()

                # Sum date pairs if present for product totals
                row_pair_in = 0.0
                row_pair_out = 0.0
                if movement_pairs:
                    for col_idx, dt_str, m_type in movement_pairs:
                        if col_idx < len(row):
                            qty = parse_numeric(row[col_idx])
                            if qty is not None and qty > 0:
                                if m_type == 'IN':
                                    row_pair_in += qty
                                else:
                                    row_pair_out += qty

                total_in = (in_val or 0) + row_pair_in
                total_out = (out_val or 0) + row_pair_out
                current_stock = cl_val if cl_val is not None else ((op_val or 0) + total_in - total_out)

                stock_status = "Unknown"
                if isinstance(current_stock, (int, float)):
                    if current_stock <= 0:
                        stock_status = "Out of Stock"
                    elif current_stock <= 10:
                        stock_status = "Low Stock"
                    else:
                        stock_status = "In Stock"

                sheet_dyn_records.append({
                    "id": r_idx + 1,
                    "source_id": self.source_id,
                    "sheet_name": sheet_name,
                    "row_index": header_rows_consumed + r_idx + 1,
                    "raw_data": raw_data,
                    "inferred_data": {
                        "part_no": part_no,
                        "description": desc,
                        "category": category,
                        "uom": uom,
                        "unit_price": unit_price,
                        "opening_stock": op_val or 0,
                        "in_qty": total_in,
                        "out_qty": total_out,
                        "current_stock": current_stock
                    },
                    "created_at": now_iso,
                    "updated_at": now_iso
                })

                prod_key = f"{sheet_name}:{part_no}"
                if prod_key not in seen_product_keys:
                    seen_product_keys.add(prod_key)
                    new_products.append({
                        "product_id": part_no,
                        "part_no": part_no,
                        "description": desc,
                        "category": category,
                        "uom": uom,
                        "unit_price": unit_price,
                        "opening_stock": op_val or 0,
                        "in_qty": total_in,
                        "out_qty": total_out,
                        "current_stock": current_stock,
                        "min_level": 10,
                        "stock_status": stock_status,
                        "source_sheet": sheet_name,
                        "source_row": header_rows_consumed + r_idx + 1,
                        "extra_fields": extra_fields,
                        "validation_flags": []
                    })

                # 1. Extract movements from date-paired columns
                if movement_pairs:
                    for col_idx, dt_str, m_type in movement_pairs:
                        if col_idx < len(row):
                            qty = parse_numeric(row[col_idx])
                            if qty is not None and qty > 0:
                                new_movements.append({
                                    "movement_id": f"MOV-{sheet_name}-{part_no}-{dt_str}-{m_type}-{col_idx}-{r_idx}",
                                    "date": dt_str,
                                    "product_id": part_no,
                                    "part_no": part_no,
                                    "description": desc,
                                    "category": category,
                                    "uom": uom,
                                    "movement_type": m_type,
                                    "qty": qty,
                                    "opening_stock": op_val or 0,
                                    "in_qty": qty if m_type == 'IN' else 0,
                                    "out_qty": qty if m_type == 'OUT' else 0,
                                    "closing_stock": current_stock,
                                    "source_sheet": sheet_name,
                                    "source_row": header_rows_consumed + r_idx + 1,
                                    "validation_flags": []
                                })

                # 2. Extract movements from Transaction Registers
                elif date_col_idx is not None and date_col_idx < len(row):
                    row_dt = parse_date_string(row[date_col_idx], default_year_month=use_period)
                    if row_dt:
                        if in_val and in_val > 0:
                            new_movements.append({
                                "movement_id": f"MOV-{sheet_name}-{part_no}-{row_dt}-IN-{r_idx}",
                                "date": row_dt,
                                "product_id": part_no,
                                "part_no": part_no,
                                "description": desc,
                                "category": category,
                                "uom": uom,
                                "movement_type": "IN",
                                "qty": in_val,
                                "opening_stock": op_val or 0,
                                "in_qty": in_val,
                                "out_qty": 0,
                                "closing_stock": current_stock,
                                "source_sheet": sheet_name,
                                "source_row": header_rows_consumed + r_idx + 1,
                                "validation_flags": []
                            })
                        if out_val and out_val > 0:
                            new_movements.append({
                                "movement_id": f"MOV-{sheet_name}-{part_no}-{row_dt}-OUT-{r_idx}",
                                "date": row_dt,
                                "product_id": part_no,
                                "part_no": part_no,
                                "description": desc,
                                "category": category,
                                "uom": uom,
                                "movement_type": "OUT",
                                "qty": out_val,
                                "opening_stock": op_val or 0,
                                "in_qty": 0,
                                "out_qty": out_val,
                                "closing_stock": current_stock,
                                "source_sheet": sheet_name,
                                "source_row": header_rows_consumed + r_idx + 1,
                                "validation_flags": []
                            })

                # 3. Extract summary IN/OUT columns
                else:
                    today_iso = datetime.date.today().isoformat()
                    if in_val and in_val > 0:
                        new_movements.append({
                            "movement_id": f"MOV-SUM-{sheet_name}-{part_no}-IN-{r_idx}",
                            "date": today_iso,
                            "product_id": part_no,
                            "part_no": part_no,
                            "description": desc,
                            "category": category,
                            "uom": uom,
                            "movement_type": "IN",
                            "qty": in_val,
                            "opening_stock": op_val or 0,
                            "in_qty": in_val,
                            "out_qty": 0,
                            "closing_stock": current_stock,
                            "source_sheet": sheet_name,
                            "source_row": header_rows_consumed + r_idx + 1,
                            "validation_flags": []
                        })
                    if out_val and out_val > 0:
                        new_movements.append({
                            "movement_id": f"MOV-SUM-{sheet_name}-{part_no}-OUT-{r_idx}",
                            "date": today_iso,
                            "product_id": part_no,
                            "part_no": part_no,
                            "description": desc,
                            "category": category,
                            "uom": uom,
                            "movement_type": "OUT",
                            "qty": out_val,
                            "opening_stock": op_val or 0,
                            "in_qty": 0,
                            "out_qty": out_val,
                            "closing_stock": current_stock,
                            "source_sheet": sheet_name,
                            "source_row": header_rows_consumed + r_idx + 1,
                            "validation_flags": []
                        })

            new_dyn_recs[sheet_name] = sheet_dyn_records

        # Atomic swap
        self.products = new_products
        self.movements = sorted(new_movements, key=lambda m: (m['date'], m['part_no']), reverse=True)
        self.worksheets = new_worksheets
        self.dynamic_columns = new_dyn_cols
        self.dynamic_records = new_dyn_recs
        self.last_sync_at = now_iso
        self.last_sync_status = "success"
        self.last_sync_error = None
        self.analysis_status = "completed"
        self.last_analyzed_at = now_iso
        self.updated_at = now_iso

    def to_source_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "spreadsheet_id": self.spreadsheet_id,
            "description": self.description,
            "period": self.period,
            "status": self.status,
            "is_active": self.is_active,
            "poll_interval_seconds": self.poll_interval_seconds,
            "last_sync_at": self.last_sync_at,
            "last_sync_status": self.last_sync_status,
            "last_sync_error": self.last_sync_error,
            "sheets_count": len(self.worksheets),
            "products_count": len(self.products),
            "movements_count": len(self.movements),
            "source_type": self.source_type,
            "total_worksheets": len(self.worksheets),
            "total_records": sum(w["row_count"] for w in self.worksheets),
            "last_analyzed_at": self.last_analyzed_at,
            "analysis_status": self.analysis_status,
            "sheets": self.worksheets,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Calculates unified DashboardKPI matching old frontend types."""
        total_products = len(self.products)
        in_stock_count = sum(1 for p in self.products if p.get("stock_status") == "In Stock")
        low_stock_count = sum(1 for p in self.products if p.get("stock_status") == "Low Stock")
        out_of_stock_count = sum(1 for p in self.products if p.get("stock_status") == "Out of Stock")
        unknown_stock_count = sum(1 for p in self.products if p.get("stock_status") == "Unknown")

        uom_quantities: Dict[str, float] = {}
        for p in self.products:
            u = p.get("uom") or "NOS"
            val = p.get("current_stock")
            if isinstance(val, (int, float)):
                uom_quantities[u] = uom_quantities.get(u, 0) + val

        inward_by_uom: Dict[str, float] = {}
        outward_by_uom: Dict[str, float] = {}
        total_in_tx = 0
        total_out_tx = 0
        date_map: Dict[str, Dict[str, Any]] = {}

        for m in self.movements:
            u = m.get("uom") or "NOS"
            in_q = m.get("in_qty", 0) or 0
            out_q = m.get("out_qty", 0) or 0
            if m.get("movement_type") == "IN":
                total_in_tx += 1
                inward_by_uom[u] = inward_by_uom.get(u, 0) + in_q
            else:
                total_out_tx += 1
                outward_by_uom[u] = outward_by_uom.get(u, 0) + out_q

            d = m.get("date")
            if d:
                if d not in date_map:
                    date_map[d] = {"date": d, "in": 0, "out": 0, "transactions": 0}
                date_map[d]["in"] += in_q
                date_map[d]["out"] += out_q
                date_map[d]["transactions"] += 1

        daily_trends = sorted(date_map.values(), key=lambda x: x["date"])

        cat_counts: Dict[str, int] = {}
        for p in self.products:
            c = p.get("category") or "General"
            cat_counts[c] = cat_counts.get(c, 0) + 1
        category_distribution = [{"category": k, "count": v} for k, v in cat_counts.items()]

        status_distribution = [
            {"status": "In Stock", "count": in_stock_count},
            {"status": "Low Stock", "count": low_stock_count},
            {"status": "Out of Stock", "count": out_of_stock_count},
        ]

        return {
            "total_products": total_products,
            "in_stock_count": in_stock_count,
            "low_stock_count": low_stock_count,
            "out_of_stock_count": out_of_stock_count,
            "unknown_stock_count": unknown_stock_count,
            "total_movements_count": len(self.movements),
            "total_in_transactions": total_in_tx,
            "total_out_transactions": total_out_tx,
            "uom_quantities": uom_quantities,
            "inward_by_uom": inward_by_uom,
            "outward_by_uom": outward_by_uom,
            "daily_trends": daily_trends,
            "category_distribution": category_distribution,
            "status_distribution": status_distribution,
            "recent_movements": self.movements[:15],
            "last_updated": self.last_sync_at
        }
