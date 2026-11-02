# On-Premise LAN Excel Synchronization Agent Guide

This guide describes how to configure, deploy, and maintain the on-premise synchronization agent inside your corporate network.

---

## 1. Why an On-Premise Agent?

Corporate stock records are often stored on a local Windows Server share (e.g., `\\corp-nas\warehouse\Stock_Master.xlsx`). 

Exposing Windows File Shares (SMB port 445) to the public internet creates extreme security risks (ransomware, unauthorized file access, credential theft).

The **StockGuard Sync Agent** solves this by:
1. Running locally on an approved computer or server inside the company LAN.
2. Initiating **outbound-only HTTPS connections** to the cloud server on Port 443.
3. Authenticating with a pre-shared token in the HTTP `X-Agent-Key` header.
4. Keeping the company network completely sealed from inbound connections.

---

## 2. Configuration (`sync-agent/config.json`)

```json
{
  "backend_url": "https://stock.company.com",
  "agent_api_key": "corp-sync-agent-secret-auth-token-2026-prod",
  "excel_file_path": "\\\\corp-nas\\Warehouse\\Inventory_Master.xlsx",
  "poll_interval_seconds": 60,
  "max_lock_retries": 5,
  "lock_retry_delay_seconds": 3
}
```

### Configuration Parameters:
- `backend_url`: The HTTPS URL of the cloud backend API.
- `agent_api_key`: The secret key matching `SYNC_AGENT_API_KEY` in the cloud backend `.env`.
- `excel_file_path`: Local file path (e.g., `D:\Stock\Master.xlsx`) or UNC network path (e.g., `\\nas\share\file.xlsx`).
- `poll_interval_seconds`: How often the agent checks the file for modifications (default: 60s).
- `max_lock_retries`: Number of attempts to read the file if it is currently locked by Microsoft Excel (default: 5).
- `lock_retry_delay_seconds`: Delay between retry attempts (default: 3s).

---

## 3. Supported Daily Stock Register Layout

The importer supports workbooks where each inventory material occupies one row. The
header row contains `Description`, `Part No`, `Category`, `UOM`, an initial
`OPENING STOCK`, and `UNIT PRICE`. Each dated group contains `OPENING STOCK`, `IN`,
and `OUT` columns, with the date above that group. The importer reads the headers
from row 2 and material rows from row 3 onward.

For each material, current balance is calculated from the latest dated group as:

```text
opening stock + IN - OUT
```

Non-zero dated `IN` and `OUT` quantities are recorded as stock movements. Re-syncing
the same workbook updates those daily movements rather than duplicating them. Use
**Excel Sync & Mapping → Inspect & Preview Workbook** to verify the detected sheet
layout before importing.

Unit prices are treated as Indian rupees. Materials with no valid unit price remain
unpriced and are excluded from the total stock valuation. The Reports page refreshes
automatically every 60 seconds while open.

---

## 4. Handling Temporary File Locks

When an employee opens an Excel file in Microsoft Excel, Windows places an exclusive write lock on the file, generating a `[WinError 32] The process cannot access the file because it is being used by another process`.

The sync agent handles this automatically:
1. It creates an in-memory shadow copy or temporary scratch replica.
2. If Windows signals a lock, it waits `lock_retry_delay_seconds` and retries up to `max_lock_retries` times without crashing.
3. The original workbook is never opened in write mode and is never modified.

---

## 5. Running as a Windows Scheduled Task (Recommended)

To run the agent automatically every 15 or 30 minutes without keeping a console window open:

1. Open **Task Scheduler** on the Windows Server (`taskschd.msc`).
2. Click **Create Task**:
   - **General**: Name: `StockGuard-Sync-Agent`, select **Run whether user is logged on or not**, Run with highest privileges.
   - **Triggers**: Begin the task **On a schedule**, Daily, repeat task every **15 minutes** indefinitely.
   - **Actions**: Start a program:
     - Program/script: `python.exe` (or full path to python executable, e.g. `C:\Python312\python.exe`)
     - Add arguments: `C:\StockGuard\sync-agent\agent.py --once`
     - Start in: `C:\StockGuard\sync-agent`
   - **Conditions**: Uncheck "Stop if the computer switches to battery power".
3. Click **OK** and enter service account credentials.

---

## 6. Running as a Continuous Background Windows Service (Using NSSM)

To run as a 24/7 background Windows Service:

1. Download NSSM (Non-Sucking Service Manager) from `https://nssm.cc/`.
2. In an Administrator PowerShell terminal:
   ```powershell
   nssm install StockGuardAgent "C:\Python312\python.exe" "C:\StockGuard\sync-agent\agent.py"
   nssm set StockGuardAgent AppDirectory "C:\StockGuard\sync-agent"
   nssm set StockGuardAgent Description "StockGuard Excel LAN Sync Agent"
   nssm start StockGuardAgent
   ```
3. Verify status:
   ```powershell
   Get-Service StockGuardAgent
   ```

---

## 7. Rotating the Sync Agent API Key

To rotate the agent credentials:
1. Generate a new high-entropy token:
   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. Update `SYNC_AGENT_API_KEY` in the cloud server `.env` and restart the backend.
3. Update `agent_api_key` in `config.json` on the on-premise server.
4. Verify by running `python agent.py --once`.
