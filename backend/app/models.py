from datetime import datetime
from sqlalchemy import String, Text, Integer, DateTime, JSON, Float, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base, now, uid


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    identity: Mapped[str] = mapped_column(String(300), unique=True)
    company: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(200))
    contact: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(300), default="")
    country: Mapped[str] = mapped_column(String(60), default="México")
    employees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    industry: Mapped[str] = mapped_column(String(100), default="B2B")
    owner: Mapped[str] = mapped_column(String(100), default="Sofía Ramírez")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    angle: Mapped[str] = mapped_column(Text, default="")
    destination: Mapped[str] = mapped_column(String(100), default="#leads-intel")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    sources: Mapped[list["Source"]] = relationship(cascade="all, delete-orphan", order_by="Source.created_at")
    signals: Mapped[list["Signal"]] = relationship(cascade="all, delete-orphan")
    draft: Mapped["Draft | None"] = relationship(uselist=False, cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Signal(Base):
    __tablename__ = "signals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    type: Mapped[str] = mapped_column(String(30))
    evidence: Mapped[str] = mapped_column(Text)
    points: Mapped[int] = mapped_column(Integer)


class Draft(Base):
    __tablename__ = "drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), unique=True)
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trace: Mapped[dict] = mapped_column(JSON, default=dict)


class Audit(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50))
    actor: Mapped[str] = mapped_column(String(100), default="Sofía Ramírez")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="enrolled_simulated")
    sequence: Mapped[str] = mapped_column(String(100), default="Clara · Primer contacto")
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Config(Base):
    __tablename__ = "configuration"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)

