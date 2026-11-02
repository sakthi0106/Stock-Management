"""
Workbook Synchronization & Inspection Endpoints
Handles Admin manual uploads and authenticated On-Premise LAN Agent push.
"""
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Header, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.models.models import SyncRun, WorkbookConfig, AuditLog
from app.schemas.schemas import SyncRunResponse, WorkbookInspectResponse, WorkbookConfigResponse
from app.services.excel_service import ExcelService
from app.services.sync_service import SyncService
from app.core.security import require_roles, UserRole
from app.core.config import settings

router = APIRouter(prefix="/sync", tags=["Synchronization"])

@router.get("/status")
def get_sync_status(
    current_user: dict = Depends(require_roles(UserRole.ALL)),
    db: Session = Depends(get_db)
):
    runs = db.query(SyncRun).order_by(desc(SyncRun.started_at)).limit(10).all()
    latest = runs[0] if runs else None

    return {
        "latest_run": SyncRunResponse.from_orm(latest) if latest else None,
        "history": [SyncRunResponse.from_orm(r) for r in runs]
    }

@router.post("/inspect", response_model=WorkbookInspectResponse)
async def inspect_workbook(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    """Admin inspects workbook sheets, headers, and recommended mappings before importing."""
    if not file.filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Only .xlsx and .xlsm files are supported.")

    content = await file.read()
    try:
        inspected = ExcelService.inspect_workbook(content, file.filename)
        return inspected
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to inspect workbook: {str(e)}")

@router.post("/manual")
async def manual_sync_upload(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    """Admin triggers an immediate manual synchronization by uploading an updated workbook."""
    if not file.filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Only .xlsx and .xlsm files are supported.")

    content = await file.read()
    user_id = int(current_user["sub"])

    try:
        result = SyncService.execute_sync(
            db=db,
            file_bytes=content,
            file_name=file.filename,
            source_type="MANUAL_UPLOAD",
            triggered_by_user_id=user_id
        )
        return {"message": "Workbook synchronized successfully.", "details": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Synchronization failed: {str(e)}")

@router.post("/agent-push")
async def agent_push_sync(
    file: UploadFile = File(...),
    x_agent_key: Optional[str] = Header(None, alias="X-Agent-Key"),
    db: Session = Depends(get_db)
):
    """
    Endpoint for on-premise company LAN Sync Agent.
    Authenticates with secure pre-shared token without opening inbound SMB ports.
    """
    if not x_agent_key or x_agent_key != settings.SYNC_AGENT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Agent API Key."
        )

    if not file.filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Only .xlsx and .xlsm files are supported.")

    content = await file.read()
    file_hash = ExcelService.calculate_file_hash(content)

    # Check if the last successful sync had the exact same hash
    last_sync = (
        db.query(SyncRun)
        .filter(SyncRun.status.in_(["SUCCESS", "PARTIAL"]), SyncRun.rows_read > 0)
        .order_by(desc(SyncRun.started_at))
        .first()
    )
    if last_sync and last_sync.file_hash == file_hash:
        return {
            "status": "UNCHANGED",
            "message": "Workbook content hash matches last successful sync. Skipped re-import.",
            "file_hash": file_hash
        }

    try:
        result = SyncService.execute_sync(
            db=db,
            file_bytes=content,
            file_name=file.filename,
            source_type="AGENT",
            triggered_by_user_id=None
        )
        return {
            "status": "PROCESSED",
            "message": "Agent sync processed successfully.",
            "details": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent sync execution failed: {str(e)}")
