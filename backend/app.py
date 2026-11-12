import logging
from flask import Flask, jsonify
from flask_cors import CORS
from config import Config
from sheets_client import GoogleSheetsClient
from inventory_store import InventoryDataStore
from sync_manager import SyncManager
from routes import api_bp, init_routes

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    sheets_client = GoogleSheetsClient()
    store = InventoryDataStore()
    sync_manager = SyncManager(client=sheets_client, store=store)

    init_routes(sync_manager, store)
    app.register_blueprint(api_bp)

    # Start background polling only if configured
    sync_manager.start_poller()

    @app.route('/')
    def root():
        return jsonify({
            "name": "Stock Management API",
            "version": "2.0.0",
            "status": "online"
        })

    return app


app = create_app()

if __name__ == '__main__':
    port = Config.PORT
    logger.info(f"Starting server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=Config.DEBUG)
