import os
import math
import uuid
import threading
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename
from spreadsheet_reader import UniversalSpreadsheetReader
from config import Config

api_bp = Blueprint('api', __name__, url_prefix='/api')

_sync_manager = None


def init_routes(sync_manager):
    global _sync_manager
    _sync_manager = sync_manager


def _get_store(source_arg: str = None):
    if not _sync_manager:
        return None
    src = (source_arg or request.args.get('source', 'active')).strip() or 'active'
    return _sync_manager.get_store(src)


@api_bp.route('/health', methods=['GET'])
def health():
    status = _sync_manager.get_status() if _sync_manager else {}
    return jsonify({
        "status": "ok",
        "sheets_connected": status.get("is_live_google_sheet", False),
        "mode": "live" if status.get("is_live_google_sheet") else "demo",
        "sync_state": status.get("state", "disconnected")
    })


# ==============================================================
# SPREADSHEET SOURCES API (Paste Google Sheet ID / Upload Excel)
# ==============================================================

@api_bp.route('/sources', methods=['GET'])
def list_sources():
    sources = [s.to_source_dict() for s in _sync_manager.sources.values()]
    return jsonify({"sources": sources, "total": len(sources)})


@api_bp.route('/sources', methods=['POST'])
def create_source():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip() or 'Google Sheet Source'
    url_or_id = (data.get('spreadsheet_url_or_id') or '').strip()
    if not url_or_id:
        return jsonify({"error": "Google Sheets URL or Spreadsheet ID is required"}), 400

    period = (data.get('period') or '').strip()
    description = (data.get('description') or '').strip()
    is_active = bool(data.get('is_active', True))

    store = _sync_manager.register_source(
        name=name,
        spreadsheet_url_or_id=url_or_id,
        period=period,
        description=description,
        source_type="google_sheets",
        is_active=is_active
    )

    # Trigger sync in background so Render cold-boot / large sheet fetch never triggers a 502/75s browser timeout;
    # frontend polls /sources and /sync/status automatically.
    threading.Thread(target=_sync_manager.sync_source, args=(store.source_id, True), daemon=True).start()

    return jsonify({
        "source": store.to_source_dict(),
        "message": "Google Sheet registered and sync started"
    }), 201


@api_bp.route('/sources/upload', methods=['POST'])
def upload_source():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    filename = secure_filename(file.filename)
    if not (filename.endswith('.xlsx') or filename.endswith('.xls')):
        return jsonify({"error": "Only .xlsx and .xls files are supported"}), 400

    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    save_path = os.path.join(Config.UPLOAD_FOLDER, f"{int(datetime.now().timestamp())}_{filename}")
    file.save(save_path)

    name = request.form.get('name', '').strip() or filename.rsplit('.', 1)[0]
    period = request.form.get('period', '').strip()
    description = request.form.get('description', 'Uploaded Excel workbook').strip()

    try:
        reader = UniversalSpreadsheetReader()
        extracted = reader.extract_from_excel(save_path)
        raw_dict = {sname: sdata.get('values', []) for sname, sdata in extracted.get('sheets', {}).items()}

        store = _sync_manager.register_source(
            name=name,
            spreadsheet_url_or_id=f"local_file:{save_path}",
            period=period,
            description=description,
            source_type="excel_upload",
            is_active=True
        )
        store.update_from_raw_sheets(raw_dict, period=period)
        _sync_manager._record_run(store, "success", None)

        return jsonify({
            "source": store.to_source_dict(),
            "message": "File uploaded and parsed successfully",
            "sync_success": True
        }), 201
    except Exception as e:
        return jsonify({"error": f"Failed to parse Excel file: {str(e)}"}), 500


@api_bp.route('/sources/<source_id>', methods=['GET'])
def get_source(source_id: str):
    store = _sync_manager.get_store(source_id)
    if not store:
        return jsonify({"error": "Source not found"}), 404
    return jsonify({"source": store.to_source_dict()})


@api_bp.route('/sources/<source_id>', methods=['PUT'])
def update_source(source_id: str):
    store = _sync_manager.get_store(source_id)
    if not store:
        return jsonify({"error": "Source not found"}), 404
    data = request.get_json() or {}
    if 'name' in data:
        store.name = data['name']
    if 'description' in data:
        store.description = data['description']
    if 'period' in data:
        store.period = data['period']
    return jsonify({"source": store.to_source_dict()})


@api_bp.route('/sources/<source_id>', methods=['DELETE'])
def delete_source(source_id: str):
    ok = _sync_manager.delete_source(source_id)
    if not ok:
        return jsonify({"error": "Source not found"}), 404
    return jsonify({"message": "Source deleted"})


