import os
import re
import json
import logging
import difflib
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Standard semantic inventory roles
SEMANTIC_ROLES = [
    "product_id",      # Part No, Item Code, SKU, Material Code, Material ID
    "description",     # Product Description, Item Name, Particulars
    "category",        # Category, Group, Section, Material Type
    "uom",             # UOM, Unit, Measure, Packing
    "unit_price",      # Unit Price, Rate, Cost/Unit, Price (Never a stock quantity!)
    "opening_stock",   # Opening Stock, Op. Stock, Initial Balance, Opening
    "in_qty",          # In, Inward, Received, Receipt, Total In
    "out_qty",         # Out, Outward, Issued, Dispatch, Total Out
    "closing_stock",   # Closing Stock, Balance, Current Stock, Cl. Stock, Available
    "date",            # Transaction date or timeline column
    "unknown"          # Custom or unfamiliar business attribute (preserved!)
]

# Role Synonyms with weightings for semantic fuzzy matching
ROLE_SYNONYMS: Dict[str, List[str]] = {
    "product_id": [
        "part no", "part_no", "part number", "item code", "item no", "item number",
        "material code", "material id", "material_id", "product code", "product id",
        "product_id", "sku", "code", "catalog no", "cat no", "partcode", "article no"
    ],
    "description": [
        "description", "product description", "item description", "material description",
        "particulars", "item name", "material name", "product name", "details",
        "specification", "item details", "material details", "item"
    ],
    "category": [
        "category", "group", "product group", "material group", "section",
        "class", "type", "material type", "item category", "dept", "department"
    ],
    "uom": [
        "uom", "unit", "unit of measure", "unit of measurement", "measure",
        "packing", "pkg", "u.o.m", "units"
    ],
    "unit_price": [
        "unit price", "unit cost", "rate", "price", "rate/unit", "unit_price",
        "price/unit", "rate (rs)", "cost per unit", "purchase rate", "mrp"
    ],
    "opening_stock": [
        "opening stock", "op stock", "op. stock", "initial balance", "opening balance",
        "opening qty", "op qty", "opening", "beg balance", "starting stock", "op.stk",
        "monthly opening", "month open", "opening_stock"
    ],
    "in_qty": [
        "in", "inward", "received", "receipt", "receipts", "total in", "in qty",
        "in_qty", "incoming", "purchase qty", "inwards", "qty in"
    ],
    "out_qty": [
        "out", "outward", "issued", "issue", "issues", "total out", "out qty",
        "out_qty", "dispatch", "outgoing", "sales qty", "outwards", "qty out"
    ],
    "closing_stock": [
        "closing stock", "current stock", "stock balance", "balance", "closing balance",
        "cl stock", "cl. stock", "closing qty", "closing", "ending balance", "stock",
        "available stock", "qty on hand", "closing_stock", "cl.stk", "total stock"
    ],
    "date": [
        "date", "transaction date", "movement date", "entry date", "day", "txn date"
    ]
}

# Strictly forbidden amount / currency total keywords to prevent misidentifying amount as stock
AMOUNT_KEYWORDS = [
    "amount", "total amount", "total cost", "total price", "line total",
    "ext price", "extended price", "val", "value", "closing value",
    "closing stk val", "total value", "amount (rs)"
]


class LLMProvider:
    """Abstract LLM Provider interface."""
    def suggest_mappings(self, sheet_name: str, columns: List[Dict[str, Any]]) -> Dict[str, Any]:
        raise NotImplementedError


