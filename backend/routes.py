import math
import os
import json
import uuid
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename
from sync_service import SyncService
from spreadsheet_reader import UniversalSpreadsheetReader
from intelligence_engine import IntelligenceEngine
import database

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')

sync_service: SyncService = None
intelligence_engine = IntelligenceEngine()

# In-memory tracking for background analysis tasks
analysis_tasks: dict = {}

FORBIDDEN_KEYWORDS = ['amount', 'total cost', 'total price', 'closing value', 'total value', 'closing stk val']


def init_routes(service: SyncService):
    global sync_service
    sync_service = service


def is_amount_field(field_name: str) -> bool:
    fn = field_name.lower()
    return any(k in fn for k in FORBIDDEN_KEYWORDS)


def _get_service_for_request(req):
    source = req.args.get('source', 'active').strip()
    srv = sync_service.get_service(source_filter=source)
    return srv, source


@api_bp.route('/health', methods=['GET'])
def health():
    status = sync_service.get_status()
    return jsonify({
        "status": "ok",
        "sheets_connected": status.get("is_live_google_sheet", False),
        "mode": "live" if status.get("is_live_google_sheet") else "demo",
        "sync_state": status.get("state", "idle")
    })


@api_bp.route('/sheets', methods=['GET'])
def get_sheets():
    source = request.args.get('source', 'active').strip()
    active_src = database.get_active_source()
    sid = active_src['source_id'] if source == 'active' and active_src else (source if source != 'active' else None)
    if not sid:
        return jsonify({"source_id": "", "sheets": [], "total": 0})
    sheets = database.get_sheets_for_source(sid)
    return jsonify({"source_id": sid, "sheets": sheets, "total": len(sheets)})


@api_bp.route('/sources', methods=['GET'])
def list_sources():
    include_disabled = request.args.get('include_disabled', 'false').lower() == 'true'
    sources = database.list_sources(include_disabled=include_disabled)
    return jsonify({"sources": sources, "total": len(sources)})


@api_bp.route('/sources', methods=['POST'])
def create_source():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    url_or_id = data.get('spreadsheet_url_or_id', '').strip()
    if not name or not url_or_id:
        return jsonify({"error": "name and spreadsheet_url_or_id are required"}), 400

    period = data.get('period', '').strip()
    description = data.get('description', '').strip()
    status = data.get('status', 'active')
    is_active = bool(data.get('is_active', False))
    poll_interval = int(data.get('poll_interval_seconds', 30))

    new_src = database.create_source(
        name=name,
        spreadsheet_url_or_id=url_or_id,
        period=period,
        description=description,
        status=status,
        is_active=is_active,
        poll_interval=poll_interval
    )
    sync_service.register_source(new_src)

    # Perform initial sync
    sync_service.sync_source(new_src['source_id'], force=True)

    return jsonify({"source": new_src, "message": "Source created and initial sync triggered"}), 201


@api_bp.route('/sources/upload', methods=['POST'])
def upload_source():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    filename = secure_filename(file.filename)
    upload_dir = Path(__file__).resolve().parent / 'uploads'
    upload_dir.mkdir(exist_ok=True)
    save_path = upload_dir / filename
    file.save(str(save_path))

    name = request.form.get('name', filename)
    period = request.form.get('period', '')
    description = request.form.get('description', 'Uploaded local Excel workbook')

    new_src = database.create_source(
        name=name,
        spreadsheet_url_or_id=f"local_file:{save_path}",
        period=period,
        description=description,
        status='active',
        is_active=True
    )
    conn = database.get_db_connection()
    conn.execute("UPDATE spreadsheet_sources SET source_type = 'excel_upload' WHERE source_id = ?", (new_src['source_id'],))
    conn.commit()
    conn.close()
    new_src['source_type'] = 'excel_upload'
    sync_service.register_source(new_src)
    ok, sync_res = sync_service.sync_source(new_src['source_id'], force=True)

    return jsonify({
        "source": new_src,
        "message": "File uploaded and parsed successfully",
        "sync_success": ok
    }), 201


