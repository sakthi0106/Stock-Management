# Windows Development Setup Guide

This guide walks you through setting up and running the **StockGuard Enterprise** application locally on a Windows machine.

---

## 1. Prerequisites

Ensure you have the following installed on your Windows machine:
- **Python**: Version 3.10+ (Python 3.11, 3.12, 3.13, 3.14 supported).
- **Node.js**: Version 18+ (Node 20 or 24 LTS recommended) and npm.
- **Git for Windows**.
- **Microsoft Excel** (or compatible viewer) for inspecting `.xlsx` workbooks.
- **PostgreSQL 15+** (Optional for local dev, as SQLite zero-configuration fallback is built-in).

---

## 2. Directory Structure

```text
stock-management/
├── backend/          # FastAPI API service
├── frontend/         # React + TypeScript + Vite + Tailwind UI
├── sync-agent/       # On-Premise LAN Sync Agent
├── sample-data/      # Sample Excel inventory files
└── docs/             # Technical and operational guides
```

---

## 3. Backend Setup

1. Open PowerShell and navigate to the backend folder:
   ```powershell
   cd C:\Users\amdha\.gemini\antigravity\scratch\stock-management\backend
   ```

2. (Optional) Create and activate a Python virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

4. Run database initialization and startup tests:
   ```powershell
   python -m unittest tests/test_api.py
   ```

5. Launch the backend server:
   ```powershell
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

   The backend will start at `http://127.0.0.1:8000`.
   - Interactive API Swagger Docs: `http://127.0.0.1:8000/docs`
   - Health check: `http://127.0.0.1:8000/health`

---

## 4. Frontend Setup

1. Open a new PowerShell terminal and navigate to the frontend folder:
   ```powershell
   cd C:\Users\amdha\.gemini\antigravity\scratch\stock-management\frontend
   ```

2. Install dependencies (if setting up fresh):
   ```powershell
   npm install
   ```

3. Start the Vite development server:
   ```powershell
   npm run dev
   ```

   Or build for production and preview:
   ```powershell
   npm run build
   npm run preview -- --port 5173
   ```

4. Open `http://localhost:5173` in your browser.

---

## 5. Seed Accounts for Testing

The system automatically initializes default persona accounts on first launch:

| Role | Email | Default Password | Permissions |
| :--- | :--- | :--- | :--- |
| **Director** | `director@company.internal` | `DirectorPass2026!` | Full dashboard, stock register, reports & CSV/Excel exports. |
| **Purchase Team** | `purchase@company.internal` | `PurchasePass2026!` | Stock balances, search/filter, movement history, reorder reports. |
| **Administrator** | `admin@company.internal` | `AdminPass2026!` | User management, manual workbook uploads, sync audit log. |

> [!TIP]
> The top navigation bar includes an instant persona switcher button to test Director, Purchase, and Admin views without having to log out.
