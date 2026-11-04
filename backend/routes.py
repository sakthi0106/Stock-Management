import math
import os
from datetime import datetime
from pathlib import Path
from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename
from sync_service import SyncService
import database

api_bp = Blueprint('api', __name__, url_prefix='/api')

sync_service: SyncService = None

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
    sid = active_src['source_id'] if source == 'active' and active_src else source
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
