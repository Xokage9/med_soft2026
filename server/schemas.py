import uuid
from datetime import date, datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from . import rules as R
from .rules import Sex, StaffRole


def Text(min_len: int, max_len: int, pattern: str | None = None):  # noqa: N802
    return Annotated[str, StringConstraints(
        strip_whitespace=True, min_length=min_len, max_length=max_len, pattern=pattern)]


def _empty_to_none(v):
    if isinstance(v, str) and not v.strip():
        return None
    return v


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginIn(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)]
    password: Annotated[str, StringConstraints(max_length=256)]


class AdminLoginIn(BaseModel):
    password: Annotated[str, StringConstraints(max_length=256)]
    code: Annotated[str, StringConstraints(strip_whitespace=True, max_length=16)]


class RefreshIn(BaseModel):
    refresh_token: Annotated[str, StringConstraints(max_length=4096)]


class SetupBeginIn(BaseModel):
    password: Annotated[str, StringConstraints(max_length=256)]
    password_confirm: Annotated[str, StringConstraints(max_length=256)]


class SetupBeginOut(BaseModel):
    setup_id: str
    secret: str
    otpauth_uri: str
    qr_data_url: str


class SetupCompleteIn(BaseModel):
    setup_id: Annotated[str, StringConstraints(max_length=128)]
    code: Annotated[str, StringConstraints(strip_whitespace=True, max_length=16)]


class MeOut(BaseModel):
    kind: str
    id: uuid.UUID
    username: str
    role: str
    staff_id: uuid.UUID | None
    name: str
    permissions: list[str]


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    me: MeOut


class StaffIn(BaseModel):
    last_name: Text(R.STAFF_NAME_MIN, R.STAFF_NAME_MAX)
    first_name: Text(R.STAFF_NAME_MIN, R.STAFF_NAME_MAX)
    position: Text(R.STAFF_POSITION_MIN, R.STAFF_POSITION_MAX)
    role: StaffRole = StaffRole.other


class AccountBrief(ORM):
    id: uuid.UUID
    username: str
    is_active: bool


class StaffOut(ORM):
    id: uuid.UUID
    last_name: str
    first_name: str
    position: str
    role: StaffRole
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    account: AccountBrief | None


class AccountCreateIn(BaseModel):
    username: Text(R.USERNAME_MIN, R.USERNAME_MAX, R.USERNAME_PATTERN)


class AccountPatchIn(BaseModel):
    is_active: bool


class AccountOut(BaseModel):
    id: uuid.UUID
    username: str
    created_at: datetime
    updated_at: datetime
    is_active: bool
    staff_id: uuid.UUID | None
    staff_name: str | None
    staff_role: StaffRole | None
    staff_deleted: bool | None
    active_sessions: int


class AccountWithPasswordOut(BaseModel):
    account: AccountOut
    password: str
    revoked_tokens: int = 0


class DiagnosisIn(BaseModel):
    code: Text(R.DIAGNOSIS_CODE_LEN, R.DIAGNOSIS_CODE_LEN)
    name: Text(R.DIAGNOSIS_NAME_MIN, R.DIAGNOSIS_NAME_MAX)


class DiagnosisOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    created_at: datetime
    updated_at: datetime


class SeedResultOut(BaseModel):
    created: int
    updated: int
    skipped: list[str]


class PatientIn(BaseModel):
    last_name: Text(R.PATIENT_NAME_MIN, R.PATIENT_NAME_MAX)
    first_name: Text(R.PATIENT_NAME_MIN, R.PATIENT_NAME_MAX)
    middle_name: Text(R.PATIENT_NAME_MIN, R.PATIENT_NAME_MAX) | None = None
    birth_date: date
    sex: Sex = Sex.unknown
    comment: Text(1, R.PATIENT_COMMENT_MAX) | None = None

    _blank = field_validator("middle_name", "comment", mode="before")(_empty_to_none)

    @field_validator("birth_date")
    @classmethod
    def _birth_date(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("дата рождения не может быть в будущем")
        if v.year < R.PATIENT_MIN_BIRTH_YEAR:
            raise ValueError(f"дата рождения не раньше {R.PATIENT_MIN_BIRTH_YEAR} года")
        return v


class PatientOut(ORM):
    id: uuid.UUID
    last_name: str
    first_name: str
    middle_name: str | None
    birth_date: date
    sex: Sex
    comment: str | None
    created_at: datetime
    updated_at: datetime
    emr_id: uuid.UUID | None = None


class OpAddDiagnosis(BaseModel):
    op: Literal["add_diagnosis"]
    diagnosis_id: uuid.UUID


class OpRemoveDiagnosis(BaseModel):
    op: Literal["remove_diagnosis"]
    entry_id: uuid.UUID


class OpAddPrescription(BaseModel):
    op: Literal["add_prescription"]
    text: Text(R.PRESCRIPTION_MIN, R.PRESCRIPTION_MAX)


class OpCancelPrescription(BaseModel):
    op: Literal["cancel_prescription"]
    entry_id: uuid.UUID


class OpEditPrescription(BaseModel):
    op: Literal["edit_prescription"]
    entry_id: uuid.UUID
    text: Text(R.PRESCRIPTION_MIN, R.PRESCRIPTION_MAX)


EmrOperation = Annotated[
    Union[OpAddDiagnosis, OpRemoveDiagnosis, OpAddPrescription, OpCancelPrescription,
          OpEditPrescription],
    Field(discriminator="op"),
]


class EmrChangesIn(BaseModel):
    base_version: int
    operations: list[EmrOperation] = Field(min_length=1, max_length=100)


class EmrDiagnosisOut(BaseModel):
    id: uuid.UUID
    diagnosis_id: uuid.UUID
    code: str
    name: str
    added_at: datetime
    added_by: str


class EmrPrescriptionOut(BaseModel):
    id: uuid.UUID
    text: str
    added_at: datetime
    added_by: str
    replaces_id: uuid.UUID | None


class EmrStateOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str
    version: int
    created_at: datetime
    created_by: str
    at: datetime | None
    diagnoses: list[EmrDiagnosisOut]
    prescriptions: list[EmrPrescriptionOut]


class EmrHistoryOut(ORM):
    id: int
    at: datetime
    staff_id: uuid.UUID
    staff_name: str
    action: str
    payload: dict


class AuditOut(ORM):
    seq: int
    event_id: uuid.UUID
    event_time: datetime
    actor: str
    actor_name: str | None
    source_ip: str | None
    action: str
    message: str
