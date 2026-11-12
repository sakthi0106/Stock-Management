import re
import datetime
import logging
from typing import Dict, List, Any, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Reserved quantity exclusion keywords (Amounts, rates, values must never be stock quantities)
EXCLUDED_QTY_TERMS = {
    'amount', 'rate', 'price', 'value', 'cost', 'val', 'closing val', 'total amount',
    'total value', 'unit rate', 'unit price', 'amt', 'purchase price'
}

# Semantic IN keywords
IN_KEYWORDS = {
    'in', 'inward', 'inwards', 'received', 'receipt', 'receipts', 'rcvd', 'rcpt',
    'total in', 'in qty', 'qty in', 'inward qty', 'receipt quantity', 'purchase qty',
    'stock in', 'inbound', 'incoming'
}

# Semantic OUT keywords
OUT_KEYWORDS = {
    'out', 'outward', 'outwards', 'issued', 'issue', 'issues', 'dispatch', 'dispatched',
    'total out', 'out qty', 'qty out', 'outward qty', 'issue quantity', 'consumption qty',
    'stock out', 'outbound', 'outgoing', 'sales qty'
}

# Special string representations
SPECIAL_EMPTY = {'', 'none', 'null', 'nan', '-', 'na', 'n/a', 'n.a.', 'nil'}


def parse_numeric(val: Any) -> Optional[float]:
    """Parses numeric value safely without turning text/empty into fake zeroes."""
    if val is None:
        return None
    s = str(val).strip().lower()
    if s in SPECIAL_EMPTY:
        return None
    # Strip currency symbols and formatting commas
    cleaned = re.sub(r'[\$,₹\s]', '', s)
    try:
        f = float(cleaned)
        return int(f) if f.is_integer() else f
    except ValueError:
        return None


def parse_date_string(val: Any, default_year_month: Optional[str] = None) -> Optional[str]:
    """Robust date parsing for standard dates, day numbers (1..31), and composite headers (e.g. '01-10-2026 IN', '1 IN')."""
    if val is None:
        return None

    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.strftime('%Y-%m-%d')

    s = str(val).strip()
    if not s or s.lower() in SPECIAL_EMPTY:
        return None

    # Handle Excel numeric serial dates (e.g., 45597 -> ~2024-11-01)
    try:
        num = float(s)
        if 35000 <= num <= 65000:
            base = datetime.date(1899, 12, 30)
            d = base + datetime.timedelta(days=int(num))
            return d.strftime('%Y-%m-%d')
    except (ValueError, OverflowError):
        pass

    # Standard YYYY-MM-DD
    m1 = re.search(r'\b(20\d{2})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])\b', s)
    if m1:
        y, m, d = m1.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    # Standard DD-MM-YYYY
    m2 = re.search(r'\b(0?[1-9]|[12]\d|3[01])[-/.](0?[1-9]|1[0-2])[-/.](20\d{2})\b', s)
    if m2:
        d, m, y = m2.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    # Month name patterns like '01-Oct-2026', '1-Nov', 'Nov 1'
    months = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }
    m3 = re.search(r'\b(0?[1-9]|[12]\d|3[01])[-/\s]([A-Za-z]{3})[-/\s]?(20\d{2})?\b', s)
    if m3:
        d_str, mon_str, y_str = m3.groups()
        mon = months.get(mon_str.lower()[:3])
        if mon:
            y = int(y_str) if y_str else datetime.date.today().year
            return f"{y:04d}-{mon:02d}-{int(d_str):02d}"

    # Day number in composite header e.g. "1 IN", "15 OUT", "Day 3 IN", "04 OUT"
    m4 = re.search(r'^(?:day\s*)?(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?(?:\s+.*)?$', s, re.IGNORECASE)
    if m4:
        day_num = int(m4.group(1))
        if 1 <= day_num <= 31:
            if default_year_month and re.match(r'^\d{4}-\d{2}$', default_year_month):
                y, m = map(int, default_year_month.split('-'))
                try:
                    return f"{y:04d}-{m:02d}-{day_num:02d}"
                except ValueError:
                    pass
            today = datetime.date.today()
            return f"{today.year:04d}-{today.month:02d}-{day_num:02d}"

    return None


