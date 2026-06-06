import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy 2.0 declarative models."""
    pass


class Service(Base):
    __tablename__ = "services"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    repo_url: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    owner_team: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    under_remediation_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    remediation_lock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    incidents: Mapped[list["Incident"]] = relationship("Incident", back_populates="service", cascade="all, delete-orphan")
    alerts: Mapped[list["Alert"]] = relationship("Alert", back_populates="service", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="DEVELOPER", nullable=False)
    slack_user_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    commanded_incidents: Mapped[list["Incident"]] = relationship("Incident", back_populates="commander")
    authored_postmortems: Mapped[list["PostMortem"]] = relationship("PostMortem", back_populates="author")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("services.id", ondelete="RESTRICT"), index=True, nullable=False)
    commander_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="TRIGGERED", index=True, nullable=False)  # e.g., TRIGGERED, ACKNOWLEDGED, RESOLVED
    severity: Mapped[str] = mapped_column(String(16), default="SEV-3", index=True, nullable=False)  # e.g., SEV-1, SEV-2, SEV-3
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    slack_channel_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    telemetry_s3_key: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    service: Mapped["Service"] = relationship("Service", back_populates="incidents")
    commander: Mapped[Optional["User"]] = relationship("User", back_populates="commanded_incidents")
    alerts: Mapped[list["Alert"]] = relationship("Alert", back_populates="incident")
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="incident", cascade="all, delete-orphan")
    post_mortem: Mapped[Optional["PostMortem"]] = relationship("PostMortem", back_populates="incident", uselist=False, cascade="all, delete-orphan")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("incidents.id", ondelete="SET NULL"), index=True, nullable=True)
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("services.id", ondelete="RESTRICT"), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g., prometheus, datadog, pagerduty
    external_alert_id: Mapped[str] = mapped_column(String(256), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="FIRING", nullable=False)  # e.g., FIRING, RESOLVED
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    incident: Mapped[Optional["Incident"]] = relationship("Incident", back_populates="alerts")
    service: Mapped["Service"] = relationship("Service", back_populates="alerts")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("incidents.id", ondelete="SET NULL"), index=True, nullable=True)
    operator_user: Mapped[str] = mapped_column(String(128), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g., RESTART_POD, SCALE_DEPLOYMENT
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)  # e.g., PENDING, EXECUTED, FAILED, BLOCKED
    backup_state_yaml: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_preview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    incident: Mapped[Optional["Incident"]] = relationship("Incident", back_populates="audit_logs")


class PostMortem(Base):
    __tablename__ = "post_mortems"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    timeline_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    remediation_items: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    incident: Mapped["Incident"] = relationship("Incident", back_populates="post_mortem")
    author: Mapped[Optional["User"]] = relationship("User", back_populates="authored_postmortems")
