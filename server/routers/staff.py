import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import require
from ..models import Staff, UserAccount, utcnow
from ..schemas import AccountCreateIn, AccountWithPasswordOut, StaffIn, StaffOut
from ..security import passwords
from ..security.permissions import Perm
from ..security.tokens import Principal, revoke_all
from .accounts import account_out

router = APIRouter(prefix="/api/admin/staff", tags=["admin: staff"])
admin_only = require(Perm.ADMIN)


def _get(db: Session, staff_id: uuid.UUID) -> Staff:
    staff = db.get(Staff, staff_id)
    if staff is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Медработник не найден")
    return staff


def _fields(s: Staff) -> dict:
    return {"фамилия": s.last_name, "имя": s.first_name, "должность": s.position,
            "роль": s.role.value}


@router.get("", response_model=list[StaffOut])
def list_staff(include_deleted: bool = False, db: Session = Depends(get_db),
               _: Principal = Depends(admin_only)):
    q = select(Staff).order_by(Staff.last_name, Staff.first_name)
    if not include_deleted:
        q = q.where(Staff.is_deleted.is_(False))
    return db.scalars(q).all()


@router.get("/{staff_id}", response_model=StaffOut)
def get_staff(staff_id: uuid.UUID, db: Session = Depends(get_db),
              _: Principal = Depends(admin_only)):
    return _get(db, staff_id)


@router.post("", response_model=StaffOut, status_code=201)
def create_staff(body: StaffIn, request: Request, db: Session = Depends(get_db),
                 principal: Principal = Depends(admin_only)):
    staff = Staff(**body.model_dump())
    db.add(staff)
    db.flush()
    audit.write(db, action="staff_created", principal=principal, request=request,
                message=f"Создан медработник {staff.display_name} [{staff.id}], "
                        f"должность «{staff.position}», роль {staff.role.value}")
    db.commit()
    return staff


@router.put("/{staff_id}", response_model=StaffOut)
def update_staff(staff_id: uuid.UUID, body: StaffIn, request: Request,
                 db: Session = Depends(get_db), principal: Principal = Depends(admin_only)):
    staff = _get(db, staff_id)
    if staff.is_deleted:
        raise HTTPException(status.HTTP_409_CONFLICT, "Медработник удалён, изменение невозможно")
    before = _fields(staff)
    old_role = staff.role
    for k, v in body.model_dump().items():
        setattr(staff, k, v)
    message = f"Изменён медработник {staff.display_name} [{staff.id}]: " \
              f"{audit.changes_text(before, _fields(staff))}"

    if staff.role != old_role and staff.account is not None:
        n = revoke_all(db, "user", staff.account.id, "role_changed")
        message += f". Смена роли: отозвано refresh-токенов аккаунта {staff.account.username}: {n}"
    audit.write(db, action="staff_updated", principal=principal, request=request, message=message)
    db.commit()
    return staff


@router.delete("/{staff_id}", response_model=StaffOut)
def delete_staff(staff_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                 principal: Principal = Depends(admin_only)):
    staff = _get(db, staff_id)
    if staff.is_deleted:
        raise HTTPException(status.HTTP_409_CONFLICT, "Медработник уже удалён")
    staff.is_deleted = True
    staff.deleted_at = utcnow()
    message = f"Удалён (логически) медработник {staff.display_name} [{staff.id}]"
    if staff.account is not None:
        acc = staff.account
        acc.is_active = False
        n = revoke_all(db, "user", acc.id, "staff_deleted")
        message += f". Аккаунт {acc.username} деактивирован, отозвано refresh-токенов: {n}"
    audit.write(db, action="staff_deleted", principal=principal, request=request, message=message)
    db.commit()
    return staff


@router.post("/{staff_id}/account", response_model=AccountWithPasswordOut, status_code=201)
def create_account(staff_id: uuid.UUID, body: AccountCreateIn, request: Request,
                   db: Session = Depends(get_db), principal: Principal = Depends(admin_only)):
    staff = _get(db, staff_id)
    if staff.is_deleted:
        raise HTTPException(status.HTTP_409_CONFLICT, "Медработник удалён")
    if staff.account is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "У медработника уже есть аккаунт")
    if db.scalar(select(UserAccount.id).where(UserAccount.username == body.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Такой логин уже занят")

    password = passwords.generate_password()
    acc = UserAccount(username=body.username, password_hash=passwords.hash_password(password),
                      staff=staff)
    db.add(acc)
    db.flush()
    audit.write(db, action="account_created", principal=principal, request=request,
                message=f"Создан аккаунт {acc.username} [{acc.id}] для медработника "
                        f"{staff.display_name} [{staff.id}]")
    db.commit()
    return AccountWithPasswordOut(account=account_out(db, acc), password=password)
