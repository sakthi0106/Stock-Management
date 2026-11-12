# Stock Management System

Modern, lightweight, real-time stock management platform powered directly by Google Sheets with automatic 15-second background synchronization.

## Architecture

- **Primary Data Source**: Google Sheets API (no SQL/PostgreSQL/SQLite database required).
- **Backend**: Python Flask REST API with background thread poller.
- **Frontend**: React (Vite) + Tailwind CSS + Lucide Icons + Recharts.
- **Hosting**: Render (Backend) & Vercel (Frontend).

## Features

1. **Dashboard**: Real-time KPI summaries (Total Items, Total IN, Total OUT, Movements), velocity trends bar chart, and recent transaction log.
2. **Daily Stock Movement Registers**: Date-wise tracking of IN (Inward) and OUT (Outward) quantities extracted dynamically from Google Sheets.
3. **Inventory Catalog**: Real-time stock levels, opening balances, total receipts, total dispatches, and current balances by part number and worksheet.
4. **15-Second Auto-Sync**: Background worker synchronizing live updates from Google Sheets without page refresh.
5. **Local Excel Support**: Upload .xlsx / .xls registers for offline testing or manual loading.

## Running Locally

### Backend
```bash
cd backend
pip install -r requirements.txt
python app.py
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```
