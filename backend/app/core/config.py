"""
Application Configuration Settings
"""
import os
from typing import List

class Settings:
    PROJECT_NAME: str = "Secure Excel Stock Management Dashboard"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "prod-stock-mgmt-secret-key-change-in-env-98327461")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12 hours
    ALGORITHM: str = "HS256"
    
    # Database URL: Primary is PostgreSQL. If not set or during quick standalone testing, SQLite fallback is enabled.
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql+psycopg2://postgres:postgres@localhost:5432/stock_db"
    )
    # Automatic fallback for local standalone testing if postgresql driver isn't installed yet or connection fails
    SQLITE_FALLBACK_URL: str = "sqlite:///./stock_management.db"
    
    # Sync Agent secret token for authenticated on-premise push
    SYNC_AGENT_API_KEY: str = os.getenv("SYNC_AGENT_API_KEY", "corp-sync-agent-secret-auth-token-2026")
    
    # Default allowed origins
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
    
    # Default workbook directory
    WORKBOOK_STORAGE_PATH: str = os.getenv("WORKBOOK_STORAGE_PATH", "./sample-data")

settings = Settings()
