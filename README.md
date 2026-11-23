# Stock Management System

Modern, enterprise-grade, real-time stock management platform powered directly by Google Sheets with automatic background synchronization.

## Architecture

- **Primary Data Source**: Google Sheets API & Universal Excel Parser (no SQL/PostgreSQL database required).
- **Backend**: Python Flask REST API running in a containerized Gunicorn WSGI server.
- **Backend Deployment**: **Google Cloud Run** (Scalable, containerized serverless container).
- **Frontend**: React (Vite) + TypeScript + Tailwind CSS + Lucide Icons + Recharts.
- **Frontend Deployment**: **Vercel**.

## Features

1. **Dashboard**: Real-time KPI summaries (Total Items, Total IN, Total OUT, Movements), velocity trends bar chart, and recent transaction log.
2. **Daily Stock Movement Registers**: Date-wise tracking of IN (Inward) and OUT (Outward) quantities extracted dynamically from Google Sheets.
3. **Inventory Catalog**: Real-time stock levels, opening balances, total receipts, total dispatches, and current balances by part number and worksheet.
4. **Multi-Source Support**: Connect multiple Google Spreadsheets simultaneously or upload modern Excel workbooks (.xlsx).
5. **Background Auto-Sync**: Background worker synchronizing live updates from Google Sheets without page refresh.
6. **Isolated Deletions & Deduplication**: Individual sources can be added, updated, or deleted without affecting other connected spreadsheets.

---

## Deploying Backend to Google Cloud Run

Google Cloud Run provides a scalable, fast, and robust environment for the Python backend with no cold-kill timeouts and direct access to Google Cloud infrastructure.

### Option 1: One-Line Deploy with gcloud CLI
From the root of this project:

```bash
# Set your GCP Project ID
gcloud config set project YOUR_GCP_PROJECT_ID

# Deploy directly from source
gcloud run deploy stock-management-backend \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 120s \
  --set-env-vars FLASK_ENV=production
```

Or execute the provided deployment helper:
- **Linux/macOS**: `./deploy-cloudrun.sh`
- **Windows**: `.\deploy-cloudrun.ps1`

### Option 2: Continuous Deployment from GitHub via Cloud Run Console
1. Open the [Google Cloud Run Console](https://console.cloud.google.com/run).
2. Click **Create Service**.
3. Select **Continuously deploy from a repository**.
4. Authorize and choose your GitHub repository (`Stock-Management`).
5. Select branch `main` and Build Type **Dockerfile**.
6. Under **Authentication**, select **Allow unauthenticated invocations**.
7. Under **Container, Volumes, Networking**:
   - Container Port: `8080`
   - Memory: `1 GiB` or `2 GiB`
   - CPU: `1`
8. Under **Environment Variables**, add:
   - `FLASK_ENV`: `production`
   - `GOOGLE_SERVICE_ACCOUNT_JSON`: `<Your service account JSON content or secret>`
   - `GOOGLE_SHEETS_SPREADSHEET_ID`: `<Your Google Spreadsheet ID>`
9. Click **Create**. Cloud Run will automatically build and deploy every commit pushed to `main`.

---

## Connecting the Vercel Frontend to Cloud Run

After Google Cloud Run is deployed, you will receive a public HTTPS URL (e.g. `https://stock-management-backend-xyz-uc.a.run.app`).

1. Go to your [Vercel Dashboard](https://vercel.com).
2. Select your `stock-management` project -> **Settings** -> **Environment Variables**.
3. Set or update:
   - Key: `VITE_API_BASE_URL`
   - Value: `https://stock-management-backend-xyz-uc.a.run.app/api`
4. Redeploy your frontend in Vercel to apply the new backend URL.

---

## Running Locally

### Backend
```bash
cd backend
pip install -r requirements.txt
python app.py
```
Or with Gunicorn:
```bash
gunicorn --config gunicorn.conf.py app:app
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```