class UniversalParser:
    """Universal parser for inventory catalogs, date-wise grids, transaction registers, and summary registers."""

    @classmethod
    def clean_headers(cls, raw_headers: List[Any]) -> List[str]:
        return [str(h).strip() if h is not None else "" for h in raw_headers]

    @classmethod
    def detect_header_rows(cls, rows: List[List[Any]]) -> Tuple[List[str], int]:
        """Detects single or merged 2-row headers and combines parent with child cells."""
        if not rows:
            return [], 0
        if len(rows) == 1:
            return cls.clean_headers(rows[0]), 1

        r0 = cls.clean_headers(rows[0])
        r1 = cls.clean_headers(rows[1])

        # Check if row 1 contains IN / OUT sub-headers
        in_out_count = sum(1 for c in r1 if c.lower() in ('in', 'out', 'inward', 'outward', 'rcvd', 'issued', 'receipt', 'issue'))
        if in_out_count >= 2:
            combined = []
            curr_parent = ""
            max_len = max(len(r0), len(r1))
            for i in range(max_len):
                top_val = r0[i] if i < len(r0) else ""
                sub_val = r1[i] if i < len(r1) else ""
                if top_val:
                    curr_parent = top_val
                if curr_parent and sub_val:
                    combined.append(f"{curr_parent} {sub_val}".strip())
                elif sub_val:
                    combined.append(sub_val)
                elif curr_parent:
                    combined.append(curr_parent)
                else:
                    combined.append(f"Col_{i+1}")
            return combined, 2

        # Otherwise single header row at index 0 or index 1
        for idx in range(min(3, len(rows))):
            h = cls.clean_headers(rows[idx])
            has_part = any(k in c.lower() for c in h for k in ['part', 'item', 'code', 'description', 'sku', 'product'])
            if has_part:
                return h, idx + 1

        return r0, 1

    @classmethod
    def classify_columns(cls, headers: List[str]) -> Dict[str, Any]:
        """Identifies semantic roles of headers."""
        roles = {
            'part_no': None,
            'description': None,
            'category': None,
            'uom': None,
            'opening_stock': None,
            'in_qty': None,
            'out_qty': None,
            'closing_stock': None,
            'unit_price': None,
            'date': None,
            'date_movement_pairs': []  # list of (col_idx, date_str, 'IN'|'OUT')
        }

        unit_price_exact = ('unit price', 'unit_price', 'unit rate', 'unit cost', 'purchase price', 'selling price', 'mrp')
        unit_price_fallback = ('rate', 'price', 'cost')

        for idx, h in enumerate(headers):
            hl = h.lower().replace('_', ' ').strip()
            if any(k in hl for k in unit_price_exact):
                if roles['unit_price'] is None:
                    roles['unit_price'] = idx
            elif roles['unit_price'] is None and any(k == hl or re.search(rf'\b{k}\b', hl) for k in unit_price_fallback):
                if not any(tot in hl for tot in ('total', 'closing', 'opening', 'value', 'amount')):
                    roles['unit_price'] = idx

            if any(term in hl for term in EXCLUDED_QTY_TERMS):
                continue

            # Check for date-movement pairs (e.g. '01-10-2026 IN', '1 IN')
            dt = parse_date_string(h)
            if dt:
                is_in = any(k in hl for k in ['in', 'rcvd', 'receipt', 'inward', 'received'])
                is_out = any(k in hl for k in ['out', 'issue', 'issued', 'outward', 'dispatch'])
                if is_in and not is_out:
                    roles['date_movement_pairs'].append((idx, dt, 'IN'))
                    continue
                elif is_out and not is_in:
                    roles['date_movement_pairs'].append((idx, dt, 'OUT'))
                    continue

            # Standard roles
            if roles['part_no'] is None and any(k in hl for k in ['part no', 'part_no', 'item code', 'item no', 'code', 'sku', 'part number']):
                roles['part_no'] = idx
            elif roles['description'] is None and any(k in hl for k in ['description', 'item description', 'product name', 'item name', 'particulars']):
                roles['description'] = idx
            elif roles['category'] is None and any(k in hl for k in ['category', 'group', 'type', 'section']):
                roles['category'] = idx
            elif roles['uom'] is None and any(k in hl for k in ['uom', 'unit', 'measure']):
                roles['uom'] = idx
            elif roles['opening_stock'] is None and any(k in hl for k in ['opening', 'op. stock', 'initial balance', 'open stock']):
                roles['opening_stock'] = idx
            elif roles['closing_stock'] is None and any(k in hl for k in ['closing', 'cl. stock', 'balance', 'available', 'current stock']):
                roles['closing_stock'] = idx
            elif roles['in_qty'] is None and any(k in hl for k in IN_KEYWORDS):
                roles['in_qty'] = idx
            elif roles['out_qty'] is None and any(k in hl for k in OUT_KEYWORDS):
                roles['out_qty'] = idx
            elif roles['date'] is None and 'date' in hl:
                roles['date'] = idx

        # Fallback for part_no / description if missing
        if roles['part_no'] is None and len(headers) > 0:
            roles['part_no'] = 0
        if roles['description'] is None and len(headers) > 1:
            roles['description'] = 1

        return roles
