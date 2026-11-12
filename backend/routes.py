import os
from pathlib import Path
from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename
from spreadsheet_reader import UniversalSpreadsheetReader
from config import Config

api_bp = Blueprint('api', __name__, url_prefix='/api')

_sync_manager = None
_store = None


def init_routes(sync_manager, store):
    global _sync_manager, _store
    _sync_manager = sync_manager
    _store = store


@api_bp.route('/health', methods=['GET'])
def health():
    status = _sync_manager.get_status() if _sync_manager else {}
    return jsonify({
        "status": "ok",
        "google_sheets_connected": status.get("is_configured", False),
        "sync_status": status
    })


@api_bp.route('/sync/status', methods=['GET'])
def sync_status():
    if not _sync_manager:
        return jsonify({"error": "SyncManager not initialized"}), 500
    return jsonify(_sync_manager.get_status())


@api_bp.route('/sync/refresh', methods=['POST'])
def sync_refresh():
    if not _sync_manager:
        return jsonify({"error": "SyncManager not initialized"}), 500
    success = _sync_manager.sync(force=True)
    return jsonify({"success": success, "status": _sync_manager.get_status()})


@api_bp.route('/sync/pause', methods=['POST'])
def sync_pause():
    if not _sync_manager:
        return jsonify({"error": "SyncManager not initialized"}), 500
    _sync_manager.pause_sync()
    return jsonify({"success": True, "message": "Sync paused", "status": _sync_manager.get_status()})


@api_bp.route('/sync/resume', methods=['POST'])
def sync_resume():
    if not _sync_manager:
        return jsonify({"error": "SyncManager not initialized"}), 500
    _sync_manager.resume_sync()
    return jsonify({"success": True, "message": "Sync resumed", "status": _sync_manager.get_status()})


@api_bp.route('/dashboard', methods=['GET'])
def get_dashboard():
    if not _store:
        return jsonify({"error": "Data store unavailable"}), 500
    summary = _store.get_dashboard_summary()
    summary["sync_status"] = _sync_manager.get_status() if _sync_manager else {}
    return jsonify(summary)


@api_bp.route('/inventory', methods=['GET'])
def get_inventory():
    if not _store:
        return jsonify({"error": "Data store unavailable"}), 500

    sheet_filter = request.args.get('sheet', '').strip()
    search = request.args.get('search', '').strip().lower()

    items = _store.products
    if sheet_filter:
        items = [p for p in items if p.get('source_sheet') == sheet_filter]
    if search:
        items = [p for p in items if search in p.get('part_no', '').lower() or search in p.get('description', '').lower()]

    return jsonify({
        "items": items,
        "total": len(items)
    })


@api_bp.route('/movements', methods=['GET'])
def get_movements():
    if not _store:
        return jsonify({"error": "Data store unavailable"}), 500

    sheet_filter = request.args.get('sheet', '').strip()
    search = request.args.get('search', '').strip().lower()
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()
    m_type = request.args.get('type', '').strip().upper()

    movements = _store.movements
    if sheet_filter:
        movements = [m for m in movements if m.get('source_sheet') == sheet_filter]
    if search:
        movements = [m for m in movements if search in m.get('part_no', '').lower() or search in m.get('description', '').lower()]
    if from_date:
        movements = [m for m in movements if m.get('date', '') >= from_date]
    if to_date:
        movements = [m for m in movements if m.get('date', '') <= to_date]
    if m_type in ('IN', 'OUT'):
        movements = [m for m in movements if m.get('movement_type') == m_type]

    return jsonify({
        "items": movements,
        "total": len(movements)
    })


@api_bp.route('/worksheets', methods=['GET'])
def get_worksheets():
    if not _store:
        return jsonify({"error": "Data store unavailable"}), 500
    return jsonify({
        "worksheets": _store.worksheets,
        "total": len(_store.worksheets)
    })


@api_bp.route('/upload', methods=['POST'])
def upload_file():
    """Allows uploading local Excel spreadsheets as an immediate data source."""
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    filename = secure_filename(file.filename)
    if not (filename.endswith('.xlsx') or filename.endswith('.xls')):
        return jsonify({"error": "Only .xlsx and .xls files are supported"}), 400

    upload_dir = Config.UPLOAD_FOLDER
    os.makedirs(upload_dir, exist_ok=True)
    save_path = os.path.join(upload_dir, filename)
    file.save(save_path)

    try:
        reader = UniversalSpreadsheetReader()
        extracted = reader.extract_from_excel(save_path)
        raw_dict = {sname: sdata.get('values', []) for sname, sdata in extracted.get('sheets', {}).items()}

        _store.update_from_raw_sheets(raw_dict)
        _store.source_metadata["title"] = filename
        _store.source_metadata["source_type"] = "excel_upload"

        return jsonify({
            "success": True,
            "message": f"Successfully loaded {len(_store.products)} products and {len(_store.movements)} movements from {filename}",
            "total_items": len(_store.products),
            "total_movements": len(_store.movements)
        })
    except Exception as e:
        return jsonify({"error": f"Failed to parse uploaded spreadsheet: {str(e)}"}), 500
