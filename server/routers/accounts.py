import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import require
from ..models import UserAccount
from ..schemas import AccountOut, AccountPatchIn, AccountWithPasswordOut
from ..security import passwords
from ..security.permissions import Perm
from ..security.tokens import Principal, active_refresh_count, revoke_all

router = APIRouter(prefix="/api/admin/accounts", tags=["admin: accounts"])
admin_only = require(Perm.ADMIN)


def account_out(db: Session, acc: UserAccount) -> AccountOut:
    s = acc.staff
    return AccountOut(
        id=acc.id, username=acc.username, created_at=acc.created_at, updated_at=acc.updated_at,
        is_active=acc.is_active, staff_id=s.id if s else None,
        staff_name=s.display_name if s else None, staff_role=s.role if s else None,
        staff_deleted=s.is_deleted if s else None,
        active_sessions=active_refresh_count(db, "user", acc.id),
    )


def _get(db: Session, account_id: uuid.UUID) -> UserAccount:
    acc = db.get(UserAccount, account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Аккаунт не найден")
    return acc


@router.get("", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db), _: Principal = Depends(admin_only)):
    return [account_out(db, a) for a in db.scalars(select(UserAccount).order_by(UserAccount.username))]


@router.post("/{account_id}/reset-password", response_model=AccountWithPasswordOut)
def reset_password(account_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                   principal: Principal = Depends(admin_only)):
    acc = _get(db, account_id)
    password = passwords.generate_password()
    acc.password_hash = passwords.hash_password(password)
    n = revoke_all(db, "user", acc.id, "password_changed")
    audit.write(db, action="account_password_reset", principal=principal, request=request,
                message=f"Сгенерирован новый пароль для аккаунта {acc.username} [{acc.id}]; "
                        f"отозвано refresh-токенов: {n}")
    db.commit()
    return AccountWithPasswordOut(account=account_out(db, acc), password=password, revoked_tokens=n)


@router.patch("/{account_id}", response_model=AccountOut)
def set_active(account_id: uuid.UUID, body: AccountPatchIn, request: Request,
               db: Session = Depends(get_db), principal: Principal = Depends(admin_only)):
    acc = _get(db, account_id)
    if acc.is_active == body.is_active:
        return account_out(db, acc)
    if body.is_active and (acc.staff is None or acc.staff.is_deleted):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Нельзя активировать аккаунт удалённого медработника")
    acc.is_active = body.is_active
    if body.is_active:
        message = f"Аккаунт {acc.username} [{acc.id}] активирован"
    else:
        n = revoke_all(db, "user", acc.id, "deactivated")
        message = f"Аккаунт {acc.username} [{acc.id}] деактивирован; отозвано refresh-токенов: {n}"
    audit.write(db, action="account_updated", principal=principal, request=request, message=message)
    db.commit()
    return account_out(db, acc)
