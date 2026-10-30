import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit, emr_service
from ..db import get_db
from ..deps import require_staff
from ..models import Emr, EmrHistory, Patient, Staff
from ..schemas import EmrChangesIn, EmrHistoryOut, EmrStateOut, PatientIn, PatientOut
from ..security.permissions import Perm
from ..security.tokens import Principal

router = APIRouter(tags=["staff: patients & EMR"])


def _patient(db: Session, patient_id: uuid.UUID) -> Patient:
    p = db.get(Patient, patient_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пациент не найден")
    return p


def _emr(db: Session, emr_id: uuid.UUID) -> Emr:
    e = db.get(Emr, emr_id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ЭМК не найдена")
    return e


def _acting_staff(db: Session, principal: Principal) -> Staff:
    staff = db.get(Staff, principal.staff_id)
    if staff is None or staff.is_deleted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Медработник удалён")
    return staff


def _out(p: Patient) -> PatientOut:
    out = PatientOut.model_validate(p)
    out.emr_id = p.emr.id if p.emr else None
    return out


def _fields(p: Patient) -> dict:
    return {"фамилия": p.last_name, "имя": p.first_name, "отчество": p.middle_name,
            "дата рождения": p.birth_date.isoformat(), "пол": p.sex.value, "комментарий": p.comment}


@router.get("/api/patients", response_model=list[PatientOut])
def list_patients(q: str | None = None, db: Session = Depends(get_db),
                  _: Principal = Depends(require_staff(Perm.PATIENT_READ))):
    query = select(Patient).order_by(Patient.last_name, Patient.first_name)
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.where(or_(Patient.last_name.ilike(like), Patient.first_name.ilike(like),
                                Patient.middle_name.ilike(like)))
    return [_out(p) for p in db.scalars(query)]


@router.get("/api/patients/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: uuid.UUID, db: Session = Depends(get_db),
                _: Principal = Depends(require_staff(Perm.PATIENT_READ))):
    return _out(_patient(db, patient_id))


@router.post("/api/patients", response_model=PatientOut, status_code=201)
def create_patient(body: PatientIn, request: Request, db: Session = Depends(get_db),
                   principal: Principal = Depends(require_staff(Perm.PATIENT_WRITE))):
    p = Patient(**body.model_dump())
    db.add(p)
    db.flush()
    audit.write(db, action="patient_created", principal=principal, request=request,
                message=f"Создан пациент {p.display_name} [{p.id}]")
    db.commit()
    return _out(p)


@router.put("/api/patients/{patient_id}", response_model=PatientOut)
def update_patient(patient_id: uuid.UUID, body: PatientIn, request: Request,
                   db: Session = Depends(get_db),
                   principal: Principal = Depends(require_staff(Perm.PATIENT_WRITE))):
    p = _patient(db, patient_id)
    before = _fields(p)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    audit.write(db, action="patient_updated", principal=principal, request=request,
                message=f"Изменён пациент {p.display_name} [{p.id}]: "
                        f"{audit.changes_text(before, _fields(p))}")
    db.commit()
    return _out(p)


@router.delete("/api/patients/{patient_id}", status_code=204)
def delete_patient(patient_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                   principal: Principal = Depends(require_staff(Perm.PATIENT_WRITE))):
    p = _patient(db, patient_id)
    if p.emr is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "У пациента есть ЭМК — удаление запрещено")
    name = p.display_name
    db.delete(p)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "У пациента есть ЭМК — удаление запрещено")
    audit.write(db, action="patient_deleted", principal=principal, request=request,
                message=f"Удалён пациент {name} [{patient_id}]")
    db.commit()


@router.post("/api/patients/{patient_id}/emr", response_model=EmrStateOut, status_code=201)
def create_emr(patient_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
               principal: Principal = Depends(require_staff(Perm.EMR_CREATE))):
    p = _patient(db, patient_id)
    if p.emr is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "У пациента уже есть ЭМК")
    staff = _acting_staff(db, principal)
    try:
        emr = emr_service.create_emr(db, p, staff)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "У пациента уже есть ЭМК")
    audit.write(db, action="emr_created", principal=principal, request=request,
                message=f"Создана ЭМК [{emr.id}] пациента {p.display_name} [{p.id}]")
    db.commit()
    db.refresh(emr)
    return emr_service.get_state(db, emr)


@router.get("/api/emrs/{emr_id}", response_model=EmrStateOut)
def get_emr(emr_id: uuid.UUID, at: datetime | None = None, db: Session = Depends(get_db),
            _: Principal = Depends(require_staff(Perm.EMR_READ))):
    if at is not None and at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return emr_service.get_state(db, _emr(db, emr_id), at)


@router.get("/api/emrs/{emr_id}/history", response_model=list[EmrHistoryOut])
def emr_history(emr_id: uuid.UUID, db: Session = Depends(get_db),
                _: Principal = Depends(require_staff(Perm.EMR_READ))):
    _emr(db, emr_id)
    return db.scalars(select(EmrHistory).where(EmrHistory.emr_id == emr_id)
                      .order_by(EmrHistory.id)).all()


@router.post("/api/emrs/{emr_id}/changes", response_model=EmrStateOut)
def change_emr(emr_id: uuid.UUID, body: EmrChangesIn, request: Request,
               db: Session = Depends(get_db),
               principal: Principal = Depends(require_staff(Perm.EMR_WRITE))):
    emr = _emr(db, emr_id)
    staff = _acting_staff(db, principal)
    summary = emr_service.apply_changes(db, emr, staff, body)
    audit.write(db, action="emr_updated", principal=principal, request=request,
                message=f"Изменена ЭМК [{emr.id}] пациента {emr.patient.display_name}: "
                        f"{', '.join(summary) or 'без изменений'}")
    db.commit()
    db.refresh(emr)
    return emr_service.get_state(db, emr)
