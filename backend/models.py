"""
Database models.

Two tables:
  - leads:          raw inbound lead info (what the form collects)
  - lead_decisions: agent's work product — enrichment, score, reasoning, email, trace
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


def _utcnow():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


class Lead(Base):
    """Inbound lead — what a sales rep would manually enter today."""
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # One-to-one relationship
    decision: Mapped["LeadDecision | None"] = relationship(
        "LeadDecision", back_populates="lead", uselist=False, cascade="all, delete-orphan"
    )


class LeadDecision(Base):
    """Agent output — everything the agent decided for a given lead."""
    __tablename__ = "lead_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("leads.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    enrichment_data: Mapped[str] = mapped_column(Text, nullable=True)  # JSON string
    past_interaction_found: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[int] = mapped_column(Integer, nullable=True)
    score_reason: Mapped[str] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(String(50), nullable=True)  # auto-outreach-sent | needs-human-review | discarded
    generated_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning_trace: Mapped[str] = mapped_column(Text, nullable=True)  # JSON string
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationship back to lead
    lead: Mapped["Lead"] = relationship("Lead", back_populates="decision")