@api_bp.route('/sources/<source_id>', methods=['GET'])
def get_source(source_id: str):
    src = database.get_source(source_id)
    if not src:
        return jsonify({"error": "Source not found"}), 404
    return jsonify({"source": src})


@api_bp.route('/sources/<source_id>', methods=['PUT'])
def update_source(source_id: str):
    updates = request.get_json() or {}
    updated = database.update_source(source_id, updates)
    if not updated:
        return jsonify({"error": "Source not found"}), 404
    sync_service.reload_sources()
    return jsonify({"source": updated})


@api_bp.route('/sources/<source_id>', methods=['DELETE'])
def delete_source(source_id: str):
    database.delete_source(source_id)
    sync_service.unregister_source(source_id)
    return jsonify({"message": f"Source {source_id} deleted successfully"})


@api_bp.route('/sources/<source_id>/activate', methods=['POST'])
def activate_source(source_id: str):
    ok = database.set_active_source(source_id)
    if not ok:
        return jsonify({"error": "Source not found"}), 404
    sync_service.reload_sources()
    return jsonify({"message": "Source activated", "source_id": source_id})


@api_bp.route('/sources/<source_id>/archive', methods=['POST'])
def archive_source(source_id: str):
    ok = database.archive_source(source_id)
    if not ok:
        return jsonify({"error": "Source not found"}), 404
    sync_service.reload_sources()
    return jsonify({"message": "Source archived"})


@api_bp.route('/sources/<source_id>/sync', methods=['POST'])
def sync_source(source_id: str):
    src = database.get_source(source_id)
    if not src:
        return jsonify({"error": "Source not found"}), 404
    data = request.get_json() or {}
    force = bool(data.get('force', True))
    ok, res = sync_service.sync_source(source_id, force=force)
    status = sync_service.get_source_status(source_id)
    return jsonify({"success": ok, "status": status})


@api_bp.route('/sources/<source_id>/sheets', methods=['GET'])
def get_source_sheets(source_id: str):
    src = database.get_source(source_id)
    if not src:
        return jsonify({"error": "Source not found"}), 404
    sheets = database.get_sheets_for_source(source_id)
    return jsonify({"source_id": source_id, "sheets": sheets, "total": len(sheets)})


@api_bp.route('/sources/<source_id>/sheets/<sheet_name>', methods=['DELETE'])
def delete_source_sheet(source_id: str, sheet_name: str):
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM spreadsheet_sheets WHERE source_id = ? AND sheet_name = ?", (source_id, sheet_name))
    cur.execute("DELETE FROM sheet_column_mappings WHERE source_id = ? AND sheet_name = ?", (source_id, sheet_name))
    cur.execute("DELETE FROM inventory_records WHERE source_id = ? AND source_sheet = ?", (source_id, sheet_name))
    cur.execute("DELETE FROM stock_movements WHERE source_id = ? AND source_sheet = ?", (source_id, sheet_name))
    conn.commit()
    conn.close()
    return jsonify({"message": f"Sheet '{sheet_name}' removed from source {source_id}"})


