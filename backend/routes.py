import math
import os
from datetime import datetime
from pathlib import Path
from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename
from sync_service import SyncService
import database

api_bp = Blueprint("api", __name__, url_prefix="/api")

# Will be initialized in app.py
sync_service: SyncService = None

def init_routes(service: SyncService):
    global sync_service
    sync_service = service

FORBIDDEN_KEYWORDS = ["amount", "total cost", "total price", "closing value", "total value", "closing stk val"]

def is_amount_field(key: str) -> bool:
    k = key.lower()
    return any(kw in k for kw in FORBIDDEN_KEYWORDS)

def _get_service_for_request():
    """Resolve the InventoryService based on optional ?source= query param."""
    source = request.args.get("source", "active").strip()
    return sync_service.get_service(source_filter=source), source

# ------------------------------------------------------------------ #
#  Health & Sheets                                                     #
# ------------------------------------------------------------------ #

@api_bp.route("/health", methods=["GET"])
def health():
    status = sync_service.get_status()
    return jsonify({
        "status": "ok",
        "sheets_connected": status["is_live_google_sheet"],
        "mode": "live" if status["is_live_google_sheet"] else "demo",
        "sync_state": status["state"]
    })

@api_bp.route("/sheets", methods=["GET"])
def get_sheets():
    status = sync_service.get_status()
    return jsonify({"sheets": status.get("sheets", [])})

# ------------------------------------------------------------------ #
#  Spreadsheet Sources Management                                       #
# ------------------------------------------------------------------ #

@api_bp.route("/sources", methods=["GET"])
def list_sources():
    include_disabled = request.args.get("include_disabled", "false").lower() == "true"
    sources = database.list_sources(include_disabled=include_disabled)
    # Enrich with live sync status from in-memory service
    statuses = {s["source_id"]: s for s in sync_service.get_all_source_statuses()}
    for src in sources:
        live = statuses.get(src["source_id"], {})
        src["live_state"] = live.get("state", "pending")
        src["is_live_google_sheet"] = live.get("is_live", False)
    return jsonify({"sources": sources, "total": len(sources)})

