import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from .models import (
    Diagnosis, Emr, EmrDiagnosis, EmrHistory, EmrPrescription, Staff, utcnow,
)
from .schemas import (
    EmrChangesIn, EmrDiagnosisOut, EmrPrescriptionOut, EmrStateOut, OpAddDiagnosis,
    OpAddPrescription, OpCancelPrescription, OpEditPrescription, OpRemoveDiagnosis,
)


def _names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return {s.id: s.display_name for s in db.scalars(select(Staff).where(Staff.id.in_(ids)))}


def get_state(db: Session, emr: Emr, at: datetime | None = None) -> EmrStateOut:
    dq = select(EmrDiagnosis).where(EmrDiagnosis.emr_id == emr.id)
    pq = select(EmrPrescription).where(EmrPrescription.emr_id == emr.id)
    if at is None:
        dq = dq.where(EmrDiagnosis.removed_at.is_(None))
        pq = pq.where(EmrPrescription.cancelled_at.is_(None))
    else:
        dq = dq.where(EmrDiagnosis.added_at <= at,
                      or_(EmrDiagnosis.removed_at.is_(None), EmrDiagnosis.removed_at > at))
        pq = pq.where(EmrPrescription.added_at <= at,
                      or_(EmrPrescription.cancelled_at.is_(None), EmrPrescription.cancelled_at > at))
    diags = db.scalars(dq.order_by(EmrDiagnosis.added_at)).all()
    prescs = db.scalars(pq.order_by(EmrPrescription.added_at)).all()
    names = _names(db, {d.added_by for d in diags} | {p.added_by for p in prescs} | {emr.created_by})

    return EmrStateOut(
        id=emr.id, patient_id=emr.patient_id, patient_name=emr.patient.display_name,
        version=emr.version, created_at=emr.created_at, created_by=names.get(emr.created_by, "?"),
        at=at,
        diagnoses=[EmrDiagnosisOut(id=d.id, diagnosis_id=d.diagnosis_id, code=d.code, name=d.name,
                                   added_at=d.added_at, added_by=names.get(d.added_by, "?"))
                   for d in diags],
        prescriptions=[EmrPrescriptionOut(id=p.id, text=p.text, added_at=p.added_at,
                                          added_by=names.get(p.added_by, "?"),
                                          replaces_id=p.replaces_id)
                       for p in prescs],
    )


def _history(db, emr, staff, at, action, payload):
    db.add(EmrHistory(emr_id=emr.id, at=at, staff_id=staff.id, staff_name=staff.display_name,
                      action=action, payload=payload))


def _active_diag(db, emr, entry_id) -> EmrDiagnosis:
    e = db.get(EmrDiagnosis, entry_id)
    if e is None or e.emr_id != emr.id or e.removed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Диагноз уже удалён из ЭМК или не найден")
    return e


def _active_presc(db, emr, entry_id) -> EmrPrescription:
    e = db.get(EmrPrescription, entry_id)
    if e is None or e.emr_id != emr.id or e.cancelled_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Назначение уже отменено или не найдено")
    return e


def create_emr(db: Session, patient, staff: Staff) -> Emr:
    now = utcnow()
    emr = Emr(patient_id=patient.id, created_by=staff.id, created_at=now)
    db.add(emr)
    db.flush()
    _history(db, emr, staff, now, "emr_created", {"patient_id": str(patient.id)})
    return emr


def apply_changes(db: Session, emr: Emr, staff: Staff, body: EmrChangesIn) -> list[str]:
    res = db.execute(update(Emr).where(Emr.id == emr.id, Emr.version == body.base_version)
                     .values(version=Emr.version + 1))
    if res.rowcount != 1:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "ЭМК изменили, пока вы редактировали. Обновите карту и повторите.")

    now = utcnow()
    summary: list[str] = []
    for op in body.operations:
        if isinstance(op, OpAddDiagnosis):
            d = db.get(Diagnosis, op.diagnosis_id)
            if d is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Нет такого диагноза")
            dup = db.scalar(select(EmrDiagnosis.id).where(
                EmrDiagnosis.emr_id == emr.id, EmrDiagnosis.diagnosis_id == d.id,
                EmrDiagnosis.removed_at.is_(None)))
            if dup:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Диагноз {d.code} уже есть в ЭМК")
            e = EmrDiagnosis(emr_id=emr.id, diagnosis_id=d.id, code=d.code, name=d.name,
                             added_at=now, added_by=staff.id)
            db.add(e)
            db.flush()
            _history(db, emr, staff, now, "diagnosis_added",
                     {"entry_id": str(e.id), "diagnosis_id": str(d.id), "code": d.code, "name": d.name})
            summary.append(f"+диагноз {d.code}")

        elif isinstance(op, OpRemoveDiagnosis):
            e = _active_diag(db, emr, op.entry_id)
            e.removed_at, e.removed_by = now, staff.id
            _history(db, emr, staff, now, "diagnosis_removed",
                     {"entry_id": str(e.id), "diagnosis_id": str(e.diagnosis_id),
                      "code": e.code, "name": e.name})
            summary.append(f"−диагноз {e.code}")

        elif isinstance(op, OpAddPrescription):
            e = EmrPrescription(emr_id=emr.id, text=op.text, added_at=now, added_by=staff.id)
            db.add(e)
            db.flush()
            _history(db, emr, staff, now, "prescription_added", {"entry_id": str(e.id), "text": e.text})
            summary.append("+назначение")

        elif isinstance(op, OpCancelPrescription):
            e = _active_presc(db, emr, op.entry_id)
            e.cancelled_at, e.cancelled_by = now, staff.id
            _history(db, emr, staff, now, "prescription_cancelled", {"entry_id": str(e.id), "text": e.text})
            summary.append("−назначение")

        elif isinstance(op, OpEditPrescription):
            old = _active_presc(db, emr, op.entry_id)
            if old.text == op.text:
                continue
            old.cancelled_at, old.cancelled_by = now, staff.id
            new = EmrPrescription(emr_id=emr.id, text=op.text, added_at=now, added_by=staff.id,
                                  replaces_id=old.id)
            db.add(new)
            db.flush()
            _history(db, emr, staff, now, "prescription_edited",
                     {"old_entry_id": str(old.id), "old_text": old.text,
                      "entry_id": str(new.id), "text": new.text})
            summary.append("~назначение")
    return summary