@api_bp.route('/inventory', methods=['GET'])
def get_inventory():
    srv, source = _get_service_for_request(request)
    if not srv:
        return jsonify({"error": "No inventory data available"}), 503

    search = request.args.get('search', '').strip()
    sheet = request.args.get('sheet', '').strip()
    category = request.args.get('category', '').strip()
    part_no = request.args.get('part_no', '').strip()
    uom = request.args.get('uom', '').strip()
    status = request.args.get('status', '').strip()
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 50))
    sort_by = request.args.get('sort_by', 'product_id').strip()
    sort_order = request.args.get('sort_order', 'asc').strip().lower()

    items = srv.get_products(
        search=search,
        sheet=sheet,
        category=category,
        part_no=part_no,
        uom=uom,
        status=status
    )

    # Sort
    def sort_key(p):
        v = p.get(sort_by)
        if v is None or v in ('NA', '-'):
            return ''
        if isinstance(v, str):
            return v.lower()
        return v

    items.sort(key=sort_key, reverse=(sort_order == 'desc'))

    total = len(items)
    total_pages = max(1, math.ceil(total / page_size))
    start_idx = (page - 1) * page_size
    page_items = items[start_idx:start_idx + page_size]

    # Sanitize out any amount columns
    sanitized_items = []
    for item in page_items:
        clean = dict(item)
        if "extra_fields" in clean:
            clean["extra_fields"] = {k: v for k, v in clean["extra_fields"].items() if not is_amount_field(k)}
        sanitized_items.append(clean)

    # Extract distinct categories, sheets, uoms
    all_prods = srv.products
    categories = sorted(list({p.get('category') for p in all_prods if p.get('category')}))
    sheets = sorted(list({p.get('source_sheet') for p in all_prods if p.get('source_sheet')}))
    uoms = sorted(list({p.get('uom') for p in all_prods if p.get('uom')}))

    return jsonify({
        "items": sanitized_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "categories": categories,
        "sheets": sheets,
        "uoms": uoms,
        "source_filter": source
    })


@api_bp.route('/inventory/<product_id>', methods=['GET'])
def get_product(product_id: str):
    srv, source = _get_service_for_request(request)
    if not srv:
        return jsonify({"error": "No inventory data available"}), 503

    prod = srv.get_product_by_id(product_id)
    if not prod:
        return jsonify({"error": "Product not found"}), 404

    clean = dict(prod)
    if "extra_fields" in clean:
        clean["extra_fields"] = {k: v for k, v in clean["extra_fields"].items() if not is_amount_field(k)}

    movements = srv.get_movements(product_id=product_id)
    return jsonify({
        "product": clean,
        "movements": movements
    })


@api_bp.route('/movements', methods=['GET'])
def get_movements():
    srv, source = _get_service_for_request(request)
    if not srv:
        return jsonify({"error": "No inventory data available"}), 503

    product_id = request.args.get('product_id', '').strip() or None
    from_date = request.args.get('from_date', '').strip() or None
    to_date = request.args.get('to_date', '').strip() or None
    movement_type = request.args.get('movement_type', '').strip() or None

    items = srv.get_movements(
        product_id=product_id,
        from_date=from_date,
        to_date=to_date,
        movement_type=movement_type
    )

    return jsonify({
        "items": items,
        "movements": items,
        "total": len(items),
        "source_filter": source
    })


@api_bp.route('/dashboard', methods=['GET'])
def get_dashboard():
    srv, source = _get_service_for_request(request)
    if not srv:
        return jsonify({"error": "No data available"}), 503

    summary = srv.get_dashboard_summary()
    sync_status = sync_service.get_status()

    summary['sync_status'] = sync_status
    summary['source_filter'] = source

    return jsonify(summary)


@api_bp.route('/movement-reports', methods=['GET'])
def get_movement_reports():
    srv, source = _get_service_for_request(request)
    if not srv:
        return jsonify({"error": "No movement data available"}), 503

    product_id = request.args.get('product_id', '').strip() or None
    from_date = request.args.get('from_date', '').strip() or None
    to_date = request.args.get('to_date', '').strip() or None

    items = srv.get_movements(
        product_id=product_id,
        from_date=from_date,
        to_date=to_date
    )

    return jsonify({
        "items": items,
        "total": len(items)
    })


@api_bp.route('/sync/status', methods=['GET'])
def get_sync_status():
    return jsonify(sync_service.get_status())


@api_bp.route('/sync/refresh', methods=['POST'])
def trigger_refresh():
    source = request.args.get('source', 'active').strip()
    ok, res = sync_service.perform_sync(source_id=source, force=True)
    status = sync_service.get_status()
    return jsonify({"success": ok, "status": status})


