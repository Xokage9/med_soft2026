import hashlib
import hmac
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import get_principal
from ..models import AdminAccount, RefreshToken, UserAccount, utcnow
from ..schemas import (
    AdminLoginIn, LoginIn, MeOut, RefreshIn, SetupBeginIn, SetupBeginOut, SetupCompleteIn,
    TokenPairOut,
)
from ..security import passwords, totp
from ..security.permissions import ADMIN_ROLE, permissions_for
from ..security.tokens import Principal, TokenError, decode_refresh, issue_pair, revoke_all

router = APIRouter(prefix="/api/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = "Неверные учётные данные или аккаунт неактивен"


def _me(kind: str, sid: uuid.UUID, username: str, role: str, staff_id, name: str) -> MeOut:
    return MeOut(kind=kind, id=sid, username=username, role=role, staff_id=staff_id, name=name,
                 permissions=sorted(p.value for p in permissions_for(role)))


def _pair_for_user(db: Session, acc: UserAccount) -> TokenPairOut:
    staff = acc.staff
    me = _me("user", acc.id, acc.username, staff.role.value, staff.id, staff.display_name)
    pair = issue_pair(db, kind="user", subject_id=acc.id, username=acc.username,
                      role=me.role, staff_id=staff.id, name=me.name)
    return TokenPairOut(**pair, me=me)


def _pair_for_admin(db: Session, admin: AdminAccount) -> TokenPairOut:
    me = _me("admin", admin.id, admin.username, ADMIN_ROLE, None, "Администратор")
    pair = issue_pair(db, kind="admin", subject_id=admin.id, username=admin.username,
                      role=ADMIN_ROLE, staff_id=None, name=me.name)
    return TokenPairOut(**pair, me=me)


def _user_unusable_reason(acc: UserAccount | None) -> str | None:
    if acc is None:
        return "аккаунт не найден"
    if not acc.is_active:
        return "аккаунт деактивирован"
    if acc.staff is None or acc.staff.is_deleted:
        return "аккаунт не связан с действующим медработником"
    return None


def _get_admin(db: Session) -> AdminAccount | None:
    return db.scalar(select(AdminAccount))


@router.post("/login", response_model=TokenPairOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    acc = db.scalar(select(UserAccount).where(UserAccount.username == body.username))
    password_ok = passwords.verify_password(acc.password_hash if acc else None, body.password)
    if acc is None:
        reason = "неизвестный логин"
    elif not password_ok:
        reason = "неверный пароль"
    else:
        reason = _user_unusable_reason(acc)

    if reason:
        audit.write(db, action="login_failed", request=request,
                    message=f"Неуспешный вход пользователя «{body.username}»: {reason}")
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_LOGIN_ERROR)

    if passwords.needs_rehash(acc.password_hash):
        acc.password_hash = passwords.hash_password(body.password)
    pair = _pair_for_user(db, acc)
    audit.write(db, action="login", request=request, actor=f"user:{acc.id}",
                actor_name=f"{acc.username} ({acc.staff.role.value})",
                message=f"Вход пользователя {acc.username}: {acc.staff.display_name}, "
                        f"роль {acc.staff.role.value}")
    db.commit()
    return pair


@router.get("/admin/status")
def admin_status(db: Session = Depends(get_db)):
    admin = _get_admin(db)
    return {"configured": bool(admin and admin.is_configured)}


@router.post("/admin/setup/begin", response_model=SetupBeginOut)
def admin_setup_begin(body: SetupBeginIn, request: Request, db: Session = Depends(get_db)):
    admin = _get_admin(db)
    if admin and admin.is_configured:
        raise HTTPException(status.HTTP_409_CONFLICT, "Администратор уже настроен")
    if body.password != body.password_confirm:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Пароли не совпадают")
    if err := passwords.check_admin_password_policy(body.password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, err)

    if admin is None:
        admin = AdminAccount()
        db.add(admin)
    secret = totp.new_secret()
    setup_id = secrets.token_urlsafe(32)
    admin.pending_password_hash = passwords.hash_password(body.password)
    admin.pending_totp_secret = secret
    admin.pending_setup_nonce_hash = hashlib.sha256(setup_id.encode()).hexdigest()
    audit.write(db, action="admin_setup_started", request=request,
                message="Начата первичная настройка администратора (пароль задан, ожидается TOTP)")
    db.commit()

    uri = totp.provisioning_uri(secret, admin.username)
    return SetupBeginOut(setup_id=setup_id, secret=secret, otpauth_uri=uri,
                         qr_data_url=totp.qr_svg_data_url(uri))


@router.post("/admin/setup/complete", response_model=TokenPairOut)
def admin_setup_complete(body: SetupCompleteIn, request: Request, db: Session = Depends(get_db)):
    admin = _get_admin(db)
    if admin is None or admin.is_configured or not admin.pending_totp_secret:
        raise HTTPException(status.HTTP_409_CONFLICT, "Нет незавершённой настройки")
    nonce_ok = hmac.compare_digest(
        hashlib.sha256(body.setup_id.encode()).hexdigest(), admin.pending_setup_nonce_hash or "")
    step = totp.verify(admin.pending_totp_secret, body.code) if nonce_ok else None
    if step is None:
        audit.write(db, action="admin_setup_failed", request=request,
                    message="Неверный код TOTP при первичной настройке администратора")
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный код подтверждения")

    admin.password_hash = admin.pending_password_hash
    admin.totp_secret = admin.pending_totp_secret
    admin.totp_last_step = step
    admin.is_configured = True
    admin.pending_password_hash = admin.pending_totp_secret = admin.pending_setup_nonce_hash = None
    pair = _pair_for_admin(db, admin)
    audit.write(db, action="admin_setup_completed", request=request, actor=f"admin:{admin.id}",
                actor_name="admin", message="Первичная настройка администратора завершена (TOTP включён)")
    audit.write(db, action="admin_login", request=request, actor=f"admin:{admin.id}",
                actor_name="admin", message="Вход администратора")
    db.commit()
    return pair


@router.post("/admin/login", response_model=TokenPairOut)
def admin_login(body: AdminLoginIn, request: Request, db: Session = Depends(get_db)):
    admin = _get_admin(db)
    if admin is None or not admin.is_configured:
        raise HTTPException(status.HTTP_409_CONFLICT, "Требуется первичная настройка администратора")

    reason = None
    if not passwords.verify_password(admin.password_hash, body.password):
        reason = "неверный пароль"
    else:
        step = totp.verify(admin.totp_secret, body.code, admin.totp_last_step)
        if step is None:
            reason = "неверный или уже использованный код TOTP"
    if reason:
        audit.write(db, action="login_failed", request=request,
                    message=f"Неуспешный вход администратора: {reason}")
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный пароль или код")

    admin.totp_last_step = step
    pair = _pair_for_admin(db, admin)
    audit.write(db, action="admin_login", request=request, actor=f"admin:{admin.id}",
                actor_name="admin", message="Вход администратора")
    db.commit()
    return pair


@router.post("/refresh", response_model=TokenPairOut)
def refresh(body: RefreshIn, request: Request, db: Session = Depends(get_db)):
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия истекла, войдите снова")
    try:
        claims = decode_refresh(body.refresh_token)
    except TokenError:
        raise unauthorized
    row = db.get(RefreshToken, uuid.UUID(claims["jti"]))
    if row is None:
        raise unauthorized

    if row.revoked_at is not None:
        if row.revoke_reason == "rotated":
            n = revoke_all(db, row.subject_kind, row.subject_id, "reuse_detected")
            audit.write(db, action="token_reuse_detected", request=request, actor=audit.SYSTEM_ACTOR,
                        message=f"Повторное использование refresh-токена субъекта "
                                f"{row.subject_kind}:{row.subject_id}; отозвано токенов: {n}")
            db.commit()
        raise unauthorized

    now = utcnow()
    res = db.execute(update(RefreshToken)
                     .where(RefreshToken.jti == row.jti, RefreshToken.revoked_at.is_(None))
                     .values(revoked_at=now, revoke_reason="rotated"))
    if res.rowcount != 1:
        raise unauthorized

    if row.subject_kind == "user":
        acc = db.get(UserAccount, row.subject_id)
        if _user_unusable_reason(acc):
            db.rollback()
            raise unauthorized
        pair = _pair_for_user(db, acc)
    else:
        admin = _get_admin(db)
        if admin is None or admin.id != row.subject_id:
            db.rollback()
            raise unauthorized
        pair = _pair_for_admin(db, admin)

    db.execute(update(RefreshToken).where(RefreshToken.jti == row.jti)
               .values(replaced_by=uuid.UUID(decode_refresh(pair.refresh_token)["jti"])))
    db.commit()
    return pair


@router.post("/logout", status_code=204)
def logout(body: RefreshIn, request: Request, db: Session = Depends(get_db)):
    try:
        claims = decode_refresh(body.refresh_token)
    except TokenError:
        return Response(status_code=204)
    row = db.get(RefreshToken, uuid.UUID(claims["jti"]))
    if row and row.revoked_at is None:
        row.revoked_at, row.revoke_reason = utcnow(), "logout"
        audit.write(db, action="logout", request=request,
                    actor=f"{row.subject_kind}:{row.subject_id}", message="Выход из системы")
        db.commit()
    return Response(status_code=204)


@router.get("/me", response_model=MeOut)
def me(principal: Principal = Depends(get_principal)):
    return _me(principal.kind, principal.id, principal.username, principal.role,
               principal.staff_id, principal.name)
