import re
import logging
from datetime import datetime, date, timezone
from typing import Dict, List, Any, Optional, Tuple, Union
from collections import defaultdict

logger = logging.getLogger(__name__)

SPECIAL_STRINGS = {"NA", "-", "N/A", "N.A."}

def parse_num_or_preserve(val: Any) -> Union[float, int, str, None]:
    """Parse numeric values while strictly preserving 'NA' and '-' literals."""
    if val is None:
        return None
    val_str = str(val).strip()
    if val_str in SPECIAL_STRINGS:
        return val_str
    if val_str == "":
        return None
    # Remove commas and currency symbols if present
    cleaned = re.sub(r'[\$,₹]', '', val_str).replace(',', '')
    try:
        f = float(cleaned)
        return int(f) if f.is_integer() else f
    except ValueError:
        return val_str

def parse_date_cell(val: Any) -> Optional[str]:
    """Parse date from datetime object, timestamp string, or various date formats into YYYY-MM-DD."""
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    if not s or s.lower() in ("opening stock", "closing", "amount", "unit price"):
        return None
    # YYYY-MM-DD or YYYY-M-D (with optional timestamp)
    m1 = re.match(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})', s)
    if m1:
        y, m, d = m1.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    # M/D/YYYY or MM/DD/YYYY (e.g. Google Sheets 10/1/2026)
    m2 = re.match(r'^(\d{1,2})[/-](\d{1,2})[/-](\d{4})', s)
    if m2:
        m, d, y = m2.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    return None