@api_bp.route('/sync/history', methods=['GET'])
def get_sync_history():
    source = request.args.get('source', None)
    limit = int(request.args.get('limit', 15))
    runs = database.get_recent_sync_runs(source_id=source, limit=limit)
    return jsonify({"runs": runs, "total": len(runs)})


@api_bp.route('/data-quality', methods=['GET'])
def get_data_quality():
    srv, source = _get_service_for_request(request)
    if not srv:
        return jsonify({"error": "No data available"}), 503
    report = srv.get_data_quality_report()
    return jsonify(report)


# ==============================================================
# SPREADSHEET INTELLIGENCE & UNIVERSAL DATA RECOGNITION API
# ==============================================================

def _run_source_analysis(source_id: str, task_id: Optional[str] = None):
    """Background worker that executes universal extraction, profiling, and classification."""
    try:
        src = database.get_source(source_id)
        if not src:
            raise ValueError(f"Source '{source_id}' not found.")
        real_source_id = src["source_id"]

        if task_id:
            analysis_tasks[task_id] = {"status": "analyzing", "progress": "Starting extraction...", "source_id": real_source_id}

        database.update_source_intelligence_status(real_source_id, status="analyzing")

        from sheets_client import GoogleSheetsClient
        sheets_client = sync_service.default_client if sync_service and hasattr(sync_service, 'default_client') else GoogleSheetsClient()
        reader = UniversalSpreadsheetReader(google_sheets_client=sheets_client)

        spreadsheet_ref = src.get("spreadsheet_id", "")
        extracted = None

        if src.get("source_type") == "excel_upload" or spreadsheet_ref.startswith("local_file:"):
            file_path = spreadsheet_ref.replace("local_file:", "")
            if not os.path.exists(file_path):
                # Check backend uploads directory
                possible = os.path.join(os.path.dirname(__file__), "uploads", os.path.basename(file_path))
                if os.path.exists(possible):
                    file_path = possible
            extracted = reader.extract_from_excel(file_path)
        else:
            extracted = reader.extract_from_google_sheets(spreadsheet_ref)

        sheets = extracted.get("sheets", {})
        total_sheets = len(sheets)
        total_records = 0

        # Purge any deleted worksheets that no longer exist in the workbook
        database.cleanup_deleted_worksheets(real_source_id, set(sheets.keys()))

        for s_idx, (sheet_name, sdata) in enumerate(sheets.items(), start=1):
            if task_id:
                analysis_tasks[task_id]["progress"] = f"Analyzing worksheet {s_idx}/{total_sheets}: {sheet_name}"

            raw_values = sdata.get("values", [])
            if not raw_values:
                continue

            header_rows, headers, data_start_row = UniversalSpreadsheetReader.detect_header_rows(raw_values)
            profile = intelligence_engine.profile_worksheet(
                sheet_name=sheet_name,
                values=raw_values,
                header_rows=header_rows,
                headers=headers,
                data_start_row=data_start_row
            )

            # Persist worksheet profiling
            database.save_worksheet_analysis(real_source_id, profile)

            # Persist raw dynamic records
            data_rows = raw_values[data_start_row - 1:] if len(raw_values) >= data_start_row else []
            database.save_dynamic_records(real_source_id, sheet_name, headers, data_rows)

            total_records += len(data_rows)

        database.update_source_intelligence_status(
            real_source_id,
            status="completed",
            total_sheets=total_sheets,
            total_records=total_records
        )

        if task_id:
            analysis_tasks[task_id] = {
                "status": "completed",
                "progress": f"Analysis complete. {total_sheets} worksheets and {total_records} records discovered.",
                "source_id": real_source_id,
                "total_sheets": total_sheets,
                "total_records": total_records
            }

    except Exception as e:
        logger.error(f"Spreadsheet Intelligence analysis failed for {source_id}: {e}", exc_info=True)
        try:
            target_id = real_source_id if 'real_source_id' in locals() else source_id
            database.update_source_intelligence_status(target_id, status="failed")
        except Exception:
            pass
        if task_id:
            analysis_tasks[task_id] = {
                "status": "failed",
                "error": str(e),
                "source_id": source_id
            }