@api_bp.route('/sources/<source_id>/activate', methods=['POST'])
def activate_source(source_id: str):
    ok = _sync_manager.activate_source(source_id)
    if not ok:
        return jsonify({"error": "Source not found"}), 404
    return jsonify({"message": "Source activated", "source_id": source_id})


@api_bp.route('/sources/<source_id>/archive', methods=['POST'])
def archive_source(source_id: str):
    store = _sync_manager.get_store(source_id)
    if not store:
        return jsonify({"error": "Source not found"}), 404
    store.status = 'archived'
    store.is_active = 0
    return jsonify({"message": "Source archived"})


@api_bp.route('/sources/<source_id>/sync', methods=['POST'])
def sync_single_source(source_id: str):
    threading.Thread(target=_sync_manager.sync_source, args=(source_id, True), daemon=True).start()
    return jsonify({"success": True, "status": _sync_manager.get_status(), "message": "Sync started"})


@api_bp.route('/sources/<source_id>/sheets', methods=['GET'])
def get_source_sheets(source_id: str):
    store = _sync_manager.get_store(source_id)
    if not store:
        return jsonify({"source_id": source_id, "sheets": [], "total": 0})
    return jsonify({"source_id": store.source_id, "sheets": store.worksheets, "total": len(store.worksheets)})


@api_bp.route('/sources/<source_id>/sheets/<sheet_name>', methods=['DELETE'])
def delete_source_sheet(source_id: str, sheet_name: str):
    store = _sync_manager.get_store(source_id)
    if not store:
        return jsonify({"error": "Source not found"}), 404
    store.remove_worksheet(sheet_name)
    return jsonify({"message": f"Worksheet '{sheet_name}' removed"})


# ==============================================================
# DASHBOARD, INVENTORY, MOVEMENTS, QUALITY
# ==============================================================

@api_bp.route('/dashboard', methods=['GET'])
def get_dashboard():
    store = _get_store()
    if not store:
        return jsonify({
            "total_products": 0,
            "in_stock_count": 0,
            "low_stock_count": 0,
            "out_of_stock_count": 0,
            "unknown_stock_count": 0,
            "total_movements_count": 0,
            "total_in_transactions": 0,
            "total_out_transactions": 0,
            "uom_quantities": {},
            "inward_by_uom": {},
            "outward_by_uom": {},
            "daily_trends": [],
            "category_distribution": [],
            "status_distribution": [],
            "recent_movements": [],
            "last_updated": None,
            "sync_status": _sync_manager.get_status() if _sync_manager else {}
        })

    summary = store.get_dashboard_summary()
    summary["sync_status"] = _sync_manager.get_status()
    return jsonify(summary)


@api_bp.route('/inventory', methods=['GET'])
def get_inventory():
    store = _get_store()
    if not store:
        return jsonify({
            "items": [], "total": 0, "page": 1, "page_size": 50,
            "total_pages": 0, "categories": [], "sheets": [], "uoms": []
        })

    search = request.args.get('search', '').strip().lower()
    sheet = request.args.get('sheet', '').strip()
    category = request.args.get('category', '').strip()
    part_no = request.args.get('part_no', '').strip().lower()
    uom = request.args.get('uom', '').strip().upper()
    status = request.args.get('status', '').strip()
    page = max(1, int(request.args.get('page', 1)))
    page_size = max(1, min(500, int(request.args.get('page_size', 50))))
    sort_by = request.args.get('sort_by', 'part_no')
    sort_order = request.args.get('sort_order', 'asc')

    all_products = store.products
    categories = sorted(list(set(p.get("category", "General") for p in all_products)))
    sheets = sorted(list(set(p.get("source_sheet", "") for p in all_products if p.get("source_sheet"))))
    uoms = sorted(list(set(p.get("uom", "NOS") for p in all_products)))

    filtered = all_products
    if search:
        filtered = [
            p for p in filtered
            if search in str(p.get("part_no", "")).lower()
            or search in str(p.get("description", "")).lower()
            or search in str(p.get("category", "")).lower()
            or any(search in str(v).lower() for v in (p.get("extra_fields") or {}).values())
        ]
    if sheet:
        filtered = [p for p in filtered if p.get("source_sheet") == sheet]
    if category:
        filtered = [p for p in filtered if p.get("category") == category]
    if part_no:
        filtered = [p for p in filtered if part_no in str(p.get("part_no", "")).lower()]
    if uom:
        filtered = [p for p in filtered if p.get("uom") == uom]
    if status:
        filtered = [p for p in filtered if p.get("stock_status") == status]

    reverse = (sort_order == 'desc')
    filtered = sorted(filtered, key=lambda x: str(x.get(sort_by) or ''), reverse=reverse)

    total = len(filtered)
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    start = (page - 1) * page_size
    paginated = filtered[start:start + page_size]

    return jsonify({
        "items": paginated,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "categories": categories,
        "sheets": sheets,
        "uoms": uoms
    })


