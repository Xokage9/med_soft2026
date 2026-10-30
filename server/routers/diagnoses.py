import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import require
from ..models import Diagnosis, EmrDiagnosis
from ..schemas import DiagnosisIn, DiagnosisOut, SeedResultOut
from ..security.permissions import Perm
from ..security.tokens import Principal
from ..settings import settings

router = APIRouter(tags=["diagnoses"])
admin_only = require(Perm.ADMIN)

DUPLICATE = "Диагноз с таким кодом или наименованием уже есть"


def _get(db: Session, diagnosis_id: uuid.UUID) -> Diagnosis:
    d = db.get(Diagnosis, diagnosis_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Диагноз не найден")
    return d


@router.get("/api/diagnoses", response_model=list[DiagnosisOut])
def list_diagnoses(db: Session = Depends(get_db),
                   _: Principal = Depends(require(Perm.DIAGNOSIS_READ))):
    return db.scalars(select(Diagnosis).order_by(Diagnosis.code)).all()


@router.post("/api/admin/diagnoses", response_model=DiagnosisOut, status_code=201)
def create_diagnosis(body: DiagnosisIn, request: Request, db: Session = Depends(get_db),
                     principal: Principal = Depends(admin_only)):
    d = Diagnosis(code=body.code, name=body.name)
    db.add(d)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE)
    audit.write(db, action="diagnosis_created", principal=principal, request=request,
                message=f"Добавлен диагноз {d.code} «{d.name}»")
    db.commit()
    return d


@router.put("/api/admin/diagnoses/{diagnosis_id}", response_model=DiagnosisOut)
def update_diagnosis(diagnosis_id: uuid.UUID, body: DiagnosisIn, request: Request,
                     db: Session = Depends(get_db), principal: Principal = Depends(admin_only)):
    d = _get(db, diagnosis_id)
    before = {"код": d.code, "наименование": d.name}
    d.code, d.name = body.code, body.name
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE)
    audit.write(db, action="diagnosis_updated", principal=principal, request=request,
                message=f"Изменён диагноз [{d.id}]: "
                        f"{audit.changes_text(before, {'код': d.code, 'наименование': d.name})}")
    db.commit()
    return d


@router.delete("/api/admin/diagnoses/{diagnosis_id}", status_code=204)
def delete_diagnosis(diagnosis_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                     principal: Principal = Depends(admin_only)):
    d = _get(db, diagnosis_id)
    if db.scalar(select(EmrDiagnosis.id).where(EmrDiagnosis.diagnosis_id == d.id).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Диагноз используется в ЭМК, удалить нельзя")
    db.delete(d)
    audit.write(db, action="diagnosis_deleted", principal=principal, request=request,
                message=f"Удалён диагноз {d.code} «{d.name}»")
    db.commit()


@router.post("/api/admin/diagnoses/load", response_model=SeedResultOut)
def load_diagnoses(request: Request, db: Session = Depends(get_db),
                   principal: Principal = Depends(admin_only)):
    items = json.loads(settings.seed_diagnoses.read_text(encoding="utf-8"))
    created = updated = 0
    skipped: list[str] = []
    for item in items:
        body = DiagnosisIn(**item)
        by_code = db.scalar(select(Diagnosis).where(Diagnosis.code == body.code))
        by_name = db.scalar(select(Diagnosis).where(Diagnosis.name == body.name))
        if by_name is not None and by_name is not by_code:
            skipped.append(f"{body.code}: наименование «{body.name}» занято кодом {by_name.code}")
        elif by_code is None:
            db.add(Diagnosis(code=body.code, name=body.name))
            created += 1
        elif by_code.name != body.name:
            by_code.name = body.name
            updated += 1
        db.flush()
    audit.write(db, action="diagnoses_loaded", principal=principal, request=request,
                message=f"Загружен реестр диагнозов: добавлено {created}, обновлено {updated}, "
                        f"пропущено {len(skipped)}")
    db.commit()
    return SeedResultOut(created=created, updated=updated, skipped=skipped)