class InventoryService:
    def __init__(self, analysis_report: Dict[str, Any], raw_sheets_data: Dict[str, List[List[Any]]], source_id: str = "active", period: str = ""):
        self.analysis = analysis_report
        self.raw_data = raw_sheets_data
        self.source_id = source_id
        self.period = period
        self.products: List[Dict[str, Any]] = []
        self.movements: List[Dict[str, Any]] = []
        self.data_quality_issues: List[Dict[str, Any]] = []
        self._build_models()

    def _build_models(self):
        """Construct normalized products and daily stock movements from sheet data."""
        self.products.clear()
        self.movements.clear()
        self.data_quality_issues.clear()

        sheets_meta = self.analysis.get("sheets", {})

        for sheet_name, sheet_analysis in sheets_meta.items():
            rows = self.raw_data.get(sheet_name, [])
            if not rows or len(rows) < 2:
                continue

            # Row 0 contains Dates across daily columns (e.g. 10/1/2026 or 2026-10-01)
            row_0 = rows[0]
            
            # Row 1 is detailed column headers
            header_row_idx = sheet_analysis.get("header_rows", [2])[0] - 1
            if header_row_idx >= len(rows):
                header_row_idx = 1 if len(rows) > 1 else 0

            headers = [str(c).strip() if c is not None else "" for c in rows[header_row_idx]]
            data_start = header_row_idx + 1
            data_rows = rows[data_start:]

            self._parse_sheet_catalog(sheet_name, row_0, headers, data_rows, sheet_analysis)

        # Sort all movements chronologically and by product
        self.movements.sort(key=lambda m: (m["date"], m["source_sheet"], m["product_id"]))

    def _parse_sheet_catalog(
        self,
        sheet_name: str,
        row_dates_raw: List[Any],
        headers: List[str],
        data_rows: List[List[Any]],
        sheet_analysis: Dict[str, Any]
    ):
        h_lower = [h.lower() for h in headers]

        def find_idx(*patterns):
            for pat in patterns:
                for idx, h in enumerate(h_lower):
                    if pat in h:
                        return idx
            return None

        desc_idx = find_idx("description", "product name", "item name", "particulars", "name")
        part_idx = find_idx("part no", "part_no", "part#", "cat no", "model", "item code")
        cat_idx = find_idx("category", "group", "type")
        uom_idx = find_idx("uom", "unit")
        open_stock_idx = find_idx("opening stock", "open stock")
        unit_price_idx = find_idx("unit price", "unit cost", "rate", "price/unit", "rate (rs)")

        # Find explicit closing stock column in row 0 or row 1 (excluding amount / value columns)
        closing_col_idx = None
        for c, v in enumerate(row_dates_raw):
            if v and "closing" in str(v).lower():
                closing_col_idx = c
                break
        if closing_col_idx is None:
            for c, h in enumerate(h_lower):
                if "closing" in h and not any(kw in h for kw in ["amount", "value", "cost", "price", "val"]):
                    closing_col_idx = c
                    break

        # Map all daily columns across row 0 (Row 0: date, Row 1: sub-headers OPENING, IN, OUT)
        date_col_map = []  # List of (date_str, open_idx, in_idx, out_idx)
        for c_idx in range(len(row_dates_raw)):
            d_val = parse_date_cell(row_dates_raw[c_idx])
            if d_val:
                open_i = c_idx
                in_i = c_idx + 1
                out_i = c_idx + 2
                date_col_map.append((d_val, open_i, in_i, out_i))

        # Sort dates chronologically
        date_col_map.sort(key=lambda x: x[0])
        latest_date_str = date_col_map[-1][0] if date_col_map else "2026-10-31"

        section_headers = {
            "copper", "accessories", "cables", "cables & wires", "truffs", "lugs", 
            "lamps", "ferrule tube", "terminal black", "fasteners", "busbars"
        }

        for r_idx, row in enumerate(data_rows, start=3):
            if not row or not any(row):
                continue

            desc = str(row[desc_idx]).strip() if desc_idx is not None and desc_idx < len(row) and row[desc_idx] is not None else ""
            if not desc or desc.lower() in section_headers:
                continue

            part_no = str(row[part_idx]).strip() if part_idx is not None and part_idx < len(row) and row[part_idx] is not None else "NA"
            if part_no == "" or part_no.lower() in ("none", "null"):
                part_no = "NA"

            category = str(row[cat_idx]).strip() if cat_idx is not None and cat_idx < len(row) and row[cat_idx] is not None else sheet_name
            uom = str(row[uom_idx]).strip().upper() if uom_idx is not None and uom_idx < len(row) and row[uom_idx] is not None else "NOS"

            p_id = part_no if part_no not in SPECIAL_STRINGS and part_no != "NA" else f"{sheet_name[:3].upper()}-{r_idx}"

            unit_price = parse_num_or_preserve(row[unit_price_idx]) if unit_price_idx is not None and unit_price_idx < len(row) else None
            monthly_opening = parse_num_or_preserve(row[open_stock_idx]) if open_stock_idx is not None and open_stock_idx < len(row) else 0

            # -------------------------------------------------------------
            # Track Daily Transactions & Determine Current Stock (Latest Date)
            # -------------------------------------------------------------
            running_stock = monthly_opening if isinstance(monthly_opening, (int, float)) else 0
            latest_day_stock = running_stock

            for d_str, o_i, in_i, out_i in date_col_map:
                d_open_raw = parse_num_or_preserve(row[o_i]) if o_i < len(row) else None
                d_in_raw = parse_num_or_preserve(row[in_i]) if in_i < len(row) else None
                d_out_raw = parse_num_or_preserve(row[out_i]) if out_i < len(row) else None

                in_val = float(d_in_raw) if isinstance(d_in_raw, (int, float)) else 0.0
                out_val = float(d_out_raw) if isinstance(d_out_raw, (int, float)) else 0.0

                if isinstance(d_open_raw, (int, float)):
                    day_open = d_open_raw
                    running_stock = d_open_raw
                else:
                    day_open = running_stock

                day_closing = (day_open if isinstance(day_open, (int, float)) else 0) + in_val - out_val
                running_stock = day_closing
                latest_day_stock = day_closing

                # If there was an active transaction on this day, record the movement
                if in_val > 0 or out_val > 0:
                    mov_type = "IN" if in_val > 0 and out_val == 0 else ("OUT" if out_val > 0 and in_val == 0 else "IN/OUT")
                    primary_qty = in_val if in_val > 0 else out_val

                    self.movements.append({
                        "movement_id": f"{p_id}-{d_str}",
                        "date": d_str,
                        "product_id": p_id,
                        "part_no": part_no,
                        "description": desc,
                        "category": category,
                        "movement_type": mov_type,
                        "qty": primary_qty,
                        "uom": uom,
                        "opening_stock": day_open,
                        "in_qty": in_val,
                        "out_qty": out_val,
                        "closing_stock": day_closing,
                        "reference_no": f"STK-{d_str}",
                        "party_name": "Store Operations",
                        "remarks": f"Daily movement recorded in {sheet_name}",
                        "source_sheet": sheet_name,
                        "source_row": r_idx,
                        "source_id": self.source_id,
                        "period": self.period,
                        "validation_flags": []
                    })

            # Check explicit closing column in sheet
            explicit_closing = None
            if closing_col_idx is not None and closing_col_idx < len(row) and row[closing_col_idx] is not None:
                parsed_c = parse_num_or_preserve(row[closing_col_idx])
                if parsed_c is not None and parsed_c != "":
                    explicit_closing = parsed_c

            # CURRENT STOCK AS PER LATEST DATE:
            # Prefer explicit closing column if valid, otherwise the closing stock calculated on the latest date
            if explicit_closing is not None:
                current_stock = explicit_closing
            else:
                current_stock = latest_day_stock

            # Determine stock status
            min_level = 10
            status = "In Stock"
            if current_stock in ("NA", "-"):
                status = "Unknown"
            elif isinstance(current_stock, (int, float)):
                if current_stock <= 0:
                    status = "Out of Stock"
                elif current_stock <= min_level:
                    status = "Low Stock"

            # Filter extra fields — STRICT EXCLUSION OF AMOUNT/VALUE COLUMNS
            extra = {}
            for c_i, h in enumerate(headers):
                if any(kw in h.lower() for kw in ["amount", "total cost", "total price", "value", "val"]):
                    continue
                if c_i not in (desc_idx, part_idx, cat_idx, uom_idx, open_stock_idx, unit_price_idx, closing_col_idx):
                    if c_i < len(row) and row[c_i] is not None:
                        val = parse_num_or_preserve(row[c_i])
                        if val is not None and val != "":
                            extra[h] = val

            self.products.append({
                "product_id": p_id,
                "description": desc,
                "part_no": part_no,
                "category": category,
                "uom": uom,
                "unit_price": unit_price,
                "opening_stock": monthly_opening,
                "current_stock": current_stock,
                "latest_date": latest_date_str,
                "min_level": min_level,
                "stock_status": status,
                "source_sheet": sheet_name,
                "source_row": r_idx,
                "source_id": self.source_id,
                "period": self.period,
                "extra_fields": extra,
                "validation_flags": []
            })

    # ---------------- High Performance Query and Analytics ----------------
    def get_products(
        self,
        search: str = "",
        sheet: str = "",
        category: str = "",
        part_no: str = "",
        uom: str = "",
        status: str = "",
        source_id: str = ""
    ) -> List[Dict[str, Any]]:
        res = self.products
        if search:
            s = search.lower()
            res = [
                p for p in res
                if s in p["product_id"].lower()
                or s in p["description"].lower()
                or s in p["part_no"].lower()
                or s in p["category"].lower()
            ]
        if sheet:
            s_sheet = sheet.lower()
            res = [p for p in res if p["source_sheet"].lower() == s_sheet]
        if category:
            s_cat = category.lower()
            res = [p for p in res if p["category"].lower() == s_cat]
        if part_no:
            s_part = part_no.lower()
            res = [p for p in res if s_part in p["part_no"].lower()]
        if uom:
            s_uom = uom.lower()
            res = [p for p in res if p["uom"].lower() == s_uom]
        if status:
            s_status = status.lower()
            res = [p for p in res if p["stock_status"].lower() == s_status]
        if source_id:
            res = [p for p in res if p.get("source_id", "") == source_id]
        return res

    def get_product_by_id(self, product_id: str) -> Optional[Dict[str, Any]]:
        p_clean = product_id.strip().lower()
        for p in self.products:
            if p["product_id"].lower() == p_clean or p["part_no"].lower() == p_clean:
                return p
        return None

    def get_movements(
        self,
        product_id: str = "",
        from_date: str = "",
        to_date: str = "",
        movement_type: str = ""
    ) -> List[Dict[str, Any]]:
        res = self.movements
        if product_id:
            pid = product_id.strip().lower()
            res = [m for m in res if pid in m["product_id"].lower() or pid in m["part_no"].lower() or pid in m["description"].lower()]
        if from_date:
            res = [m for m in res if m["date"] >= from_date]
        if to_date:
            res = [m for m in res if m["date"] <= to_date]
        if movement_type:
            m_type = movement_type.upper()
            if m_type == "IN":
                res = [m for m in res if m["movement_type"] in ("IN", "IN/OUT") and (m.get("in_qty") or 0) > 0]
            elif m_type == "OUT":
                res = [m for m in res if m["movement_type"] in ("OUT", "IN/OUT") and (m.get("out_qty") or 0) > 0]
        return res

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Aggregate high performance analytics respecting strict UOM boundaries and zero amount exposure."""
        total_products = len(self.products)
        in_stock = sum(1 for p in self.products if p["stock_status"] == "In Stock")
        low_stock = sum(1 for p in self.products if p["stock_status"] == "Low Stock")
        out_of_stock = sum(1 for p in self.products if p["stock_status"] == "Out of Stock")
        unknown_stock = sum(1 for p in self.products if p["stock_status"] == "Unknown")

        # Current Stock Quantities grouped strictly by UOM (never combine meters with coils or pieces)
        uom_quantities = defaultdict(float)
        for p in self.products:
            curr = p["current_stock"]
            if isinstance(curr, (int, float)):
                uom_quantities[p["uom"]] += curr

        # Movements grouped by UOM
        inward_by_uom = defaultdict(float)
        outward_by_uom = defaultdict(float)
        total_in_txns = 0
        total_out_txns = 0

        for m in self.movements:
            u = m["uom"]
            in_q = m.get("in_qty") or 0
            out_q = m.get("out_qty") or 0
            if in_q > 0:
                inward_by_uom[u] += in_q
                total_in_txns += 1
            if out_q > 0:
                outward_by_uom[u] += out_q
                total_out_txns += 1

        # Daily trends series for bar charts (grouped by date)
        daily_trends = defaultdict(lambda: {"in": 0.0, "out": 0.0, "count": 0})
        for m in self.movements:
            d = m["date"]
            in_q = m.get("in_qty") or 0
            out_q = m.get("out_qty") or 0
            daily_trends[d]["in"] += in_q
            daily_trends[d]["out"] += out_q
            daily_trends[d]["count"] += 1

        daily_trends_list = [
            {
                "date": k,
                "in": round(v["in"], 2),
                "out": round(v["out"], 2),
                "transactions": v["count"]
            }
            for k, v in sorted(daily_trends.items())
        ]

        # Category distribution
        categories = defaultdict(int)
        for p in self.products:
            categories[p["category"]] += 1

        # Recent 10 transactions
        recent_movs = self.movements[-10:] if self.movements else []

        return {
            "total_products": total_products,
            "in_stock_count": in_stock,
            "low_stock_count": low_stock,
            "out_of_stock_count": out_of_stock,
            "unknown_stock_count": unknown_stock,
            "total_movements_count": len(self.movements),
            "total_in_transactions": total_in_txns,
            "total_out_transactions": total_out_txns,
            "uom_quantities": dict(uom_quantities),
            "inward_by_uom": dict(inward_by_uom),
            "outward_by_uom": dict(outward_by_uom),
            "daily_trends": daily_trends_list,
            "category_distribution": [
                {"category": k, "count": v}
                for k, v in sorted(categories.items(), key=lambda x: x[1], reverse=True)
            ],
            "status_distribution": [
                {"status": "In Stock", "count": in_stock},
                {"status": "Low Stock", "count": low_stock},
                {"status": "Out of Stock", "count": out_of_stock}
            ],
            "recent_movements": recent_movs,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

    def get_data_quality_report(self) -> Dict[str, Any]:
        """Compile comprehensive data quality issues across all sheets."""
        issues = []
        p_ids = [p["product_id"] for p in self.products]
        seen_ids = set()
        dups = set()
        for pid in p_ids:
            if pid in seen_ids:
                dups.add(pid)
            seen_ids.add(pid)

        if dups:
            issues.append({
                "type": "DUPLICATE_PRODUCT_ID",
                "severity": "WARNING",
                "message": f"Found duplicate product identifiers in source sheets: {list(dups)[:5]}"
            })

        na_count = sum(1 for p in self.products if p["current_stock"] in ("NA", "-") or p["unit_price"] in ("NA", "-"))
        if na_count > 0:
            issues.append({
                "type": "SPECIAL_LITERALS_PRESERVED",
                "severity": "INFO",
                "message": f"{na_count} products have preserved literal special values ('NA' or '-')"
            })

        return {
            "total_issues": len(issues),
            "issues": issues,
            "duplicate_ids": list(dups),
            "sheets_analyzed": len(self.analysis.get("sheets", {}))
        }
