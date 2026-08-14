from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

SYSTEM_CONCEPT_SOURCES = ("manual", "heuristic")


class Concept(Base):
    """A trading concept (Open Interest, Funding, ...) — M:N to systems.

    Seeded (names only) by migration 0003. Assignments live in
    ``SystemConcept`` and carry a ``source`` so heuristic edges stay
    distinguishable from manual ones.
    """

    __tablename__ = "concepts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    system_links: Mapped[list["SystemConcept"]] = relationship(
        back_populates="concept",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SystemConcept(Base):
    """Association between a system and a concept (M:N with metadata)."""

    __tablename__ = "system_concepts"

    id: Mapped[int] = mapped_column(primary_key=True)
    system_id: Mapped[int] = mapped_column(
        ForeignKey("systems.id", ondelete="CASCADE"), nullable=False
    )
    concept_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(
        Enum(*SYSTEM_CONCEPT_SOURCES, name="system_concept_source", native_enum=False),
        nullable=False,
        default="manual",
        server_default="manual",
    )
    # Grund des heuristischen Matches (Phase 6, D6); NULL bei manueller Zuweisung.
    match_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    concept: Mapped["Concept"] = relationship(back_populates="system_links")

    __table_args__ = (
        UniqueConstraint("system_id", "concept_id", name="uq_system_concept"),
    )
