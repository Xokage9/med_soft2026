import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer,
    String, Text, TypeDecorator, Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .rules import Sex, StaffRole


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime is not allowed")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


def _enum(cls):
    return Enum(cls, values_callable=lambda e: [m.value for m in e],
                native_enum=False, validate_strings=True, length=32)


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    last_name: Mapped[str] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(64))
    position: Mapped[str] = mapped_column(String(64))
    role: Mapped[StaffRole] = mapped_column(_enum(StaffRole), default=StaffRole.other)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    account: Mapped["UserAccount | None"] = relationship(back_populates="staff", uselist=False)

    @property
    def display_name(self) -> str:
        return f"{self.last_name} {self.first_name}"


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    staff_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff.id", ondelete="RESTRICT"), unique=True)

    staff: Mapped[Staff | None] = relationship(back_populates="account")


class AdminAccount(Base):
    __tablename__ = "admin_account"
    __table_args__ = (CheckConstraint("singleton = 1", name="admin_singleton"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    singleton: Mapped[int] = mapped_column(Integer, default=1, unique=True)
    username: Mapped[str] = mapped_column(String(16), default="admin")
    password_hash: Mapped[str | None] = mapped_column(Text)
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_last_step: Mapped[int] = mapped_column(Integer, default=0)
    is_configured: Mapped[bool] = mapped_column(Boolean, default=False)
    pending_password_hash: Mapped[str | None] = mapped_column(Text)
    pending_totp_secret: Mapped[str | None] = mapped_column(String(64))
    pending_setup_nonce_hash: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    jti: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    subject_kind: Mapped[str] = mapped_column(String(16))
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoke_reason: Mapped[str | None] = mapped_column(String(32))
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=uuid.uuid4)
    event_time: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(80))
    actor_name: Mapped[str | None] = mapped_column(String(128))
    source_ip: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(48))
    message: Mapped[str] = mapped_column(Text)


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    last_name: Mapped[str] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(64))
    middle_name: Mapped[str | None] = mapped_column(String(64))
    birth_date: Mapped[date] = mapped_column(Date)
    sex: Mapped[Sex] = mapped_column(_enum(Sex), default=Sex.unknown)
    comment: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    emr: Mapped["Emr | None"] = relationship(back_populates="patient", uselist=False)

    @property
    def display_name(self) -> str:
        return " ".join(p for p in (self.last_name, self.first_name, self.middle_name) if p)


class Emr(Base):
    __tablename__ = "emrs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)

    patient: Mapped[Patient] = relationship(back_populates="emr")


class EmrDiagnosis(Base):
    __tablename__ = "emr_diagnoses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    emr_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("emrs.id"), index=True)
    diagnosis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("diagnoses.id", ondelete="RESTRICT"))
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(64))
    added_at: Mapped[datetime] = mapped_column(UTCDateTime)
    added_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff.id"))
    removed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    removed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff.id"))


class EmrPrescription(Base):
    __tablename__ = "emr_prescriptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    emr_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("emrs.id"), index=True)
    text: Mapped[str] = mapped_column(String(256))
    added_at: Mapped[datetime] = mapped_column(UTCDateTime)
    added_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff.id"))
    replaces_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("emr_prescriptions.id"))


class EmrHistory(Base):
    __tablename__ = "emr_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    emr_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("emrs.id"), index=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime)
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff.id"))
    staff_name: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)
