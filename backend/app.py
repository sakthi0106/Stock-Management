import os
import atexit
import signal
import logging
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from config import Config
from database import init_db
from sheets_client import GoogleSheetsClient
from sync_service import SyncService
from routes import api_bp, init_routes
from keepalive import start_keepalive

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('app')

DIST_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist'))


def create_app():
    app = Flask(__name__)
    # Enable CORS with 24-hour preflight cache to eliminate redundant OPTIONS roundtrips
    CORS(app, resources={r"/api/*": {"origins": "*"}, r"/health": {"origins": "*"}}, max_age=86400)

    init_db()

    sheets_client = GoogleSheetsClient()
    sync_service = SyncService(sheets_client)
    sync_service.start_background_poller()

    # Launch Render free-tier keepalive ping worker (targets RENDER_EXTERNAL_URL every 10 mins)
    start_keepalive(interval_seconds=600)

    init_routes(sync_service)
    app.register_blueprint(api_bp)

    @app.route('/health', methods=['GET'])
    def server_health():
        return jsonify({"status": "ok", "service": "stock-management-backend"}), 200

    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_frontend(path):
        if path.startswith('api/'):
            return jsonify({"error": "Resource not found"}), 404
        if path != "" and os.path.exists(os.path.join(DIST_FOLDER, path)):
            return send_from_directory(DIST_FOLDER, path)
        if os.path.exists(os.path.join(DIST_FOLDER, 'index.html')):
            return send_from_directory(DIST_FOLDER, 'index.html')
        return "Frontend build not found. Please run 'npm run build' in the frontend directory.", 404

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Internal server error: {e}")
        return jsonify({"error": "Internal server error"}), 500

    # Graceful shutdown handler for Render SIGTERM
    def _graceful_shutdown(*args):
        logger.info("Graceful shutdown signal received. Stopping background poller...")
        try:
            sync_service.stop_background_poller()
        except Exception:
            pass

    import threading
    if threading.current_thread() is threading.main_thread():
        try:
            signal.signal(signal.SIGTERM, _graceful_shutdown)
            signal.signal(signal.SIGINT, _graceful_shutdown)
        except (ValueError, AttributeError, RuntimeError):
            pass
    atexit.register(_graceful_shutdown)

    return app


app = create_app()

if __name__ == '__main__':
    logger.info(f"Starting Stock Management System on http://{Config.FLASK_HOST}:{Config.FLASK_PORT}...")
    app.run(host=Config.FLASK_HOST, port=Config.FLASK_PORT, debug=False)