class GeminiProvider(LLMProvider):
    """Google Gemini AI integration using GEMINI_API_KEY if configured."""
    def __init__(self, api_key: str):
        self.api_key = api_key

    def suggest_mappings(self, sheet_name: str, columns: List[Dict[str, Any]]) -> Dict[str, Any]:
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = f"""
You are an expert spreadsheet analyst. Analyze the following worksheet and columns from a stock management system.
Worksheet Name: "{sheet_name}"
Columns:
{json.dumps(columns, indent=2)}

Assign the most appropriate semantic role to each column from:
["product_id", "description", "category", "uom", "unit_price", "opening_stock", "in_qty", "out_qty", "closing_stock", "date", "unknown"]

Rules:
1. Never assign price or amount columns to stock quantities.
2. Return a JSON object mapping each original column name to:
   {{"role": "<role>", "confidence": <float 0.0-1.0>, "reason": "<explanation>"}}
3. Do not invent missing values. Output valid JSON only.
"""
            response = model.generate_content(prompt)
            text = response.text.strip()
            # Clean possible markdown code fence
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?", "", text)
                text = re.sub(r"```$", "", text).strip()
            return json.loads(text)
        except Exception as e:
            logger.warning(f"Gemini AI mapping suggestion failed: {e}. Falling back to heuristic ML.")
            return {}


class OpenAIProvider(LLMProvider):
    """OpenAI integration using OPENAI_API_KEY if configured."""
    def __init__(self, api_key: str):
        self.api_key = api_key

    def suggest_mappings(self, sheet_name: str, columns: List[Dict[str, Any]]) -> Dict[str, Any]:
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            prompt = f"""
Analyze the following worksheet and columns from an inventory spreadsheet.
Worksheet Name: "{sheet_name}"
Columns:
{json.dumps(columns, indent=2)}

Assign the most appropriate semantic role to each column from:
["product_id", "description", "category", "uom", "unit_price", "opening_stock", "in_qty", "out_qty", "closing_stock", "date", "unknown"]

Return JSON only mapping original column name to {{"role": "<role>", "confidence": <float 0.0-1.0>, "reason": "<explanation>"}}.
"""
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            text = resp.choices[0].message.content.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?", "", text)
                text = re.sub(r"```$", "", text).strip()
            return json.loads(text)
        except Exception as e:
            logger.warning(f"OpenAI mapping suggestion failed: {e}. Falling back to heuristic ML.")
            return {}


class HeuristicMLProvider(LLMProvider):
    """Rule-based, statistical, and fuzzy-matching engine that runs 100% locally and deterministically."""

    @staticmethod
    def calculate_similarity(name: str, target: str) -> float:
        """Calculate normalized similarity between two strings."""
        return difflib.SequenceMatcher(None, name.lower(), target.lower()).ratio()

    def suggest_mappings(self, sheet_name: str, columns: List[Dict[str, Any]]) -> Dict[str, Any]:
        suggestions = {}
        for col in columns:
            orig = col.get("original_name", "")
            norm = col.get("normalized_name", "")
            col_type = col.get("data_type", "text")
            samples = col.get("sample_values", [])

            # Check if serial number or row index
            SERIAL_NO_KEYWORDS = ['sl_no', 's_no', 'si_no', 'sno', 'sino', 'sr_no', 'serial_no', 'line_no', 'slno', 's_n']
            if any(norm == k or norm.startswith(f"{k}_") for k in SERIAL_NO_KEYWORDS):
                suggestions[orig] = {
                    "role": "unknown",
                    "confidence": 0.95,
                    "reason": "Identified as row index / serial number."
                }
                continue

            # Check if column is an amount column
            if any(k in norm for k in AMOUNT_KEYWORDS):
                suggestions[orig] = {
                    "role": "unknown",  # Do not assign to stock quantity, retain as financial attribute
                    "confidence": 0.95,
                    "reason": "Identified as financial/amount column. Kept as non-inventory attribute."
                }
                continue

            # Check if date
            if col_type == "date" or any(w in norm for w in ["date", "day", "txn date"]):
                suggestions[orig] = {
                    "role": "date",
                    "confidence": 0.90,
                    "reason": "Date pattern or column name indicates timeline/transaction date."
                }
                continue

            # Calculate match score against all semantic roles
            best_role = "unknown"
            best_score = 0.0

            for role, synonyms in ROLE_SYNONYMS.items():
                for syn in synonyms:
                    # Exact match
                    if norm == syn:
                        score = 1.0
                    elif syn in norm:
                        score = 0.85
                    elif norm in syn:
                        score = 0.80
                    else:
                        sim = self.calculate_similarity(norm, syn)
                        score = sim * 0.75

                    if score > best_score:
                        best_score = score
                        best_role = role

            # Value-based inference adjustments
            if best_role in ["product_id", "unknown"] and samples:
                # If sample values look like part codes (alphanumeric, e.g. "SB-101", "CBL-04")
                if all(re.match(r'^[A-Za-z0-9\-_./]{2,25}$', str(s)) for s in samples if str(s).strip()):
                    if best_role == "unknown" and best_score < 0.6:
                        best_role = "product_id"
                        best_score = 0.75

            # If type is numeric and role is product_id, but name contains stock/qty, rectify
            if col_type in ["integer", "float"] and best_role == "product_id" and any(k in norm for k in ["stock", "qty", "bal"]):
                best_role = "closing_stock"
                best_score = 0.85

            confidence = round(min(1.0, max(0.2, best_score)), 2)
            if best_score < 0.55:
                best_role = "unknown"
                confidence = 0.40

            suggestions[orig] = {
                "role": best_role,
                "confidence": confidence,
                "reason": f"Fuzzy matched to {best_role} with confidence {confidence}."
            }

        return suggestions