@api_bp.route('/spreadsheet-intelligence/upload', methods=['POST'])
def intelligence_upload_spreadsheet():
    """Upload Excel spreadsheet (.xlsx, .xls) and register source for universal recognition."""
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({"error": "Filename is empty"}), 400

    filename = secure_filename(file.filename)
    if not (filename.endswith('.xlsx') or filename.endswith('.xls')):
        return jsonify({"error": "Only Excel .xlsx or .xls files are supported"}), 400

    uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    timestamp = int(datetime.now().timestamp())
    saved_filename = f"{timestamp}_{filename}"
    file_path = os.path.join(uploads_dir, saved_filename)
    file.save(file_path)

    display_name = request.form.get('name', '').strip() or filename.rsplit('.', 1)[0].replace('_', ' ').title()
    period = request.form.get('period', '').strip()
    description = request.form.get('description', '').strip()

    # Create source in database
    new_src = database.create_source(
        name=display_name,
        spreadsheet_url_or_id=f"local_file:{file_path}",
        period=period,
        description=description,
        status="active",
        is_active=False
    )
    source_id = new_src["source_id"]

    # Mark as excel_upload source_type
    conn = database.get_db_connection()
    conn.execute("UPDATE spreadsheet_sources SET source_type = 'excel_upload' WHERE source_id = ?", (source_id,))
    conn.commit()
    conn.close()

    # Launch analysis in background thread so HTTP response never times out
    task_id = str(uuid.uuid4())
    analysis_tasks[task_id] = {"status": "pending", "progress": "Queued for extraction...", "source_id": source_id}
    thread = threading.Thread(target=_run_source_analysis, args=(source_id, task_id), daemon=True)
    thread.start()

    return jsonify({
        "success": True,
        "message": "File uploaded and intelligence analysis started.",
        "source_id": source_id,
        "task_id": task_id
    }), 201


@api_bp.route('/spreadsheet-intelligence/analyze', methods=['POST'])
def intelligence_trigger_analysis():
    """Trigger universal spreadsheet intelligence analysis on any source."""
    data = request.get_json() or {}
    source_id = data.get('source_id', '').strip()
    if not source_id:
        active_src = database.get_active_source()
        if active_src:
            source_id = active_src['source_id']
        else:
            return jsonify({"error": "source_id is required"}), 400

    task_id = str(uuid.uuid4())
    analysis_tasks[task_id] = {"status": "pending", "progress": "Initializing analysis...", "source_id": source_id}
    thread = threading.Thread(target=_run_source_analysis, args=(source_id, task_id), daemon=True)
    thread.start()

    return jsonify({
        "success": True,
        "message": f"Intelligence analysis initiated for source '{source_id}'",
        "task_id": task_id,
        "source_id": source_id
    })


@api_bp.route('/spreadsheet-intelligence/status/<task_id>', methods=['GET'])
def intelligence_get_task_status(task_id):
    """Poll progress status of an intelligence analysis task."""
    task = analysis_tasks.get(task_id)
    if not task:
        return jsonify({"status": "unknown", "message": "Task not found"}), 404
    return jsonify(task)


@api_bp.route('/spreadsheet-intelligence/sources', methods=['GET'])
def intelligence_list_sources():
    """List all spreadsheet sources with their intelligence profiling status."""
    sources = database.list_sources(include_disabled=True)
    return jsonify({"sources": sources, "total": len(sources)})


@api_bp.route('/spreadsheet-intelligence/sources/<source_id>/worksheets', methods=['GET'])
def intelligence_get_worksheets(source_id):
    """Retrieve discovered worksheets and metadata for a source."""
    src = database.get_source(source_id)
    real_id = src["source_id"] if src else source_id
    worksheets = database.get_worksheet_metadata(real_id)
    return jsonify({"source_id": real_id, "worksheets": worksheets, "total": len(worksheets)})


