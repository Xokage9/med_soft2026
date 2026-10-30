from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import audit
from .db import get_db
from .security.permissions import Perm
from .security.tokens import Principal, TokenError, decode_access

_bearer = HTTPBearer(auto_error=False)


def get_principal(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Principal:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется вход",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        return decode_access(creds.credentials)
    except TokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Недействительный токен: {e}",
                            headers={"WWW-Authenticate": "Bearer"}) from e


def require(perm: Perm):
    def dependency(request: Request, principal: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)) -> Principal:
        if not principal.can(perm):
            audit.write(db, action="access_denied", principal=principal, request=request,
                        message=f"Отказ в доступе: {request.method} {request.url.path} "
                                f"(нужно право {perm.value}, роль {principal.role})")
            db.commit()
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для операции")
        return principal
    return dependency


def require_staff(perm: Perm):
    def dependency(principal: Principal = Depends(require(perm))) -> Principal:
        if principal.kind != "user" or principal.staff_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Операция доступна только медработнику")
        return principal
    return dependency
