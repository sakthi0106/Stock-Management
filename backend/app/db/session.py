"""
Database engine and session management
Supports PostgreSQL with transparent fallback to SQLite for local standalone development.
"""
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

logger = logging.getLogger("stock_mgmt.db")

Base = declarative_base()

# Attempt to connect to PostgreSQL. If unavailable, use SQLite for seamless local dev/mock.
def create_app_engine():
    db_url = settings.DATABASE_URL
    try:
        if db_url.startswith("postgresql"):
            # Check if psycopg2 or asyncpg can connect
            engine = create_engine(db_url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
            # Test quick connection
            with engine.connect() as conn:
                pass
            logger.info("Successfully connected to primary PostgreSQL database.")
            return engine
    except Exception as e:
        logger.warning(
            f"Could not connect to PostgreSQL at {db_url} ({e}). "
            f"Falling back to local SQLite engine ({settings.SQLITE_FALLBACK_URL})."
        )
    
    # SQLite fallback
    engine = create_engine(
        settings.SQLITE_FALLBACK_URL,
        connect_args={"check_same_thread": False}
    )
    return engine

engine = create_app_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
