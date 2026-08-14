from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_path: Mapped[str | None] = mapped_column(String(1024))

    tabs_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    systems_complete: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    systems_incomplete: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    tabs_skipped: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    trades_imported: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    tab_results: Mapped[list | None] = mapped_column(JSONB)
