import uuid
import datetime
import logging
from typing import Dict, List, Any, Optional
from spreadsheet_parser import UniversalParser, parse_numeric, parse_date_string

logger = logging.getLogger(__name__)


class InventoryDataStore:
    """Thread-safe In-Memory Data Store holding Google Sheets stock records and movements."""

    def __init__(self):
        self.products: List[Dict[str, Any]] = []
        self.movements: List[Dict[str, Any]] = []
        self.worksheets: List[Dict[str, Any]] = []
        self.source_metadata: Dict[str, Any] = {
            "title": "Stock Data",
            "source_type": "google_sheets",
            "last_sync_at": None,
            "status": "idle"
        }

    def reset(self):
        self.products.clear()
        self.movements.clear()
        self.worksheets.clear()

    def update_from_raw_sheets(self, raw_sheets: Dict[str, List[List[Any]]], period: Optional[str] = None):
        """Processes raw 2D grid from Google Sheets into inventory items and daily movements."""
        new_products = []
        new_movements = []
        new_worksheets = []

        seen_product_keys = set()

        for sheet_name, rows in raw_sheets.items():
            if not rows or len(rows) < 2:
                continue

            headers, header_rows_consumed = UniversalParser.detect_header_rows(rows)
            data_rows = rows[header_rows_consumed:]
            roles = UniversalParser.classify_columns(headers)

            p_idx = roles.get('part_no')
            d_idx = roles.get('description')
            c_idx = roles.get('category')
            u_idx = roles.get('uom')
            op_idx = roles.get('opening_stock')
            cl_idx = roles.get('closing_stock')
            in_idx = roles.get('in_qty')
            out_idx = roles.get('out_qty')
            date_col_idx = roles.get('date')
            movement_pairs = roles.get('date_movement_pairs', [])

            new_worksheets.append({
                "sheet_name": sheet_name,
                "row_count": len(data_rows),
                "headers": headers,
                "roles": roles
            })

            for r_idx, row in enumerate(data_rows):
                if not any(cell is not None and str(cell).strip() != "" for cell in row):
                    continue

                part_no = str(row[p_idx]).strip() if p_idx is not None and p_idx < len(row) and row[p_idx] is not None else ""
                desc = str(row[d_idx]).strip() if d_idx is not None and d_idx < len(row) and row[d_idx] is not None else ""
                category = str(row[c_idx]).strip() if c_idx is not None and c_idx < len(row) and row[c_idx] is not None else "General"
                uom = str(row[u_idx]).strip().upper() if u_idx is not None and u_idx < len(row) and row[u_idx] is not None else "NOS"

                if not part_no and not desc:
                    continue

                if not part_no:
                    part_no = f"ITEM-{sheet_name}-{r_idx+1}"

                # Calculate item stock numbers
                op_val = parse_numeric(row[op_idx]) if op_idx is not None and op_idx < len(row) else 0.0
                cl_val = parse_numeric(row[cl_idx]) if cl_idx is not None and cl_idx < len(row) else None
                in_val = parse_numeric(row[in_idx]) if in_idx is not None and in_idx < len(row) else 0.0
                out_val = parse_numeric(row[out_idx]) if out_idx is not None and out_idx < len(row) else 0.0

                prod_key = f"{sheet_name}:{part_no}"
                if prod_key not in seen_product_keys:
                    seen_product_keys.add(prod_key)
                    # Computed closing if not directly present in sheet
                    current_stock = cl_val if cl_val is not None else ((op_val or 0) + (in_val or 0) - (out_val or 0))

                    new_products.append({
                        "product_id": part_no,
                        "part_no": part_no,
                        "description": desc,
                        "category": category,
                        "uom": uom,
                        "opening_stock": op_val or 0,
                        "in_qty": in_val or 0,
                        "out_qty": out_val or 0,
                        "current_stock": current_stock,
                        "source_sheet": sheet_name
                    })

                # 1. Extract movements from date-paired columns (e.g. "01-10-2026 IN", "1 IN")
                if movement_pairs:
                    for col_idx, dt_str, m_type in movement_pairs:
                        if col_idx < len(row):
                            qty = parse_numeric(row[col_idx])
                            if qty and qty > 0:
                                new_movements.append({
                                    "movement_id": f"MOV-{sheet_name}-{part_no}-{dt_str}-{m_type}-{col_idx}",
                                    "date": dt_str,
                                    "part_no": part_no,
                                    "description": desc,
                                    "category": category,
                                    "uom": uom,
                                    "movement_type": m_type,
                                    "qty": qty,
                                    "in_qty": qty if m_type == 'IN' else 0,
                                    "out_qty": qty if m_type == 'OUT' else 0,
                                    "source_sheet": sheet_name
                                })

                # 2. Extract movements from Transaction Registers (Date + IN or OUT)
                elif date_col_idx is not None and date_col_idx < len(row):
                    row_dt = parse_date_string(row[date_col_idx], default_year_month=period)
                    if row_dt:
                        if in_val and in_val > 0:
                            new_movements.append({
                                "movement_id": f"MOV-{sheet_name}-{part_no}-{row_dt}-IN-{r_idx}",
                                "date": row_dt,
                                "part_no": part_no,
                                "description": desc,
                                "category": category,
                                "uom": uom,
                                "movement_type": "IN",
                                "qty": in_val,
                                "in_qty": in_val,
                                "out_qty": 0,
                                "source_sheet": sheet_name
                            })
                        if out_val and out_val > 0:
                            new_movements.append({
                                "movement_id": f"MOV-{sheet_name}-{part_no}-{row_dt}-OUT-{r_idx}",
                                "date": row_dt,
                                "part_no": part_no,
                                "description": desc,
                                "category": category,
                                "uom": uom,
                                "movement_type": "OUT",
                                "qty": out_val,
                                "in_qty": 0,
                                "out_qty": out_val,
                                "source_sheet": sheet_name
                            })

                # 3. Extract summary IN and OUT movements (using sheet/current date)
                else:
                    today_iso = datetime.date.today().isoformat()
                    if in_val and in_val > 0:
                        new_movements.append({
                            "movement_id": f"MOV-SUM-{sheet_name}-{part_no}-IN",
                            "date": today_iso,
                            "part_no": part_no,
                            "description": desc,
                            "category": category,
                            "uom": uom,
                            "movement_type": "IN",
                            "qty": in_val,
                            "in_qty": in_val,
                            "out_qty": 0,
                            "source_sheet": sheet_name
                        })
                    if out_val and out_val > 0:
                        new_movements.append({
                            "movement_id": f"MOV-SUM-{sheet_name}-{part_no}-OUT",
                            "date": today_iso,
                            "part_no": part_no,
                            "description": desc,
                            "category": category,
                            "uom": uom,
                            "movement_type": "OUT",
                            "qty": out_val,
                            "in_qty": 0,
                            "out_qty": out_val,
                            "source_sheet": sheet_name
                        })

        # Atomic swap
        self.products = new_products
        self.movements = sorted(new_movements, key=lambda m: (m['date'], m['part_no']), reverse=True)
        self.worksheets = new_worksheets
        self.source_metadata["last_sync_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.source_metadata["status"] = "success"

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Calculates unified dashboard metrics straight from items and movements."""
        total_items = len(self.products)
        total_in_qty = sum(m.get('in_qty', 0) for m in self.movements)
        total_out_qty = sum(m.get('out_qty', 0) for m in self.movements)

        # Date-wise trends
        date_map = {}
        for m in self.movements:
            d = m.get('date')
            if not d:
                continue
            if d not in date_map:
                date_map[d] = {"date": d, "in_qty": 0, "out_qty": 0, "movement_count": 0}
            date_map[d]["in_qty"] += m.get('in_qty', 0)
            date_map[d]["out_qty"] += m.get('out_qty', 0)
            date_map[d]["movement_count"] += 1

        daily_trends = sorted(date_map.values(), key=lambda x: x["date"])

        # Category Breakdown
        categories: Dict[str, int] = {}
        for p in self.products:
            cat = p.get('category') or 'General'
            categories[cat] = categories.get(cat, 0) + 1

        category_breakdown = [{"category": k, "count": v} for k, v in categories.items()]

        return {
            "total_items": total_items,
            "total_movements": len(self.movements),
            "total_in_qty": total_in_qty,
            "total_out_qty": total_out_qty,
            "daily_trends": daily_trends,
            "category_breakdown": category_breakdown,
            "recent_movements": self.movements[:10],
            "worksheets": [w["sheet_name"] for w in self.worksheets]
        }
