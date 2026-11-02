# Troubleshooting & Operations Guide

This guide covers common issues with Excel synchronization, network shares, file locks, and schema mismatches.

---

## 1. File Locks (`WinError 32: The process cannot access the file because it is being used by another process`)

### Cause
An employee in the office has the primary Excel workbook open in Microsoft Excel while the synchronization agent attempts to read it.

### Solution
1. The **Sync Agent** already includes built-in shadow copy retries (`max_lock_retries: 5`, `lock_retry_delay_seconds: 3`).
2. If the file remains locked continuously, check if a user left the file open overnight:
   - On the Windows File Server hosting the share, open **Computer Management** (`compmgmt.msc`).
   - Navigate to **Shared Folders** > **Open Files**.
   - Locate the workbook file and observe which user has the active write lock.
3. Recommend company staff to use **Excel Co-Authoring** (via SharePoint/OneDrive) or set Excel to "Shared Workbook" mode if concurrent editing is required.

---

## 2. Unchanged Files Being Synchronized Repeatedly

### Cause
Sync scheduled jobs running on a timer re-reading unchanged files.

### Solution
- The system computes a **SHA-256 content hash** of the workbook file before processing.
- If the current file hash matches the last successful synchronization hash stored in the database, the backend skips re-importing and logs `UNCHANGED`.
- Check the backend sync logs:
  ```json
  {"status": "UNCHANGED", "message": "Workbook content hash matches last successful sync. Skipped re-import."}
  ```

---

## 3. Duplicate Records Prevention (Deduplication Strategy)

### Problem
Repeated imports of the same workbook or appending records without reliable transaction IDs.

### Implementation
- Each transaction record is assigned a composite deterministic idempotency hash:
  $$\text{Hash} = \text{SHA256}(\text{SheetName} \parallel \text{RowIndex} \parallel \text{Date} \parallel \text{ProductCode} \parallel \text{Qty} \parallel \text{Reference})$$
- The `dedup_hash` column has a unique database constraint.
- During sync, if a transaction hash already exists in `stock_transactions`, it is recorded as `rows_skipped` and no duplicate row is created.

---

## 4. Invalid Rows and Schema Mismatches

### Problem
Employees add new columns, rename headers, or leave product codes blank.

### Solution
1. In the **Admin Dashboard**, navigate to **Excel Sync & Mapping**.
2. Upload the workbook into the **Inspect & Preview** tool.
3. Review the detected headers and sheet names.
4. Check the validation error log:
   - Rows with missing or empty Product Code are logged to `all_errors` and skipped without aborting the rest of the import.
   - Rows with invalid numbers (e.g. text written in a quantity column) default safely to `0.0` and log a validation warning.

---

## 5. Network Dropouts Between LAN Agent and Cloud Backend

### Problem
The company internet connection temporarily drops out or the cloud server is restarting during a scheduled sync.

### Solution
- The sync agent uses HTTP timeouts and catches `requests.exceptions.RequestException`.
- Failed push attempts log a warning and retain the last known hash.
- On the next scheduled run or interval, the agent re-attempts the push.
- The cloud dashboard automatically displays a **Data Freshness Warning** banner if no successful sync has completed in over 24 hours.
