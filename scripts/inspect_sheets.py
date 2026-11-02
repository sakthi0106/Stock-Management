#!/usr/bin/env python3
"""
Inspect all worksheets in the Google Spreadsheet, analyzing:
- Headers and header row indices
- Total row and column counts
- Merged ranges and formulas
- Date, stock, and unit price columns
- Explicitly identifying and isolating Amount columns to ensure zero leakage
- Preserving 'NA' and '-' literals
- Exporting a comprehensive sheet_analysis.json report
"""

import sys
import json
import logging
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from config import Config
from sheets_client import GoogleSheetsClient
from sheet_analyzer import SheetAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("inspect_sheets")

def run_inspection(output_path: Path = None):
    if output_path is None:
        output_path = backend_dir.parent / "sheet_analysis.json"

    logger.info("Initializing Google Sheets connection...")
    client = GoogleSheetsClient()
    
    if client.is_configured():
        logger.info(f"Connected to Live Google Sheets API v4 with Spreadsheet ID: {Config.GOOGLE_SHEETS_SPREADSHEET_ID}")
    else:
        logger.warning("Google Sheets credentials / Spreadsheet ID not provided yet.")
        logger.warning("Running inspection on verified multi-sheet inventory dataset...")

    analyzer = SheetAnalyzer(client)
    report = analyzer.analyze_all_sheets()

    # Save to JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info(f"Sheet analysis report successfully generated: {output_path}")
    print("\n" + "=" * 70)
    print("GOOGLE SHEETS INSPECTION SUMMARY")
    print("=" * 70)
    print(f"Spreadsheet Title   : {report.get('title')}")
    print(f"Sheets Found        : {report.get('sheets_count')}")
    print(f"Connection Status   : {'LIVE GOOGLE SHEETS' if report.get('is_configured') else 'DEMO / SIMULATION (Awaiting Google Credentials)'}")
    print("-" * 70)

    for sheet_name, s_info in report.get("sheets", {}).items():
        print(f"\nWorksheet: [{sheet_name}]")
        print(f"  Rows: {s_info.get('row_count')}, Cols: {s_info.get('column_count')}, Data Starts: Row {s_info.get('data_start_row')}")
        print(f"  Headers: {', '.join(s_info.get('headers', []))}")
        if s_info.get("product_key_candidates"):
            print(f"  Product Key Col   : {s_info.get('product_key_candidates')}")
        if s_info.get("unit_price_candidates"):
            print(f"  Unit Price Col    : {s_info.get('unit_price_candidates')}")
        if s_info.get("amount_columns"):
            print(f"  Amount Col (FILTERED OUT) : {s_info.get('amount_columns')}")
        if s_info.get("special_values"):
            print(f"  Preserved Literals: {s_info.get('special_values')}")
        if s_info.get("issues"):
            print(f"  Warnings/Issues   : {s_info.get('issues')}")

    print("\n" + "=" * 70)
    return report

if __name__ == "__main__":
    run_inspection()
