import os
import logging
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from config import Config
from database import init_db
from sheets_client import GoogleSheetsClient
from sync_service import SyncService
from routes import api_bp, init_routes

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('app')

DIST_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist'))


def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    init_db()

    sheets_client = GoogleSheetsClient()
    sync_service = SyncService(sheets_client)
    sync_service.start_background_poller()

    init_routes(sync_service)
    app.register_blueprint(api_bp)

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

    return app


if __name__ == '__main__':
    app = create_app()
    logger.info(f"Starting Stock Management System on http://{Config.FLASK_HOST}:{Config.FLASK_PORT}...")
    app.run(host=Config.FLASK_HOST, port=Config.FLASK_PORT, debug=False)
