import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
import secrets
import time
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.db import get_db

security = HTTPBearer(auto_error=False)
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7
PASSWORD_ITERATIONS = 210_000
VALID_ROLES = {"admin", "editor", "viewer"}


@dataclass(frozen=True)
class AuthUser:
    username: str
    role: str


def _sign(payload: str) -> str:
    return hmac.new(settings.app_token_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")
    return f"{payload_b64}.{_sign(payload_b64)}"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PASSWORD_ITERATIONS).hex()
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected = password_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations_text)).hex()
    return hmac.compare_digest(digest, expected)


def ensure_user_schema(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS app_users (
                id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
                username text NOT NULL UNIQUE,
                password_hash text NOT NULL,
                role text NOT NULL DEFAULT 'viewer',
                is_active boolean NOT NULL DEFAULT true,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                CONSTRAINT app_users_role_check CHECK (role IN ('admin', 'editor', 'viewer'))
            )
            """
        )
    )
    db.commit()


def bootstrap_admin_user(db: Session) -> None:
    ensure_user_schema(db)
    existing = db.scalar(select(models.AppUser).where(models.AppUser.username == settings.app_username))
    if existing:
        return
    user = models.AppUser(
        username=settings.app_username,
        password_hash=hash_password(settings.app_password),
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()


def verify_token(db: Session, token: str) -> AuthUser:
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.") from exc
    expected_signature = _sign(payload_b64)
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    if payload.get("exp", 0) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired.")
    username = str(payload.get("sub"))
    user = db.scalar(select(models.AppUser).where(models.AppUser.username == username, models.AppUser.is_active.is_(True)))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not active.")
    return AuthUser(username=user.username, role=user.role)


def require_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Session = Depends(get_db),
) -> AuthUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return verify_token(db, credentials.credentials)


def require_editor(user: AuthUser = Depends(require_user)) -> AuthUser:
    if user.role not in {"admin", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editor permissions required.")
    return user


def require_admin(user: AuthUser = Depends(require_user)) -> AuthUser:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin permissions required.")
    return user


def authenticate(db: Session, username: str, password: str) -> str | None:
    user = db.scalar(select(models.AppUser).where(models.AppUser.username == username, models.AppUser.is_active.is_(True)))
    if user and verify_password(password, user.password_hash):
        return create_token(username)
    return None


def list_users(db: Session) -> list[models.AppUser]:
    return db.scalars(select(models.AppUser).order_by(models.AppUser.username)).all()


def create_user(db: Session, username: str, password: str, role: str, is_active: bool = True) -> models.AppUser:
    if role not in VALID_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role.")
    existing = db.scalar(select(models.AppUser).where(models.AppUser.username == username))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists.")
    user = models.AppUser(username=username, password_hash=hash_password(password), role=role, is_active=is_active)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    username: str,
    role: str | None = None,
    is_active: bool | None = None,
    password: str | None = None,
) -> models.AppUser:
    user = db.scalar(select(models.AppUser).where(models.AppUser.username == username))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if role is not None:
        if role not in VALID_ROLES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role.")
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    if password:
        user.password_hash = hash_password(password)
    db.commit()
    db.refresh(user)
    return user
