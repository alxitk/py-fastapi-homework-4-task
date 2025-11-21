from email.header import Header

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config.dependencies import get_jwt_auth_manager
from exceptions import TokenExpiredError, InvalidTokenError

security = HTTPBearer()

async def get_current_user_optional(
    authorization: str | None = Header(None),
):
    """
    Возвращает:
    - UserModel — если токен валиден
    - "missing" — если заголовка нет
    - "invalid_header" — если формат не Bearer
    - "invalid_token" — если токен невалидный или истёк
    """

    if authorization is None:
        return "missing"

    parts = authorization.split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        return "invalid_header"

    token = parts[1]

    try:
        payload = decode_access_token(token)  # твоя функция
    except Exception:
        return "invalid_token"

    user = await get_user_from_payload(payload)  # твоя функция

    return user