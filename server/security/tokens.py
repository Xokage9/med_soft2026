import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import RefreshToken, utcnow
from ..settings import settings
from .permissions import Perm, permissions_for

ALGORITHM = "EdDSA"


def _load_or_create_key() -> Ed25519PrivateKey:
    path = settings.jwt_private_key
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    return key


_private_key = _load_or_create_key()
_public_key = _private_key.public_key()


def public_key_pem() -> str:
    return _public_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


class TokenError(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    kind: str
    id: uuid.UUID
    username: str
    role: str
    staff_id: uuid.UUID | None
    name: str
    expires_at: datetime

    @property
    def actor(self) -> str:
        return f"{self.kind}:{self.id}"

    @property
    def permissions(self) -> frozenset[Perm]:
        return permissions_for(self.role)

    def can(self, perm: Perm) -> bool:
        return perm in self.permissions


def _encode(claims: dict) -> str:
    return jwt.encode(claims, _private_key, algorithm=ALGORITHM)


def _decode(token: str, expected_type: str) -> dict:
    try:
        claims = jwt.decode(
            token, _public_key, algorithms=[ALGORITHM], issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "jti", "typ", "iss"]})
    except jwt.ExpiredSignatureError as e:
        raise TokenError("token expired") from e
    except jwt.PyJWTError as e:
        raise TokenError("invalid token") from e
    if claims.get("typ") != expected_type:
        raise TokenError("wrong token type")
    return claims


def issue_pair(db: Session, *, kind: str, subject_id: uuid.UUID, username: str, role: str,
               staff_id: uuid.UUID | None, name: str) -> dict:
    now = utcnow()
    access_exp = now + settings.access_ttl
    refresh_exp = now + settings.refresh_ttl
    refresh_jti = uuid.uuid4()

    access = _encode({
        "iss": settings.jwt_issuer, "typ": "access", "sub": str(subject_id), "jti": str(uuid.uuid4()),
        "iat": now, "exp": access_exp,
        "kind": kind, "username": username, "role": role,
        "staff_id": str(staff_id) if staff_id else None, "name": name,
    })
    refresh = _encode({
        "iss": settings.jwt_issuer, "typ": "refresh", "sub": str(subject_id),
        "jti": str(refresh_jti), "iat": now, "exp": refresh_exp, "kind": kind,
    })
    db.add(RefreshToken(jti=refresh_jti, subject_kind=kind, subject_id=subject_id,
                        issued_at=now, expires_at=refresh_exp))
    db.flush()
    return {
        "access_token": access, "refresh_token": refresh, "token_type": "Bearer",
        "access_expires_at": access_exp.isoformat(), "refresh_expires_at": refresh_exp.isoformat(),
        "_refresh_jti": refresh_jti,
    }


def decode_access(token: str) -> Principal:
    c = _decode(token, "access")
    return Principal(
        kind=c["kind"], id=uuid.UUID(c["sub"]), username=c["username"], role=c["role"],
        staff_id=uuid.UUID(c["staff_id"]) if c.get("staff_id") else None, name=c.get("name", ""),
        expires_at=datetime.fromtimestamp(c["exp"], timezone.utc),
    )


def decode_refresh(token: str) -> dict:
    return _decode(token, "refresh")


def revoke_all(db: Session, kind: str, subject_id: uuid.UUID, reason: str) -> int:
    now = utcnow()
    result = db.execute(
        update(RefreshToken)
        .where(RefreshToken.subject_kind == kind, RefreshToken.subject_id == subject_id,
               RefreshToken.revoked_at.is_(None), RefreshToken.expires_at > now)
        .values(revoked_at=now, revoke_reason=reason)
    )
    return result.rowcount or 0


def active_refresh_count(db: Session, kind: str, subject_id: uuid.UUID) -> int:
    now = utcnow()
    return len(db.scalars(select(RefreshToken.jti).where(
        RefreshToken.subject_kind == kind, RefreshToken.subject_id == subject_id,
        RefreshToken.revoked_at.is_(None), RefreshToken.expires_at > now)).all())