@api_bp.route('/spreadsheet-intelligence/sources/<source_id>/worksheets/<sheet_name>', methods=['GET'])
def intelligence_get_single_worksheet(source_id, sheet_name):
    """Retrieve details and metadata for a specific worksheet."""
    src = database.get_source(source_id)
    real_id = src["source_id"] if src else source_id
    ws = database.get_worksheet_metadata(real_id, sheet_name=sheet_name)
    if not ws:
        return jsonify({"error": "Worksheet not found"}), 404
    columns = database.get_dynamic_columns(real_id, sheet_name)
    return jsonify({"worksheet": ws[0], "columns": columns})


@api_bp.route('/spreadsheet-intelligence/sources/<source_id>/worksheets/<sheet_name>/columns', methods=['GET'])
def intelligence_get_columns(source_id, sheet_name):
    """Get all discovered columns and semantic mappings for a worksheet."""
    src = database.get_source(source_id)
    real_id = src["source_id"] if src else source_id
    cols = database.get_dynamic_columns(real_id, sheet_name)
    return jsonify({"source_id": real_id, "sheet_name": sheet_name, "columns": cols, "total": len(cols)})


@api_bp.route('/spreadsheet-intelligence/sources/<source_id>/worksheets/<sheet_name>/columns', methods=['PUT'])
def intelligence_update_columns(source_id, sheet_name):
    """Approve or update column mappings."""
    src = database.get_source(source_id)
    real_id = src["source_id"] if src else source_id
    data = request.get_json() or {}
    columns_to_update = data.get("columns", [])

    if not columns_to_update and "column_index" in data:
        columns_to_update = [data]

    for col in columns_to_update:
        c_idx = col.get("column_index")
        role = col.get("inferred_role") or col.get("role")
        status = col.get("mapping_status", "approved")
        confidence = float(col.get("confidence", 1.0))
        if c_idx is not None and role:
            database.update_dynamic_column_mapping(
                source_id=real_id,
                sheet_name=sheet_name,
                column_index=int(c_idx),
                inferred_role=role,
                mapping_status=status,
                confidence=confidence
            )

    updated_cols = database.get_dynamic_columns(real_id, sheet_name)
    return jsonify({
        "success": True,
        "message": f"Updated {len(columns_to_update)} column mapping(s).",
        "columns": updated_cols
    })


@api_bp.route('/spreadsheet-intelligence/sources/<source_id>/worksheets/<sheet_name>/records', methods=['GET'])
def intelligence_get_records(source_id, sheet_name):
    """Get raw and dynamic records preserving every original column and literal value."""
    src = database.get_source(source_id)
    real_id = src["source_id"] if src else source_id
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 50))
    search = request.args.get("search", "").strip()

    data = database.get_dynamic_records(
        source_id=real_id,
        sheet_name=sheet_name,
        page=page,
        limit=limit,
        search=search
    )
    return jsonify(data)


@api_bp.route('/spreadsheet-intelligence/sources/<source_id>/data-quality', methods=['GET'])
def intelligence_get_data_quality(source_id):
    """Get data quality report and anomaly metrics for a source."""
    src = database.get_source(source_id)
    real_id = src["source_id"] if src else source_id
    report = database.get_data_quality_report(real_id)
    return jsonify(report)