@api_bp.route('/inventory/<product_id>', methods=['GET'])
def get_product(product_id: str):
    store = _get_store()
    if not store:
        return jsonify({"error": "No data available"}), 404
    prod = next((p for p in store.products if p.get("product_id") == product_id), None)
    if not prod:
        return jsonify({"error": "Product not found"}), 404
    movs = [m for m in store.movements if m.get("product_id") == product_id]
    return jsonify({"product": prod, "movements": movs})


@api_bp.route('/movements', methods=['GET'])
def get_movements():
    store = _get_store()
    if not store:
        return jsonify({"items": [], "total": 0})

    product_id = request.args.get('product_id', '').strip()
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()
    m_type = request.args.get('movement_type', '').strip().upper()

    items = store.movements
    if product_id:
        items = [m for m in items if product_id.lower() in str(m.get("product_id", "")).lower() or product_id.lower() in str(m.get("part_no", "")).lower()]
    if from_date:
        items = [m for m in items if m.get("date", "") >= from_date]
    if to_date:
        items = [m for m in items if m.get("date", "") <= to_date]
    if m_type in ('IN', 'OUT'):
        items = [m for m in items if m.get("movement_type") == m_type]

    return jsonify({"items": items, "total": len(items)})


@api_bp.route('/data-quality', methods=['GET'])
def get_data_quality():
    store = _get_store()
    if not store:
        return jsonify({"total_issues": 0, "issues": [], "duplicate_ids": [], "sheets_analyzed": 0})

    issues = []
    if store.last_sync_error:
        issues.append({"type": "SYNC_ERROR", "severity": "CRITICAL", "message": store.last_sync_error})

    return jsonify({
        "total_issues": len(issues),
        "issues": issues,
        "duplicate_ids": [],
        "sheets_analyzed": len(store.worksheets)
    })


# ==============================================================
# SYNC CONTROLS
# ==============================================================

@api_bp.route('/sync/status', methods=['GET'])
def sync_status():
    return jsonify(_sync_manager.get_status())


@api_bp.route('/sync/refresh', methods=['POST'])
def sync_refresh():
    source = request.args.get('source', 'active').strip()
    threading.Thread(target=_sync_manager.sync_source, args=(source, True), daemon=True).start()
    return jsonify({"success": True, "status": _sync_manager.get_status(), "message": "Sync started"})


@api_bp.route('/sync/pause', methods=['POST'])
def sync_pause():
    _sync_manager.pause_sync()
    return jsonify({"success": True, "message": "Automatic 15-second sync paused", "status": _sync_manager.get_status()})


@api_bp.route('/sync/resume', methods=['POST'])
def sync_resume():
    _sync_manager.resume_sync()
    return jsonify({"success": True, "message": "Automatic 15-second sync resumed", "status": _sync_manager.get_status()})


@api_bp.route('/sync/history', methods=['GET'])
def sync_history():
    limit = int(request.args.get('limit', 15))
    runs = _sync_manager.sync_history[:limit]
    return jsonify({"runs": runs, "total": len(runs)})


# ==============================================================
# SPREADSHEET INTELLIGENCE (Dynamic Rows & Columns Viewer)
# ==============================================================

@api_bp.route('/spreadsheet-intelligence/sources', methods=['GET'])
def intelligence_sources():
    sources = [s.to_source_dict() for s in _sync_manager.sources.values()]
    return jsonify({"sources": sources, "total": len(sources)})


@api_bp.route('/spreadsheet-intelligence/analyze', methods=['POST'])
def intelligence_analyze():
    data = request.get_json() or {}
    source_id = data.get('source_id') or 'active'
    store = _sync_manager.get_store(source_id)
    if not store:
        return jsonify({"error": "Source not found"}), 404
    _sync_manager.sync_source(store.source_id, force=True)
    return jsonify({
        "success": True,
        "message": "Spreadsheet analyzed dynamically",
        "source_id": store.source_id
    })


@api_bp.route('/spreadsheet-intelligence/status/<task_id>', methods=['GET'])
def intelligence_task_status(task_id: str):
    return jsonify({"status": "completed", "progress": "Analysis complete"})


@api_bp.route('/spreadsheet-intelligence/upload', methods=['POST'])
def intelligence_upload():
    return upload_source()


@api_bp.route('/spreadsheet-intelligence/sources/<source_id>/worksheets', methods=['GET'])
def intelligence_worksheets(source_id: str):
    store = _sync_manager.get_store(source_id)
    if not store:
        return jsonify({"source_id": source_id, "worksheets": [], "total": 0})
    return jsonify({"source_id": store.source_id, "worksheets": store.worksheets, "total": len(store.worksheets)})


