"""
Sample Excel Generator for Stock Management Dashboard
Generates realistic multi-sheet and single-sheet enterprise inventory workbooks:
- Sheet 1: "Stock Summary" (Products, codes, categories, units, min thresholds, balances)
- Sheet 2: "Inward Register" (Dates, Product Codes, Quantities, Suppliers, PO Numbers, Remarks)
- Sheet 3: "Outward Register" (Dates, Product Codes, Quantities, Recipients/Departments, Work Orders, Remarks)
"""

import os
from datetime import datetime, timedelta
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

def create_sample_workbook(filepath: str):
    wb = openpyxl.Workbook()
    
    # -------------------------------------------------------------
    # 1. Sheet 1: Current Stock Summary
    # -------------------------------------------------------------
    ws_summary = wb.active
    ws_summary.title = "Stock Summary"
    ws_summary.views.sheetView[0].showGridLines = True
    
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Segoe UI", size=10)
    thin_border = Border(
        left=Side(style='thin', color='E2E8F0'),
        right=Side(style='thin', color='E2E8F0'),
        top=Side(style='thin', color='E2E8F0'),
        bottom=Side(style='thin', color='E2E8F0')
    )
    
    headers_summary = [
        "Product Code", "Product Name", "Category", "Unit of Measure", 
        "Opening Stock", "Total Inward", "Total Outward", "Current Balance", 
        "Min Threshold", "Unit Cost (USD)", "Location / Bin"
    ]
    ws_summary.append(headers_summary)
    for col_num in range(1, len(headers_summary) + 1):
        cell = ws_summary.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    products = [
        ("PRD-1001", "Heavy Duty Steel Hex Bolt M12x50", "Fasteners", "PCS", 500, 1200, 850, 850, 300, 0.45, "Aisle A-01"),
        ("PRD-1002", "Stainless Steel Washer 12mm", "Fasteners", "PCS", 1200, 2500, 2900, 800, 500, 0.12, "Aisle A-02"),
        ("PRD-1003", "Grade 8 Nylon Lock Nut M12", "Fasteners", "PCS", 400, 1000, 1250, 150, 250, 0.35, "Aisle A-03"),  # Low stock
        ("PRD-2001", "Industrial Gear Oil ISO VG 220", "Lubricants", "LTR", 200, 450, 410, 240, 100, 14.50, "Bay B-04"),
        ("PRD-2002", "High-Temp Lithium Grease EP2", "Lubricants", "KG", 80, 150, 220, 10, 25, 9.80, "Bay B-05"),    # Low stock
        ("PRD-2003", "Hydraulic Fluid AW-68", "Lubricants", "LTR", 500, 1000, 1500, 0, 150, 11.20, "Bay B-06"),      # Out of stock
        ("PRD-3001", "Seamless Carbon Steel Pipe 2-inch", "Raw Materials", "MTR", 150, 300, 270, 180, 50, 32.00, "Yard C-01"),
        ("PRD-3002", "Alloy Structural Steel Plate 10mm", "Raw Materials", "KG", 2500, 5000, 4200, 3300, 1000, 2.75, "Yard C-02"),
        ("PRD-4001", "Nitrile Protective Gloves (Box of 100)", "Safety Gear", "BOX", 45, 120, 135, 30, 20, 18.00, "Storage D-1"),
        ("PRD-4002", "ANSI Z87.1 Safety Glasses", "Safety Gear", "PCS", 60, 100, 152, 8, 25, 5.50, "Storage D-2"),     # Low stock
        ("PRD-4003", "Reflective Safety Vest High-Vis", "Safety Gear", "PCS", 80, 150, 110, 120, 30, 8.20, "Storage D-3"),
        ("PRD-5001", "Ball Bearing 6205-2RS Deep Groove", "Bearings", "PCS", 110, 200, 265, 45, 40, 16.50, "Aisle E-01"),
        ("PRD-5002", "Tapered Roller Bearing 32208", "Bearings", "PCS", 35, 80, 70, 45, 20, 28.00, "Aisle E-02"),
        ("PRD-6001", "Digital Vernier Caliper 150mm", "Tools & Instruments", "SET", 15, 25, 12, 28, 10, 65.00, "Secure Cab 1"),
        ("PRD-6002", "Heavy Duty Air Impact Wrench 1/2-inch", "Tools & Instruments", "PCS", 8, 12, 19, 1, 5, 185.00, "Secure Cab 2"), # Low stock
    ]
    
    for row_idx, item in enumerate(products, start=2):
        ws_summary.append(list(item))
        for col_idx in range(1, len(item) + 1):
            c = ws_summary.cell(row=row_idx, column=col_idx)
            c.font = data_font
            c.border = thin_border
            if col_idx in [5, 6, 7, 8, 9, 10]:
                c.alignment = Alignment(horizontal="right")
                
    # Auto-adjust column widths
    for col in ws_summary.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws_summary.column_dimensions[col_letter].width = max(max_len + 3, 12)
        
    # -------------------------------------------------------------
    # 2. Sheet 2: Inward Register
    # -------------------------------------------------------------
    ws_inward = wb.create_sheet(title="Inward Register")
    ws_inward.views.sheetView[0].showGridLines = True
    headers_inward = [
        "Transaction Date", "Transaction ID", "Product Code", "Product Name",
        "Quantity Received", "Unit", "Supplier Name", "PO Number", "Delivery Challan", "Received By", "Remarks"
    ]
    ws_inward.append(headers_inward)
    inward_fill = PatternFill(start_color="065F46", end_color="065F46", fill_type="solid")
    for col_num in range(1, len(headers_inward) + 1):
        cell = ws_inward.cell(row=1, column=col_num)
        cell.fill = inward_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        
    base_date = datetime.now() - timedelta(days=45)
    inward_records = [
        (base_date + timedelta(days=2), "TXN-INW-001", "PRD-1001", "Heavy Duty Steel Hex Bolt M12x50", 500, "PCS", "Apex Fasteners Ltd", "PO-2026-091", "DC-7701", "John Doe", "Stock replenishment"),
        (base_date + timedelta(days=5), "TXN-INW-002", "PRD-1002", "Stainless Steel Washer 12mm", 1000, "PCS", "Apex Fasteners Ltd", "PO-2026-092", "DC-7712", "John Doe", "Standard lot"),
        (base_date + timedelta(days=8), "TXN-INW-003", "PRD-2001", "Industrial Gear Oil ISO VG 220", 250, "LTR", "PetroChem Industries", "PO-2026-104", "DC-8102", "Sarah Jenkins", "Drum packaging intact"),
        (base_date + timedelta(days=12), "TXN-INW-004", "PRD-3001", "Seamless Carbon Steel Pipe 2-inch", 150, "MTR", "Metals Unlimited Corp", "PO-2026-115", "DC-9022", "Mike Miller", "Mill test cert verified"),
        (base_date + timedelta(days=15), "TXN-INW-005", "PRD-4001", "Nitrile Protective Gloves (Box of 100)", 60, "BOX", "SafetyFirst Supplies", "PO-2026-121", "DC-4311", "John Doe", "Q2 safety consumables"),
        (base_date + timedelta(days=18), "TXN-INW-006", "PRD-1001", "Heavy Duty Steel Hex Bolt M12x50", 700, "PCS", "Apex Fasteners Ltd", "PO-2026-130", "DC-7798", "Sarah Jenkins", "Supplementary order"),
        (base_date + timedelta(days=22), "TXN-INW-007", "PRD-5001", "Ball Bearing 6205-2RS Deep Groove", 100, "PCS", "Precision Bearings Co", "PO-2026-145", "DC-1093", "Mike Miller", "Sealed pack"),
        (base_date + timedelta(days=28), "TXN-INW-008", "PRD-2002", "High-Temp Lithium Grease EP2", 50, "KG", "PetroChem Industries", "PO-2026-155", "DC-8240", "Sarah Jenkins", "Urgent maintenance request"),
        (base_date + timedelta(days=32), "TXN-INW-009", "PRD-6001", "Digital Vernier Caliper 150mm", 15, "SET", "Precision Tools Ltd", "PO-2026-168", "DC-3301", "John Doe", "Calibration certified"),
        (base_date + timedelta(days=38), "TXN-INW-010", "PRD-3002", "Alloy Structural Steel Plate 10mm", 2500, "KG", "Metals Unlimited Corp", "PO-2026-180", "DC-9210", "Mike Miller", "Heavy crane offloaded"),
    ]
    
    for row_idx, item in enumerate(inward_records, start=2):
        row_data = list(item)
        row_data[0] = row_data[0].strftime("%Y-%m-%d")
        ws_inward.append(row_data)
        for col_idx in range(1, len(row_data) + 1):
            c = ws_inward.cell(row=row_idx, column=col_idx)
            c.font = data_font
            c.border = thin_border
            if col_idx == 5:
                c.alignment = Alignment(horizontal="right")
                
    for col in ws_inward.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws_inward.column_dimensions[col_letter].width = max(max_len + 3, 12)

    # -------------------------------------------------------------
    # 3. Sheet 3: Outward Register
    # -------------------------------------------------------------
    ws_outward = wb.create_sheet(title="Outward Register")
    ws_outward.views.sheetView[0].showGridLines = True
    headers_outward = [
        "Transaction Date", "Transaction ID", "Product Code", "Product Name",
        "Quantity Issued", "Unit", "Issued To / Department", "Work Order / Project", "Dispatched By", "Remarks"
    ]
    ws_outward.append(headers_outward)
    outward_fill = PatternFill(start_color="991B1B", end_color="991B1B", fill_type="solid")
    for col_num in range(1, len(headers_outward) + 1):
        cell = ws_outward.cell(row=1, column=col_num)
        cell.fill = outward_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        
    outward_records = [
        (base_date + timedelta(days=6), "TXN-OUT-001", "PRD-1001", "Heavy Duty Steel Hex Bolt M12x50", 350, "PCS", "Assembly Line 1", "WO-4011", "John Doe", "Chassis assembly"),
        (base_date + timedelta(days=9), "TXN-OUT-002", "PRD-1002", "Stainless Steel Washer 12mm", 1200, "PCS", "Assembly Line 1", "WO-4011", "John Doe", "Chassis assembly"),
        (base_date + timedelta(days=14), "TXN-OUT-003", "PRD-2001", "Industrial Gear Oil ISO VG 220", 180, "LTR", "Heavy Machining Shop", "WO-4025", "Sarah Jenkins", "Machine overhaul"),
        (base_date + timedelta(days=19), "TXN-OUT-004", "PRD-4001", "Nitrile Protective Gloves (Box of 100)", 40, "BOX", "Safety & Hygiene Dept", "WO-GEN", "John Doe", "Monthly safety quota"),
        (base_date + timedelta(days=24), "TXN-OUT-005", "PRD-1001", "Heavy Duty Steel Hex Bolt M12x50", 500, "PCS", "Fabrication Line 2", "WO-4033", "Sarah Jenkins", "Conveyor structure"),
        (base_date + timedelta(days=26), "TXN-OUT-006", "PRD-5001", "Ball Bearing 6205-2RS Deep Groove", 65, "PCS", "Maintenance Team", "WO-4039", "Mike Miller", "Motor replacement"),
        (base_date + timedelta(days=30), "TXN-OUT-007", "PRD-2002", "High-Temp Lithium Grease EP2", 25, "KG", "Maintenance Team", "WO-4045", "Sarah Jenkins", "Routine PM"),
        (base_date + timedelta(days=35), "TXN-OUT-008", "PRD-4002", "ANSI Z87.1 Safety Glasses", 25, "PCS", "Fabrication Line 2", "WO-GEN", "John Doe", "Replacement PPE"),
        (base_date + timedelta(days=40), "TXN-OUT-009", "PRD-2003", "Hydraulic Fluid AW-68", 300, "LTR", "Hydraulics Shop", "WO-4070", "Mike Miller", "Press maintenance"),
        (base_date + timedelta(days=42), "TXN-OUT-010", "PRD-3001", "Seamless Carbon Steel Pipe 2-inch", 70, "MTR", "Piping Dept", "WO-4081", "Mike Miller", "Cooling line expansion"),
    ]
    
    for row_idx, item in enumerate(outward_records, start=2):
        row_data = list(item)
        row_data[0] = row_data[0].strftime("%Y-%m-%d")
        ws_outward.append(row_data)
        for col_idx in range(1, len(row_data) + 1):
            c = ws_outward.cell(row=row_idx, column=col_idx)
            c.font = data_font
            c.border = thin_border
            if col_idx == 5:
                c.alignment = Alignment(horizontal="right")
                
    for col in ws_outward.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws_outward.column_dimensions[col_letter].width = max(max_len + 3, 12)

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    wb.save(filepath)
    print(f"Sample workbook created successfully at: {filepath}")

if __name__ == "__main__":
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "company_inventory_master.xlsx")
    create_sample_workbook(out_path)
