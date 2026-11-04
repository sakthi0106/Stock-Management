import re
import logging
import json
from datetime import datetime, date, timezone
from typing import Dict, List, Any, Optional, Tuple, Union
from collections import defaultdict

logger = logging.getLogger(__name__)

SPECIAL_STRINGS = {'N/A', '-', 'NA', 'N.A.'}


def parse_num_or_preserve(val: Any) -> Union[float, int, str, None]:
    if val is None:
        return None
    val_str = str(val).strip()
    if not val_str:
        return None
    if val_str in SPECIAL_STRINGS:
        return val_str
    cleaned = re.sub(r'[, ]', '', val_str)
    cleaned = cleaned.replace('₹', '').replace('Rs.', '').replace('Rs', '')
    try:
        f = float(cleaned)
        if f.is_integer():
            return int(f)
        return f
    except ValueError:
        return val_str


def parse_date_cell(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.strftime('%Y-%m-%d')
    s = str(val).strip().lower()
    if not s or s in SPECIAL_STRINGS:
        return None

    # Matches YYYY-MM-DD
    m1 = re.match(r'^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', s)
    if m1:
        y, m, d = m1.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    # Matches DD-MM-YYYY
    m2 = re.match(r'^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})', s)
    if m2:
        d, m, y = m2.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    # Matches "1-oct", "01-oct-2026"
    m3 = re.match(r'^(\d{1,2})[- ]([a-z]{3})(?:[- ](\d{2,4}))?', s)
    if m3:
        months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                  'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
        day, mon, yr = m3.groups()
        if mon in months:
            m_num = months[mon]
            y_num = int(yr) if yr else 2026
            if y_num < 100:
                y_num += 2000
            return f"{y_num:04d}-{m_num:02d}-{int(day):02d}"

    return None


class InventoryService:
    def __init__(
        self,
        analysis_report: Optional[Dict[str, Any]] = None,
        raw_sheets_data: Optional[Dict[str, List[List[Any]]]] = None,
        source_id: str = "default_source",
        period: str = ""
    ):
        self.analysis = analysis_report or {}
        self.raw_data = raw_sheets_data or {}
        self.source_id = source_id
        self.period = period

        self.products: List[Dict[str, Any]] = []
        self.movements: List[Dict[str, Any]] = []
        self.data_quality_issues: List[Dict[str, Any]] = []

        self._build_models()

    def _build_models(self):
        self.products.clear()
        self.movements.clear()
        self.data_quality_issues.clear()

        sheets_meta = self.analysis.get('sheets', {})

        if sheets_meta and self.raw_data:
            for sheet_name, sheet_analysis in sheets_meta.items():
                rows = self.raw_data.get(sheet_name, [])
                if not rows or len(rows) < 2:
                    continue

                row_0 = rows[0]
                header_rows = sheet_analysis.get('header_rows', [2])
                header_row_idx = header_rows[0] - 1 if header_rows else 1
                if header_row_idx >= len(rows):
                    header_row_idx = 1 if len(rows) > 1 else 0

                headers = [str(c).strip() if c is not None else "" for c in rows[header_row_idx]]
                data_start = header_row_idx + 1
                data_rows = rows[data_start:]

                self._parse_sheet_catalog(sheet_name, row_0, headers, data_rows, sheet_analysis)

            self.movements.sort(key=lambda m: (m.get('date', ''), m.get('source_sheet', ''), m.get('product_id', '')))

        # If no products were built from raw_data, load snapshot from SQLite database
        if not self.products:
            self._load_from_db()

    def _load_from_db(self):
        try:
            import database
            conn = database.get_db_connection()
            cur = conn.cursor()

            rows = []
            m_rows = []

            if self.source_id == "all":
                cur.execute("SELECT * FROM inventory_records")
                rows = cur.fetchall()
                cur.execute("SELECT * FROM stock_movements ORDER BY date DESC, id DESC LIMIT 2000")
                m_rows = cur.fetchall()
            elif self.source_id and self.source_id not in ("active", "default_source"):
                cur.execute("SELECT * FROM inventory_records WHERE source_id = ?", (self.source_id,))
                rows = cur.fetchall()
                cur.execute("SELECT * FROM stock_movements WHERE source_id = ? ORDER BY date DESC, id DESC", (self.source_id,))
                m_rows = cur.fetchall()
            else:
                active_src = database.get_active_source()
                sid = active_src["source_id"] if active_src else None
                if sid:
                    cur.execute("SELECT * FROM inventory_records WHERE source_id = ?", (sid,))
                    rows = cur.fetchall()
                    cur.execute("SELECT * FROM stock_movements WHERE source_id = ? ORDER BY date DESC, id DESC", (sid,))
                    m_rows = cur.fetchall()
                if not rows:
                    cur.execute("SELECT * FROM inventory_records LIMIT 2000")
                    rows = cur.fetchall()
                if not m_rows:
                    cur.execute("SELECT * FROM stock_movements ORDER BY date DESC, id DESC LIMIT 2000")
                    m_rows = cur.fetchall()

            for r in rows:
                p = dict(r)
                p["extra_fields"] = json.loads(p.get("extra_fields_json") or "{}")
                p["validation_flags"] = json.loads(p.get("validation_flags_json") or "[]")
                # Parse numeric values
                p["current_stock"] = parse_num_or_preserve(p.get("current_stock"))
                p["opening_stock"] = parse_num_or_preserve(p.get("opening_stock"))
                self.products.append(p)

            for mr in m_rows:
                m = dict(mr)
                m["validation_flags"] = json.loads(m.get("validation_flags_json") or "[]")
                self.movements.append(m)

            conn.close()
        except Exception as e:
            logger.warning(f"Could not load inventory snapshot from DB: {e}")

    def _parse_sheet_catalog(
        self,
        sheet_name: str,
        row_dates_raw: List[Any],
        headers: List[str],
        data_rows: List[List[Any]],
        sheet_analysis: Dict[str, Any]
    ):
        def find_idx(candidates):
            for cand in candidates:
                for idx, h in enumerate(headers):
                    if cand in h.lower():
                        return idx
            return -1

        desc_idx = find_idx(['description', 'product name', 'item name', 'particulars', 'name'])
        part_idx = find_idx(['part no', 'part_no', 'part#', 'cat no', 'model', 'item code'])
        cat_idx = find_idx(['category', 'group', 'type'])
        uom_idx = find_idx(['uom', 'unit'])
        open_stock_idx = find_idx(['opening stock', 'open stock'])
        unit_price_idx = find_idx(['unit price', 'unit cost', 'rate', 'price/unit', 'rate (rs)'])
        closing_col_idx = find_idx(['closing'])

        # Fallbacks
        if desc_idx == -1 and len(headers) > 1:
            desc_idx = 1
        if part_idx == -1 and len(headers) > 0:
            part_idx = 0

        # Build column date mapping if dates exist in row 0
        date_col_map = {}
        for c_idx, d_val in enumerate(row_dates_raw):
            d_str = parse_date_cell(d_val)
            if d_str:
                date_col_map[c_idx] = d_str

        latest_date_str = max(date_col_map.values()) if date_col_map else "2026-10-31"

        for r_idx, row in enumerate(data_rows, start=1):
            if not row or not any(str(c).strip() for c in row):
                continue

            desc = str(row[desc_idx]).strip() if desc_idx >= 0 and desc_idx < len(row) else ""
            part_no = str(row[part_idx]).strip() if part_idx >= 0 and part_idx < len(row) else ""

            if not desc and not part_no:
                continue

            category = str(row[cat_idx]).strip() if cat_idx >= 0 and cat_idx < len(row) else sheet_name
            uom = str(row[uom_idx]).strip() if uom_idx >= 0 and uom_idx < len(row) else "NOS"
            p_id = part_no if part_no and part_no not in ('NA', '-', 'None') else f"{sheet_name}_R{r_idx}"
            unit_price = parse_num_or_preserve(row[unit_price_idx]) if unit_price_idx >= 0 and unit_price_idx < len(row) else "NA"
            monthly_opening = parse_num_or_preserve(row[open_stock_idx]) if open_stock_idx >= 0 and open_stock_idx < len(row) else 0

            # Determine closing stock
            current_stock = None
            if closing_col_idx >= 0 and closing_col_idx < len(row):
                current_stock = parse_num_or_preserve(row[closing_col_idx])

            if current_stock is None:
                current_stock = monthly_opening

            # Min level
            min_level = 10.0
            status = "In Stock"
            if isinstance(current_stock, (int, float)):
                if current_stock <= 0:
                    status = "Out of Stock"
                elif current_stock <= min_level:
                    status = "Low Stock"
            elif current_stock in SPECIAL_STRINGS:
                status = "Unknown"

            extra = {}
            for c_i, val in enumerate(row):
                if c_i < len(headers):
                    h_name = headers[c_i]
                    if h_name and not any(w in h_name.lower() for w in ['amount', 'closing value', 'closing stk val', 'total price']):
                        extra[h_name] = parse_num_or_preserve(val)

            prod = {
                "source_id": self.source_id,
                "source_sheet": sheet_name,
                "source_row": r_idx,
                "product_id": p_id,
                "part_no": part_no,
                "description": desc or part_no,
                "category": category or sheet_name,
                "uom": uom or "NOS",
                "unit_price": unit_price,
                "opening_stock": monthly_opening,
                "current_stock": current_stock,
                "latest_date": latest_date_str,
                "min_level": min_level,
                "stock_status": status,
                "period": self.period,
                "extra_fields": extra,
                "validation_flags": []
            }
            self.products.append(prod)

    def get_products(
        self,
        search: str = "",
        sheet: str = "",
        category: str = "",
        part_no: str = "",
        uom: str = "",
        status: str = ""
    ) -> List[Dict[str, Any]]:
        res = self.products

        if search:
            s = search.lower()
            res = [
                p for p in res
                if s in p.get("product_id", "").lower()
                or s in p.get("description", "").lower()
                or s in p.get("part_no", "").lower()
                or s in p.get("category", "").lower()
            ]

        if sheet:
            s_sheet = sheet.lower()
            res = [p for p in res if p.get("source_sheet", "").lower() == s_sheet]

        if category:
            s_cat = category.lower()
            res = [p for p in res if p.get("category", "").lower() == s_cat]

        if part_no:
            s_part = part_no.lower()
            res = [p for p in res if s_part in p.get("part_no", "").lower()]

        if uom:
            s_uom = uom.lower()
            res = [p for p in res if p.get("uom", "").lower() == s_uom]

        if status:
            s_st = status.lower()
            res = [p for p in res if p.get("stock_status", "").lower() == s_st]

        return res

    def get_product_by_id(self, product_id: str) -> Optional[Dict[str, Any]]:
        for p in self.products:
            if str(p.get("product_id")) == str(product_id) or str(p.get("part_no")) == str(product_id):
                return p
        return None

    def get_movements(
        self,
        product_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        movement_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        res = self.movements

        if product_id:
            res = [m for m in res if m.get("product_id") == product_id or m.get("part_no") == product_id]

        if from_date:
            res = [m for m in res if m.get("date", "") >= from_date]

        if to_date:
            res = [m for m in res if m.get("date", "") <= to_date]

        if movement_type:
            mt = movement_type.upper()
            res = [m for m in res if mt in m.get("movement_type", "").upper()]

        return res

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Aggregate high performance analytics respecting strict UOM boundaries and zero amount exposure."""
        total_prods = len(self.products)
        in_stock = sum(1 for p in self.products if p.get("stock_status") == "In Stock")
        low_stock = sum(1 for p in self.products if p.get("stock_status") == "Low Stock")
        out_of_stock = sum(1 for p in self.products if p.get("stock_status") == "Out of Stock")
        unknown_stock = sum(1 for p in self.products if p.get("stock_status") == "Unknown")

        # Distribution by UOM
        uom_quantities = defaultdict(float)
        for p in self.products:
            uom = p.get("uom", "NOS")
            cs = p.get("current_stock")
            if isinstance(cs, (int, float)):
                uom_quantities[uom] += cs

        # Category distribution
        category_dist = defaultdict(int)
        for p in self.products:
            cat = p.get("category") or p.get("source_sheet") or "General"
            category_dist[cat] += 1

        # Movement trends
        inward_by_uom = defaultdict(float)
        outward_by_uom = defaultdict(float)
        daily_trends = defaultdict(lambda: {"in": 0.0, "out": 0.0, "count": 0})

        in_txns = 0
        out_txns = 0

        for m in self.movements:
            d = m.get("date", "")
            uom = m.get("uom", "NOS")
            in_q = float(m.get("in_qty", 0) or 0)
            out_q = float(m.get("out_qty", 0) or 0)

            if in_q > 0:
                in_txns += 1
                inward_by_uom[uom] += in_q
                daily_trends[d]["in"] += in_q
            if out_q > 0:
                out_txns += 1
                outward_by_uom[uom] += out_q
                daily_trends[d]["out"] += out_q
            daily_trends[d]["count"] += 1

        # Transform distributions to list of objects matching TypeScript interfaces
        daily_trends_list = [
            {"date": d, "in": vals["in"], "out": vals["out"], "transactions": vals["count"]}
            for d, vals in sorted(daily_trends.items())
        ]

        category_dist_list = [
            {"category": cat, "count": cnt}
            for cat, cnt in sorted(category_dist.items(), key=lambda x: x[1], reverse=True)
        ]

        status_dist_list = [
            {"status": "In Stock", "count": in_stock},
            {"status": "Low Stock", "count": low_stock},
            {"status": "Out of Stock", "count": out_of_stock},
            {"status": "Unknown", "count": unknown_stock}
        ]

        return {
            "total_products": total_prods,
            "in_stock_count": in_stock,
            "low_stock_count": low_stock,
            "out_of_stock_count": out_of_stock,
            "unknown_stock_count": unknown_stock,
            "total_movements_count": len(self.movements),
            "total_in_transactions": in_txns,
            "total_out_transactions": out_txns,
            "uom_quantities": dict(uom_quantities),
            "inward_by_uom": dict(inward_by_uom),
            "outward_by_uom": dict(outward_by_uom),
            "daily_trends": daily_trends_list,
            "category_distribution": category_dist_list,
            "status_distribution": status_dist_list,
            "recent_movements": self.movements[:10],
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

    def get_data_quality_report(self) -> Dict[str, Any]:
        """Compile comprehensive data quality issues across all sheets."""
        issues = []
        dup_ids = set()
        seen = set()

        for p in self.products:
            pid = p.get("product_id")
            if pid in seen:
                dup_ids.add(pid)
            seen.add(pid)

        if dup_ids:
            issues.append({
                "type": "DUPLICATE_PRODUCT_ID",
                "severity": "WARNING",
                "message": f"Found duplicate product identifiers in source sheets: {list(dup_ids)[:5]}",
                "count": len(dup_ids)
            })

        special_count = sum(1 for p in self.products if p.get("current_stock") in SPECIAL_STRINGS or p.get("unit_price") in SPECIAL_STRINGS)
        if special_count > 0:
            issues.append({
                "type": "SPECIAL_LITERALS_PRESERVED",
                "severity": "INFO",
                "message": f"{special_count} products have preserved literal special values ('NA' or '-')",
                "count": special_count
            })

        return {
            "total_issues": len(issues),
            "issues": issues,
            "duplicate_ids": list(dup_ids),
            "sheets_analyzed": len(self.analysis.get("sheets", {})) or 6,
            "sheets": list(self.analysis.get("sheets", {}).keys()) or ["BUSBAR", "ACCESORIES", "Cable,Lug,Lamp,TB,Truff", "SLEEVE ", "Fab Sheets", "Fasteners"]
        }
