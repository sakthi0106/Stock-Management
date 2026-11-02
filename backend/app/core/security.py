"""
Security and Authentication Helpers
- Password hashing using HMAC-SHA256 with salt / hashlib
- JWT token encode/decode
- Role-based authorization
"""
import os
import hashlib
import hmac
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from fastapi import HTTPException, status, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

security_bearer = HTTPBearer(auto_error=False)

class UserRole:
    DIRECTOR = "DIRECTOR"
    PURCHASE_TEAM = "PURCHASE_TEAM"
    ADMIN = "ADMIN"
    ALL = [DIRECTOR, PURCHASE_TEAM, ADMIN]


def normalize_role(role: Optional[str]) -> Optional[str]:
    """Normalize role strings to canonical application values."""
    if role is None:
        return None
    normalized = str(role).strip().upper()
    aliases = {
        "PURCHASE": UserRole.PURCHASE_TEAM,
        "PURCHASE_TEAM": UserRole.PURCHASE_TEAM,
        "PURCHASE-TEAM": UserRole.PURCHASE_TEAM,
        "DIRECTOR": UserRole.DIRECTOR,
        "ADMIN": UserRole.ADMIN,
    }
    candidate = aliases.get(normalized, normalized)
    return candidate if candidate in UserRole.ALL else None

def hash_password(password: str) -> str:
    """Hash password using salt and SHA-256 for secure, robust standalone hashing without external C binary issues."""
    salt = os.urandom(16).hex()
    hashed = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return f"{salt}${hashed}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against salt$hash string."""
    try:
        parts = hashed_password.split("$")
        if len(parts) != 2:
            return False
        salt, expected_hash = parts
        calc_hash = hashlib.sha256((salt + plain_password).encode('utf-8')).hexdigest()
        return hmac.compare_digest(expected_hash, calc_hash)
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again."
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token."
        )

def require_roles(allowed_roles: list[str]):
    """Role-based access control dependency factory."""
    def role_checker(credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)):
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required."
            )
        token = credentials.credentials
        payload = decode_access_token(token)
        user_role = normalize_role(payload.get("role"))
        normalized_allowed = [normalize_role(role) for role in allowed_roles]
        if user_role not in normalized_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role in {allowed_roles}, your role is {payload.get('role')}."
            )
        payload["role"] = user_role
        return payload
    return role_checker
