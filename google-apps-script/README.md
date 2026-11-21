# Google Apps Script Direct Backend Connector

This directory contains the standalone Google Apps Script backend for the Stock Management System.

## Why use Google Apps Script instead of Render?
- **100% Free Forever**: Runs entirely inside Google's enterprise infrastructure.
- **Zero Cold-Boot Delay**: No 60–90 second Render free-tier sleep cycles.
- **Zero RAM Limit Crashes**: Eliminates 512MB RAM ceiling errors.
- **Real-Time Data**: Directly reads and updates your Google Sheets without complex service account credentials.

---

## 3-Step Setup Guide

### 1. Open Apps Script in Google Sheets
1. Open your Google Spreadsheet in your web browser.
2. In the top navigation bar, click **Extensions** > **Apps Script**.

### 2. Paste the Script
1. Delete any existing template code in `Code.gs`.
2. Copy and paste the entire contents of [`Code.gs`](./Code.gs) into the editor.
3. Click the **Save** floppy disk icon (or press `Ctrl+S` / `Cmd+S`).

### 3. Deploy as a Web App
1. At the top right of the Apps Script window, click the blue **Deploy** button > **New deployment**.
2. Click the gear icon next to *Select type* and select **Web app**.
3. Set the fields:
   - **Description**: `Stock Management API`
   - **Execute as**: `Me (your-email@gmail.com)`
   - **Who has access**: `Anyone` *(Crucial: allows your Vercel frontend to read data without OAuth)*
4. Click **Deploy**.
5. When prompted with Google permissions:
   - Click **Authorize access**.
   - Choose your Google Account.
   - Click **Advanced** > **Go to Stock Management API (unsafe)** > **Allow**.
6. Copy the generated **Web app URL** (starts with `https://script.google.com/macros/s/.../exec`).

---

## Connecting to Your Frontend

### Option A: Direct In-App Setup (No Rebuild Required!)
1. Open your Stock Management web app.
2. Navigate to **Spreadsheet Sources** or click the **⚡ Google Apps Script Mode** banner.
3. Paste your Web App URL into the input field and click **Connect**.
4. The dashboard and inventory will immediately refresh directly from your Google Sheet!

### Option B: Configure in Vercel Environment Variables
In your Vercel project dashboard:
1. Go to **Settings** > **Environment Variables**.
2. Add a new variable:
   - **Key**: `VITE_APPS_SCRIPT_URL`
   - **Value**: `https://script.google.com/macros/s/.../exec`
3. Click **Save** and redeploy!