@api_bp.route('/spreadsheet-intelligence/sources/<source_id>/sync', methods=['POST'])
def intelligence_sync_approved_data(source_id):
    """Synchronize approved mapped columns into live inventory and stock movements tables."""
    conn = None
    try:
        src = database.get_source(source_id)
        real_id = src["source_id"] if src else source_id
        worksheets = database.get_worksheet_metadata(real_id)
        imported_products = 0
        imported_movements = 0

        conn = database.get_db_connection()
        cursor = conn.cursor()
        now_iso = datetime.now(timezone.utc).isoformat()

        for ws in worksheets:
            sname = ws["sheet_name"]

            # Query dynamic columns directly using current connection
            cursor.execute("""
                SELECT original_col, inferred_role FROM dynamic_column_metadata
                WHERE source_id = ? AND sheet_name = ?
            """, (real_id, sname))
            col_rows = cursor.fetchall()

            # Map column names to semantic roles
            role_to_col: Dict[str, str] = {}
            for c in col_rows:
                role = c["inferred_role"]
                if role != "unknown" and role not in role_to_col:
                    role_to_col[role] = c["original_col"]

            # Read dynamic records
            cursor.execute("SELECT row_index, raw_data_json FROM dynamic_records WHERE source_id = ? AND sheet_name = ?", (real_id, sname))
            records = cursor.fetchall()

            for r in records:
                row_idx = r["row_index"]
                raw_dict = json.loads(r["raw_data_json"] or "{}")

                part_no = str(raw_dict.get(role_to_col.get("product_id", ""), "")).strip()
                desc = str(raw_dict.get(role_to_col.get("description", ""), "")).strip()
                cat = str(raw_dict.get(role_to_col.get("category", ""), "")).strip() or sname
                uom = str(raw_dict.get(role_to_col.get("uom", ""), "")).strip() or "NOS"
                unit_price = str(raw_dict.get(role_to_col.get("unit_price", ""), "")).strip()
                opening = str(raw_dict.get(role_to_col.get("opening_stock", ""), "")).strip()
                closing = str(raw_dict.get(role_to_col.get("closing_stock", ""), "")).strip()

                if not part_no and not desc:
                    continue

                if part_no.upper() in ["TOTAL", "SUBTOTAL", "GRAND TOTAL"]:
                    continue

                prod_id = f"{real_id}-{sname}-{part_no or row_idx}"
                # Derive status
                try:
                    c_num = float(closing.replace(',', ''))
                    status = "In Stock" if c_num > 10 else "Low Stock" if c_num > 0 else "Out of Stock"
                except Exception:
                    status = "Unknown"

                # Insert into inventory_records preserving raw values
                cursor.execute("""
                    INSERT INTO inventory_records (
                        source_id, source_sheet, source_row, product_id, part_no, description,
                        category, uom, unit_price, opening_stock, current_stock, latest_date,
                        stock_status, period, extra_fields_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id, source_sheet, source_row) DO UPDATE SET
                        product_id = excluded.product_id,
                        part_no = excluded.part_no,
                        description = excluded.description,
                        category = excluded.category,
                        uom = excluded.uom,
                        unit_price = excluded.unit_price,
                        opening_stock = excluded.opening_stock,
                        current_stock = excluded.current_stock,
                        stock_status = excluded.stock_status,
                        extra_fields_json = excluded.extra_fields_json,
                        updated_at = excluded.updated_at
                """, (
                    real_id,
                    sname,
                    row_idx,
                    prod_id,
                    part_no or f"ITEM-{row_idx}",
                    desc or part_no,
                    cat,
                    uom,
                    unit_price,
                    opening,
                    closing or opening,
                    now_iso[:10],
                    status,
                    "",
                    json.dumps(raw_dict, ensure_ascii=False),
                    now_iso
                ))
                imported_products += 1

        conn.commit()
        conn.close()

        # Update sync history
        database.record_sync_run(
            status="success",
            sheets_processed=len(worksheets),
            products_count=imported_products,
            movements_count=imported_movements,
            fingerprint="",
            source_id=real_id,
            source_name=src.get("name") if src else real_id
        )

        return jsonify({
            "success": True,
            "message": f"Successfully synchronized {imported_products} items from {len(worksheets)} worksheets.",
            "imported_products": imported_products,
            "worksheets_count": len(worksheets)
        })

    except Exception as e:
        logger.error(f"Intelligence sync failed for source {source_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

