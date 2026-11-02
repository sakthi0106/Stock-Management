"""
Main FastAPI Application Entrypoint
"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.db.session import engine, Base, SessionLocal
from app.models.models import User, Product, WorkbookConfig
from app.core.security import hash_password, UserRole
from app.services.sync_service import SyncService
from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.products import router as products_router
from app.api.v1.movements import router as movements_router
from app.api.v1.reports import router as reports_router
from app.api.v1.sync import router as sync_router
from app.api.v1.admin import router as admin_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stock_mgmt")

def init_db_and_seed():
    """Initializes tables and seeds default authorized roles and sample data if needed."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # 1. Seed Initial Accounts if none exist
        if db.query(User).count() == 0:
            logger.info("Seeding initial company employee accounts...")
            seed_users = [
                User(
                    email="director@company.internal",
                    hashed_password=hash_password("DirectorPass2026!"),
                    full_name="Eleanor Vance (Director)",
                    role=UserRole.DIRECTOR,
                    is_active=True
                ),
                User(
                    email="purchase@company.internal",
                    hashed_password=hash_password("PurchasePass2026!"),
                    full_name="Marcus Sterling (Purchase Lead)",
                    role=UserRole.PURCHASE_TEAM,
                    is_active=True
                ),
                User(
                    email="admin@company.internal",
                    hashed_password=hash_password("AdminPass2026!"),
                    full_name="System Administrator",
                    role=UserRole.ADMIN,
                    is_active=True
                ),
            ]
            db.add_all(seed_users)
            db.commit()
            logger.info("Company accounts seeded successfully.")

        # 2. Check if products exist; if not, sync sample workbook if present
        if db.query(Product).count() == 0:
            sample_wb_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "sample-data",
                "company_inventory_master.xlsx"
            )
            if os.path.exists(sample_wb_path):
                logger.info(f"Auto-synchronizing initial sample workbook: {sample_wb_path}")
                with open(sample_wb_path, "rb") as f:
                    wb_bytes = f.read()
                admin_user = db.query(User).filter(User.role == UserRole.ADMIN).first()
                SyncService.execute_sync(
                    db=db,
                    file_bytes=wb_bytes,
                    file_name="company_inventory_master.xlsx",
                    source_type="MANUAL_UPLOAD",
                    triggered_by_user_id=admin_user.id if admin_user else None
                )
                logger.info("Initial sample inventory synchronized successfully.")
    except Exception as e:
        logger.error(f"Error during database startup seed: {e}")
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db_and_seed()
    yield
    # Shutdown

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Enterprise-grade Secure Excel-Based Stock Management API",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development. Configured via settings in production.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(dashboard_router, prefix=settings.API_V1_STR)
app.include_router(products_router, prefix=settings.API_V1_STR)
app.include_router(movements_router, prefix=settings.API_V1_STR)
app.include_router(reports_router, prefix=settings.API_V1_STR)
app.include_router(sync_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "stock-management-backend"}

@app.get("/")
def root():
    return {
        "message": "Secure Excel-Based Stock Management API",
        "docs": "/docs",
        "health": "/health"
    }
