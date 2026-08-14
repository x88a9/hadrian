"""REST endpoint for the synchronous xlsx import (API contract §1).

Body is optional ``{"path": "..."}``; defaults to ``settings.XLSX_PATH``.
A missing file yields 404; success returns the persisted ImportRun.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.schemas.import_run import (
    ImportRequest,
    ImportRunResponse,
    ProgrammaticImportRequest,
)
from app.services.import_service import (
    run_csv_import,
    run_programmatic_import,
    run_xlsx_import,
)

router = APIRouter(tags=["import"])


@router.post("/import/xlsx", response_model=ImportRunResponse)
def import_xlsx(
    body: Optional[ImportRequest] = None,
    db: Session = Depends(get_db),
) -> ImportRunResponse:
    path = (body.path if body and body.path else None) or settings.XLSX_PATH
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"xlsx file not found: {path}")
    return run_xlsx_import(db, path)


@router.post("/import/csv", response_model=ImportRunResponse)
def import_csv(
    file: UploadFile = File(...),
    system_name: str = Form(...),
    replace: bool = Form(True),
    db: Session = Depends(get_db),
) -> ImportRunResponse:
    """Import a Hadrian²-style CSV of auto trades for ``system_name`` (D2/D3/D5).

    ``replace=true`` (default) mirrors the file (delete existing auto trades
    first); ``replace=false`` appends. A CSV without any known Hadrian² columns
    yields 400.
    """
    data = file.file.read()
    try:
        return run_csv_import(
            db, file.filename or "upload.csv", data, system_name, replace
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/import/programmatic", response_model=ImportRunResponse)
def import_programmatic(
    body: Optional[ProgrammaticImportRequest] = None,
    db: Session = Depends(get_db),
) -> ImportRunResponse:
    """Import both programmatic backtest sources (Hadrian² + Hadrian_Engine).

    Body is optional ``{"hadrian2_path": ..., "engine_path": ...}``; defaults
    come from ``settings``. A missing single directory is skipped and logged;
    if BOTH directories are missing the request yields 404.
    """
    hadrian2_dir = (
        body.hadrian2_path if body and body.hadrian2_path else None
    ) or settings.HADRIAN2_RESULTS_DIR
    engine_dir = (
        body.engine_path if body and body.engine_path else None
    ) or settings.HADRIAN_ENGINE_RESULTS_DIR

    if not os.path.isdir(hadrian2_dir) and not os.path.isdir(engine_dir):
        raise HTTPException(
            status_code=404,
            detail=(
                f"no programmatic source directory found: "
                f"hadrian2={hadrian2_dir}, engine={engine_dir}"
            ),
        )
    return run_programmatic_import(db, hadrian2_dir, engine_dir)