@api_bp.route('/spreadsheet-intelligence/sources/<source_id>/worksheets/<sheet_name>', methods=['GET'])
def intelligence_worksheet_details(source_id: str, sheet_name: str):
    store = _sync_manager.get_store(source_id)
    if not store:
        return jsonify({"error": "Source not found"}), 404
    ws = next((w for w in store.worksheets if w["sheet_name"] == sheet_name), None)
    if not ws:
        return jsonify({"error": "Worksheet not found"}), 404
    cols = store.dynamic_columns.get(sheet_name, [])
    return jsonify({"worksheet": ws, "columns": cols})


@api_bp.route('/spreadsheet-intelligence/sources/<source_id>/worksheets/<sheet_name>/columns', methods=['GET'])
def intelligence_columns(source_id: str, sheet_name: str):
    store = _sync_manager.get_store(source_id)
    if not store:
        return jsonify({"error": "Source not found"}), 404
    cols = store.dynamic_columns.get(sheet_name, [])
    return jsonify({"source_id": store.source_id, "sheet_name": sheet_name, "columns": cols, "total": len(cols)})


@api_bp.route('/spreadsheet-intelligence/sources/<source_id>/worksheets/<sheet_name>/columns', methods=['PUT'])
def intelligence_update_columns(source_id: str, sheet_name: str):
    store = _sync_manager.get_store(source_id)
    if not store:
        return jsonify({"error": "Source not found"}), 404
    data = request.get_json() or {}
    updated_cols = data.get("columns", [])
    existing = store.dynamic_columns.get(sheet_name, [])
    by_idx = {c["column_index"]: c for c in existing}
    for uc in updated_cols:
        idx = uc.get("column_index")
        if idx in by_idx and "inferred_role" in uc:
            by_idx[idx]["inferred_role"] = uc["inferred_role"]
            by_idx[idx]["mapping_status"] = "approved"
    return jsonify({"success": True, "message": "Column mappings updated", "columns": existing})


@api_bp.route('/spreadsheet-intelligence/sources/<source_id>/worksheets/<sheet_name>/records', methods=['GET'])
def intelligence_records(source_id: str, sheet_name: str):
    store = _sync_manager.get_store(source_id)
    if not store:
        return jsonify({"records": [], "total": 0, "page": 1, "limit": 50, "total_pages": 1})

    page = max(1, int(request.args.get('page', 1)))
    limit = max(1, min(500, int(request.args.get('limit', 50))))
    search = request.args.get('search', '').strip().lower()

    recs = store.dynamic_records.get(sheet_name, [])
    if search:
        recs = [
            r for r in recs
            if any(search in str(v).lower() for v in (r.get("raw_data") or {}).values())
        ]

    total = len(recs)
    total_pages = math.ceil(total / limit) if total > 0 else 1
    start = (page - 1) * limit
    paginated = recs[start:start + limit]

    return jsonify({
        "records": paginated,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages
    })


@api_bp.route('/spreadsheet-intelligence/sources/<source_id>/data-quality', methods=['GET'])
def intelligence_data_quality(source_id: str):
    store = _sync_manager.get_store(source_id)
    if not store:
        return jsonify({
            "source_id": source_id, "total_worksheets": 0, "total_rows": 0,
            "total_columns": 0, "recognized_fields": 0, "unknown_fields": 0,
            "requires_review_count": 0, "overall_quality_score": 0,
            "duplicate_candidates": [], "quality_issues": []
        })

    all_cols = [c for cols in store.dynamic_columns.values() for c in cols]
    recognized = sum(1 for c in all_cols if c["inferred_role"] != "unknown")
    unknown = sum(1 for c in all_cols if c["inferred_role"] == "unknown")
    total_rows = sum(w["row_count"] for w in store.worksheets)

    return jsonify({
        "source_id": store.source_id,
        "total_worksheets": len(store.worksheets),
        "total_rows": total_rows,
        "total_columns": len(all_cols),
        "recognized_fields": recognized,
        "unknown_fields": unknown,
        "requires_review_count": unknown,
        "overall_quality_score": 95.0 if total_rows > 0 else 0.0,
        "duplicate_candidates": [],
        "quality_issues": []
    })


@api_bp.route('/spreadsheet-intelligence/sources/<source_id>/sync', methods=['POST'])
def intelligence_sync_approved(source_id: str):
    store = _sync_manager.get_store(source_id)
    if not store:
        return jsonify({"error": "Source not found"}), 404
    _sync_manager.sync_source(store.source_id, force=True)
    return jsonify({
        "success": True,
        "message": "Dynamic data synchronized",
        "imported_products": len(store.products),
        "worksheets_count": len(store.worksheets)
    })
