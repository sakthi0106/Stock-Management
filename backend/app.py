import os
import logging
from flask import Flask, jsonify
from flask_cors import CORS
from config import Config
from database import init_db
from sheets_client import GoogleSheetsClient
from sync_service import SyncService
from routes import api_bp, init_routes

# Keep the legacy Flask entrypoint importable while exposing the FastAPI modules.
__path__ = [os.path.join(os.path.dirname(__file__), "app")]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("app")

def create_app():
    app = Flask(__name__)
    
    # Configure CORS for Vite frontend
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Initialize Database
    init_db()

    # Initialize Sheets Client and Sync Service
    sheets_client = GoogleSheetsClient()
    sync_service = SyncService(sheets_client)
    sync_service.start_background_poller()

    # Register Routes
    init_routes(sync_service)
    app.register_blueprint(api_bp)

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Resource not found"}), 404

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Internal server error: {e}")
        return jsonify({"error": "Internal server error"}), 500

    return app

if __name__ == "__main__":
    app = create_app()
    logger.info(f"Starting Stock Management Flask API on {Config.FLASK_HOST}:{Config.FLASK_PORT}...")
    app.run(host=Config.FLASK_HOST, port=Config.FLASK_PORT, debug=False)