class IntelligenceEngine:
    """Core intelligence engine coordinating universal data recognition, profiling, and quality analysis."""

    def __init__(self):
        self.heuristic_provider = HeuristicMLProvider()
        # Initialize LLM providers if environment keys exist
        self.llm_provider: Optional[LLMProvider] = None
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        openai_key = os.getenv("OPENAI_API_KEY", "")
        if gemini_key:
            self.llm_provider = GeminiProvider(gemini_key)
        elif openai_key:
            self.llm_provider = OpenAIProvider(openai_key)

    @staticmethod
    def normalize_column_name(col_name: str) -> str:
        """Normalize column name to lowercase, alphanumeric and underscores."""
        s = re.sub(r'[^\w\s]', ' ', str(col_name).strip().lower())
        return re.sub(r'\s+', '_', s).strip('_')

    @staticmethod
    def infer_data_type(values: List[Any]) -> str:
        """Infer whether column values are integer, float, date, boolean, or text."""
        non_empty = [v for v in values if v is not None and str(v).strip() != "" and str(v).strip().upper() not in ["NA", "N/A", "-"]]
        if not non_empty:
            return "text"

        date_matches = 0
        int_matches = 0
        float_matches = 0
        bool_matches = 0

        for val in non_empty:
            s = str(val).strip()
            if s.lower() in ['true', 'false', 'yes', 'no']:
                bool_matches += 1
                continue

            # Check date pattern
            if any(re.search(p, s) for p in [r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}', r'^\d{1,2}[-/]\d{1,2}[-/]\d{4}']):
                date_matches += 1
                continue

            try:
                cleaned = s.replace(',', '')
                if '.' in cleaned:
                    float(cleaned)
                    float_matches += 1
                else:
                    int(cleaned)
                    int_matches += 1
            except ValueError:
                pass

        total = len(non_empty)
        if date_matches / total >= 0.7:
            return "date"
        if bool_matches / total >= 0.8:
            return "boolean"
        if (int_matches + float_matches) / total >= 0.75:
            return "float" if float_matches > 0 else "integer"
        return "text"

    def profile_worksheet(self, sheet_name: str, values: List[List[Any]], header_rows: List[int], headers: List[str], data_start_row: int) -> Dict[str, Any]:
        """Profile all columns, extract statistical properties, and classify the worksheet."""
        data_rows = values[data_start_row - 1:] if len(values) >= data_start_row else []
        total_data_rows = len(data_rows)

        columns_profile = []
        for col_idx, h in enumerate(headers):
            col_cells = [r[col_idx] for r in data_rows if len(r) > col_idx]
            non_empty_cells = [c for c in col_cells if c is not None and str(c).strip() != ""]

            populated_pct = round((len(non_empty_cells) / total_data_rows * 100), 1) if total_data_rows > 0 else 0
            unique_vals = list(set(str(c).strip() for c in non_empty_cells))
            sample_vals = [s for s in unique_vals[:5] if s not in ["NA", "N/A", "-"]]

            inferred_type = self.infer_data_type(col_cells[:100])
            norm_name = self.normalize_column_name(h)

            columns_profile.append({
                "column_index": col_idx,
                "original_name": h,
                "normalized_name": norm_name,
                "data_type": inferred_type,
                "populated_pct": populated_pct,
                "unique_count": len(unique_vals),
                "sample_values": sample_vals
            })

        # Get AI or Heuristic semantic suggestions
        suggestions = {}
        if self.llm_provider:
            try:
                suggestions = self.llm_provider.suggest_mappings(sheet_name, columns_profile)
            except Exception as e:
                logger.warning(f"LLM suggestion failed: {e}")

        # If LLM didn't return or was incomplete, fill with local heuristic engine
        heuristic_suggestions = self.heuristic_provider.suggest_mappings(sheet_name, columns_profile)
        for col in columns_profile:
            orig = col["original_name"]
            if orig in suggestions and suggestions[orig].get("role"):
                col["inferred_role"] = suggestions[orig]["role"]
                col["confidence"] = suggestions[orig].get("confidence", 0.85)
                col["reason"] = suggestions[orig].get("reason", "Inferred by AI")
            else:
                h_res = heuristic_suggestions.get(orig, {"role": "unknown", "confidence": 0.40, "reason": "Default"})
                col["inferred_role"] = h_res["role"]
                col["confidence"] = h_res["confidence"]
                col["reason"] = h_res["reason"]

            col["requires_review"] = 1 if col["confidence"] < 0.80 or col["inferred_role"] == "unknown" else 0

        # Classify worksheet
        assigned_roles = [c["inferred_role"] for c in columns_profile]
        has_product = "product_id" in assigned_roles
        has_stock = any(r in assigned_roles for r in ["closing_stock", "opening_stock"])
        has_movement = any(r in assigned_roles for r in ["in_qty", "out_qty"])
        has_date = "date" in assigned_roles

        if has_product and has_stock:
            classification = "inventory_summary"
        elif has_movement or has_date:
            classification = "stock_movement"
        elif "unit_price" in assigned_roles and has_product:
            classification = "price_catalog"
        elif has_product:
            classification = "reference_catalog"
        else:
            classification = "general_data"

        # Quality analysis & anomaly detection
        quality_issues = []
        duplicate_candidates = []

        # Check duplicate product IDs if product_id column exists
        pk_cols = [c for c in columns_profile if c["inferred_role"] == "product_id"]
        if pk_cols:
            pk_idx = pk_cols[0]["column_index"]
            seen_keys: Dict[str, int] = {}
            for r_idx, r in enumerate(data_rows):
                if len(r) > pk_idx:
                    k = str(r[pk_idx]).strip()
                    if k and k.upper() not in ["NA", "-", "TOTAL", "SUBTOTAL"]:
                        seen_keys[k] = seen_keys.get(k, 0) + 1
            duplicate_candidates = [k for k, count in seen_keys.items() if count > 1]
            if duplicate_candidates:
                quality_issues.append(f"Detected {len(duplicate_candidates)} duplicate product identifiers (e.g. {duplicate_candidates[:3]}).")

        # Check for unmapped required inventory columns
        missing_roles = []
        if classification == "inventory_summary":
            for req in ["product_id", "description", "closing_stock"]:
                if req not in assigned_roles:
                    missing_roles.append(req)
        if missing_roles:
            quality_issues.append(f"Worksheet may be missing key inventory attributes: {', '.join(missing_roles)}")

        quality_score = 100
        quality_score -= min(30, len(duplicate_candidates) * 5)
        quality_score -= min(20, sum(1 for c in columns_profile if c["requires_review"]) * 3)
        quality_score -= min(20, len(quality_issues) * 5)
        quality_score = max(20, quality_score)

        return {
            "sheet_name": sheet_name,
            "classification": classification,
            "header_rows": header_rows,
            "data_start_row": data_start_row,
            "row_count": total_data_rows,
            "column_count": len(headers),
            "columns": columns_profile,
            "quality_score": quality_score,
            "quality_issues": quality_issues,
            "duplicate_candidates": duplicate_candidates[:20]
        }
