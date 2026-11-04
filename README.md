# Saravanan Electricals — Stock Management System

A production-grade, Google Sheets-connected stock management website for **Saravanan Electricals and Distributors (Pvt) Ltd**.

---

## Architecture & Technology Stack

- **Frontend**: React 19 + TypeScript + Vite + Tailwind CSS + Lucide Icons + Recharts
  - Theme: Dark glassmorphism with emerald, amber, and rose stock badges
  - Official Logo: Embedded transparent branding (`frontend/public/assets/company-logo.webp`) & browser favicon
  - Value Handling: Strict exclusion of Amount column; separate Unit Price; exact preservation of literal `"NA"` and `"-"`
  - Unit Grouping: Incompatible UOMs (PCS, COIL, MTR, BOX, etc.) are strictly isolated and never summed together
- **Backend**: Python Flask REST API
  - Engine: Google Sheets API v4 + Google Auth Service Account credentials
  - Inspection: Dynamic 6-worksheet analyzer (`backend/sheet_analyzer.py`)
  - Idempotency & Polling: Background polling with SHA-256 fingerprinting and atomic snapshot replacement
  - Startup: Loads the bundled workbook immediately, then refreshes from Google Sheets in the background
  - Metadata DB: Local SQLite (`stock_metadata.db`) for audit trails and sync logs only; Google Sheets remains the single source of truth for stock data
  - Automated Tests: Full pytest suite (`backend/tests/`)

---

## How to Link Your Google Sheets

1. Open `backend/.env` (or copy from `backend/.env.example`).
2. Add your Google Spreadsheet ID (from your Google Sheet URL: `https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit`):
   ```env
   GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id_here
   GOOGLE_SERVICE_ACCOUNT_JSON=C:/path/to/service_account.json
   SYNC_INTERVAL_SECONDS=30
   FLASK_HOST=127.0.0.1
   FLASK_PORT=5000
   ```
3. Share your Google Sheet with the client email found in your `service_account.json` (grant **Viewer** access).
4. Restart the backend or click **"Sync Now"** in the top bar. The system checks for spreadsheet changes automatically (minimum 30-second interval), and the open UI page reloads its data after a successful sync.

---

## Running the Application

### 1-Click Launch (Windows)
Double-click:
```text
start_all.bat
```
This automatically launches both the Flask Backend (Port 5000) and the Vite Frontend (Port 5173).

### Manual Commands
**Backend:**
```powershell
cd backend
python app.py
```

**Frontend:**
```powershell
cd frontend
npm run dev -- --port 5173
```

Open your browser at: **`http://localhost:5173`**

---

## Dynamic Spreadsheet Intelligence & Universal Data Recognition

The application includes an AI-assisted Dynamic Spreadsheet Intelligence System that automatically profiles and recognizes unfamiliar spreadsheets without requiring predefined worksheet names or fixed column mappings.

### Capabilities:
- **Universal Spreadsheet Reader (`backend/spreadsheet_reader.py`)**:
  - Supports Excel (`.xlsx`, `.xls`) and connected Google Spreadsheets.
  - Automatic header row detection with multi-row scoring, merged-cell propagation, and literal value preservation (`NA`, `-`).
- **Intelligent Column Recognition & AI/ML Layer (`backend/intelligence_engine.py`)**:
  - Semantic role inference: `product_id`, `description`, `category`, `uom`, `unit_price`, `opening_stock`, `in_qty`, `out_qty`, `closing_stock`, `date`, `unknown`.
  - Confidence scoring, RapidFuzz / Difflib similarity matching, statistical type profiling, and suppression of row index / serial numbers.
  - LLM Provider Abstraction (`GeminiProvider`, `OpenAIProvider`, `HeuristicMLProvider`) with high-accuracy offline fallback.
  - Worksheet classification: `inventory_summary`, `stock_movement`, `price_catalog`, `reference_catalog`, `general_data`.
- **Spreadsheet Intelligence UI (`frontend/src/pages/SpreadsheetIntelligence.tsx`)**:
  - **Source Management**: Inspect analysis status, upload Excel workbooks, or trigger analysis on connected Google Sheets.
  - **Worksheet Explorer**: Discover sheet dimensions, row counts, and data tables with preserved literal values.
  - **Column Mapping Review**: Confidence pills, semantic role dropdowns, and manual role overrides.
  - **Data Quality Dashboard**: Health scores, recognized vs unknown fields, missing headers, and duplicate candidate alerts.
  - **1-Click Sync**: Merge approved mapped columns directly into the live inventory.

---

## Running Automated Tests
```powershell
cd backend
python -m pytest tests -v
```
All 12 unit tests verify Amount column exclusion, preserved `"NA"` / `"-"` literals, UOM separation, and 6-sheet schema detection.