@api_bp.route("/sources", methods=["POST"])
def create_source():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    url_or_id = (data.get("spreadsheet_url_or_id") or data.get("spreadsheet_id") or "").strip()
    period = (data.get("period") or "").strip()
    description = (data.get("description") or "").strip()
    status = (data.get("status") or "active").strip()
    is_active = bool(data.get("is_active", False))
    poll_interval = int(data.get("poll_interval_seconds") or 30)

    if not name:
        return jsonify({"error": "name is required"}), 400
    if not url_or_id:
        return jsonify({"error": "spreadsheet_url_or_id is required"}), 400

    try:
        src = database.create_source(
            name=name,
            spreadsheet_url_or_id=url_or_id,
            period=period,
            description=description,
            status=status,
            is_active=is_active,
            poll_interval=poll_interval
        )
        sync_service.register_source(src)
        # Attempt immediate sync
        sync_ok = sync_service.sync_source(src["source_id"])
        updated_src = database.get_source(src["source_id"]) or src
        return jsonify({
            "source": updated_src,
            "sync_success": sync_ok,
            "message": "Spreadsheet source registered and synced successfully" if sync_ok else "Registered, but remote sync failed (check permissions)"
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route("/sources/upload", methods=["POST"])
def upload_source():
    """Upload an Excel (.xlsx, .xls) workbook file directly as a spreadsheet source."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "No file selected"}), 400

    filename = secure_filename(f.filename)
    if not (filename.lower().endswith(".xlsx") or filename.lower().endswith(".xls")):
        return jsonify({"error": "Only .xlsx and .xls Excel workbooks are supported"}), 400

    upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    saved_path = os.path.join(upload_dir, f"{int(datetime.now().timestamp())}_{filename}")
    f.save(saved_path)

    name = request.form.get("name") or Path(filename).stem
    period = request.form.get("period", "").strip()
    description = request.form.get("description", "").strip()
    is_active = request.form.get("is_active", "false").lower() in ("true", "1")

    try:
        src = database.create_source(
            name=name,
            spreadsheet_url_or_id=f"local_file:{saved_path}",
            period=period,
            description=description,
            status="active",
            is_active=is_active,
            poll_interval=30
        )
        sync_service.register_source(src)
        sync_ok = sync_service.sync_source(src["source_id"])
        updated_src = database.get_source(src["source_id"]) or src
        return jsonify({
            "source": updated_src,
            "sync_success": sync_ok,
            "message": "Excel workbook uploaded and processed successfully"
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route("/sources/<source_id>", methods=["GET"])
def get_source(source_id: str):
    src = database.get_source(source_id)
    if not src:
        return jsonify({"error": "Source not found"}), 404
    sheets = database.get_sheets_for_source(source_id)
    live = sync_service.get_source_status(source_id)
    src["sheets"] = sheets
    src["live_state"] = live.get("state", "pending")
    src["is_live_google_sheet"] = live.get("is_live", False)
    src["live_sheets"] = live.get("sheets", [])
    return jsonify({"source": src})

@api_bp.route("/sources/<source_id>", methods=["PUT"])
def update_source(source_id: str):
    data = request.get_json(force=True) or {}
    allowed = ["name", "description", "period", "status", "poll_interval_seconds", "spreadsheet_id", "is_active"]
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400
    src = database.update_source(source_id, updates)
    if not src:
        return jsonify({"error": "Source not found"}), 404
    sync_service.reload_sources()
    return jsonify({"source": src})

@api_bp.route("/sources/<source_id>", methods=["DELETE"])
def delete_source(source_id: str):
    src = database.get_source(source_id)
    if not src:
        return jsonify({"error": "Source not found"}), 404
    
    # If this is active, promote another source first so active is never orphaned
    if src.get("is_active"):
        all_sources = database.list_sources(include_disabled=True)
        other_sources = [s for s in all_sources if s["source_id"] != source_id]
        if other_sources:
            database.set_active_source(other_sources[0]["source_id"])

    database.delete_source(source_id)
    sync_service.unregister_source(source_id)
    sync_service.reload_sources()
    return jsonify({"message": f"Source {source_id} deleted successfully"})

@api_bp.route("/sources/<source_id>/sheets/<sheet_name>", methods=["DELETE"])
def delete_source_sheet(source_id: str, sheet_name: str):
    """Delete / exclude an individual worksheet from a source."""
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM spreadsheet_sheets WHERE source_id = ? AND sheet_name = ?', (source_id, sheet_name))
    cursor.execute('DELETE FROM sheet_column_mappings WHERE source_id = ? AND sheet_name = ?', (source_id, sheet_name))
    cursor.execute('DELETE FROM inventory_records WHERE source_id = ? AND source_sheet = ?', (source_id, sheet_name))
    cursor.execute('DELETE FROM stock_movements WHERE source_id = ? AND source_sheet = ?', (source_id, sheet_name))
    conn.commit()
    conn.close()
    database.record_audit("SHEET_DELETED", f"Deleted worksheet {sheet_name} from source {source_id}")
    return jsonify({"message": f"Worksheet {sheet_name} removed from {source_id}"})

@api_bp.route("/sources/<source_id>/activate", methods=["POST"])
def activate_source(source_id: str):
    ok = database.set_active_source(source_id)
    if not ok:
        return jsonify({"error": "Source not found"}), 404
    sync_service.reload_sources()
    return jsonify({"message": f"Source {source_id} is now active", "source_id": source_id})

@api_bp.route("/sources/<source_id>/archive", methods=["POST"])
def archive_source(source_id: str):
    ok = database.archive_source(source_id)
    if not ok:
        return jsonify({"error": "Source not found or already archived"}), 404
    sync_service.reload_sources()
    return jsonify({"message": f"Source {source_id} archived"})

@api_bp.route("/sources/<source_id>/sync", methods=["POST"])
def sync_source(source_id: str):
    src = database.get_source(source_id)
    if not src:
        return jsonify({"error": "Source not found"}), 404
    force = request.get_json(force=True, silent=True) or {}
    ok = sync_service.sync_source(source_id, force=bool(force.get("force", True)))
    status = sync_service.get_source_status(source_id)
    return jsonify({"success": ok, "status": status})

@api_bp.route("/sources/<source_id>/sheets", methods=["GET"])
def get_source_sheets(source_id: str):
    src = database.get_source(source_id)
    if not src:
        return jsonify({"error": "Source not found"}), 404
    sheets = database.get_sheets_for_source(source_id)
    return jsonify({"source_id": source_id, "sheets": sheets, "total": len(sheets)})

# ------------------------------------------------------------------ #
#  Inventory                                                            #
# ------------------------------------------------------------------ #

@api_bp.route("/inventory", methods=["GET"])
def get_inventory():
    source = request.args.get("source", "active").strip()
    srv = sync_service.get_service(source_filter=source)
    if srv is None:
        return jsonify({"error": "No inventory data available"}), 503

    search = request.args.get("search", "").strip()
    sheet = request.args.get("sheet", "").strip()
    category = request.args.get("category", "").strip()
    part_no = request.args.get("part_no", "").strip()
    uom = request.args.get("uom", "").strip()
    status = request.args.get("status", "").strip()

    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))
    sort_by = request.args.get("sort_by", "product_id")
    sort_order = request.args.get("sort_order", "asc")

    all_prods = srv.get_products(
        search=search,
        sheet=sheet,
        category=category,
        part_no=part_no,
        uom=uom,
        status=status
    )

    # Source-level filter when viewing "all" but wanting a single source
    filter_source = request.args.get("filter_source", "").strip()
    if filter_source:
        all_prods = [p for p in all_prods if p.get("source_id", "") == filter_source]

    def sort_key(p):
        v = p.get(sort_by)
        if v is None or v in ("NA", "-"):
            return ""
        return str(v).lower() if isinstance(v, str) else v

    all_prods.sort(key=sort_key, reverse=(sort_order.lower() == "desc"))

    total = len(all_prods)
    total_pages = max(1, math.ceil(total / page_size))
    start_idx = (page - 1) * page_size
    items = all_prods[start_idx: start_idx + page_size]

    sanitized_items = []
    for item in items:
        clean = {k: v for k, v in item.items() if not is_amount_field(k)}
        if "extra_fields" in clean:
            clean["extra_fields"] = {k: v for k, v in clean["extra_fields"].items() if not is_amount_field(k)}
        sanitized_items.append(clean)

    return jsonify({
        "items": sanitized_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "source_filter": source,
        "categories": sorted(list({p["category"] for p in srv.products if p.get("category")})),
        "sheets": sorted(list({p["source_sheet"] for p in srv.products if p.get("source_sheet")})),
        "uoms": sorted(list({p["uom"] for p in srv.products if p.get("uom")}))
    })

@api_bp.route("/inventory/<product_id>", methods=["GET"])
def get_product(product_id: str):
    source = request.args.get("source", "active").strip()
    srv = sync_service.get_service(source_filter=source)
    if srv is None:
        return jsonify({"error": "No inventory data available"}), 503
    prod = srv.get_product_by_id(product_id)
    if not prod:
        return jsonify({"error": "Product not found"}), 404

    clean = {k: v for k, v in prod.items() if not is_amount_field(k)}
    if "extra_fields" in clean:
        clean["extra_fields"] = {k: v for k, v in clean["extra_fields"].items() if not is_amount_field(k)}

    movements = srv.get_movements(product_id=product_id)
    return jsonify({"product": clean, "movements": movements})

# ------------------------------------------------------------------ #
#  Movements                                                            #
# ------------------------------------------------------------------ #

@api_bp.route("/movements", methods=["GET"])
def get_movements():
    source = request.args.get("source", "active").strip()
    srv = sync_service.get_service(source_filter=source)
    if srv is None:
        return jsonify({"items": [], "total": 0})

    product_id = request.args.get("product_id", "").strip()
    from_date = request.args.get("from_date", "").strip()
    to_date = request.args.get("to_date", "").strip()
    movement_type = request.args.get("movement_type", "").strip()

    items = srv.get_movements(
        product_id=product_id,
        from_date=from_date,
        to_date=to_date,
        movement_type=movement_type
    )
    return jsonify({"items": items, "total": len(items)})

# ------------------------------------------------------------------ #
#  Dashboard                                                            #
# ------------------------------------------------------------------ #

@api_bp.route("/dashboard", methods=["GET"])
def get_dashboard():
    source = request.args.get("source", "active").strip()
    srv = sync_service.get_service(source_filter=source)
    if srv is None:
        return jsonify({"error": "No data available"}), 503
    summary = srv.get_dashboard_summary()
    sync_status = sync_service.get_status()
    summary["sync_status"] = sync_status
    summary["source_filter"] = source
    return jsonify(summary)

# ------------------------------------------------------------------ #
#  Reports                                                              #
# ------------------------------------------------------------------ #

@api_bp.route("/reports/movements", methods=["GET"])
def get_movement_reports():
    source = request.args.get("source", "active").strip()
    srv = sync_service.get_service(source_filter=source)
    if srv is None:
        return jsonify({"items": [], "total_records": 0})

    product_id = request.args.get("product_id", "").strip()
    from_date = request.args.get("from_date", "").strip()
    to_date = request.args.get("to_date", "").strip()

    items = srv.get_movements(product_id=product_id, from_date=from_date, to_date=to_date)
    return jsonify({"items": items, "total_records": len(items)})

# ------------------------------------------------------------------ #
#  Sync                                                                 #
# ------------------------------------------------------------------ #

@api_bp.route("/sync/status", methods=["GET"])
def get_sync_status():
    return jsonify(sync_service.get_status())

@api_bp.route("/sync/refresh", methods=["POST"])
def trigger_refresh():
    source = request.args.get("source", "active").strip()
    if source == "active":
        success = sync_service.perform_sync(force=True)
    else:
        success = sync_service.sync_source(source, force=True)
    status = sync_service.get_status()
    return jsonify({"success": success, "status": status})

@api_bp.route("/sync/history", methods=["GET"])
def get_sync_history():
    source = request.args.get("source", None)
    limit = int(request.args.get("limit", 15))
    runs = database.get_recent_sync_runs(source_id=source, limit=limit)
    return jsonify({"runs": runs, "total": len(runs)})

# ------------------------------------------------------------------ #
#  Data Quality                                                         #
# ------------------------------------------------------------------ #

@api_bp.route("/data-quality", methods=["GET"])
def get_data_quality():
    source = request.args.get("source", "active").strip()
    srv = sync_service.get_service(source_filter=source)
    if srv is None:
        return jsonify({"total_issues": 0, "issues": [], "duplicate_ids": [], "sheets_analyzed": 0})
    report = srv.get_data_quality_report()
    return jsonify(report)
