from fastapi import APIRouter, status, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models.accounts import UserProfileModel, UserModel
from database import get_db
from config.dependencies import get_s3_storage_client, get_jwt_auth_manager
from security.http import get_token
from storages import S3StorageInterface
from exceptions import TokenExpiredError, InvalidTokenError

router = APIRouter()


@router.post(
    "/users/{user_id}/profile/",
    status_code=status.HTTP_201_CREATED,
)
async def create_profile(
    user_id: int,

    # ⬇⬇⬇ САМЫЙ ВАЖНЫЙ МОМЕНТ — multipart/form-data, НЕ pydantic
    first_name: str = Form(...),
    last_name: str = Form(...),
    gender: str = Form(...),
    date_of_birth: str = Form(...),
    info: str = Form(...),
    avatar: UploadFile = File(...),

    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_db),
    s3_client: S3StorageInterface = Depends(get_s3_storage_client),
    jwt_manager=Depends(get_jwt_auth_manager),
):
    # 1) Декодирование токена
    try:
        payload = jwt_manager.decode_access_token(token)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    current_user_id = payload.get("sub")
    if current_user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    result = await db.execute(select(UserModel).where(UserModel.id == current_user_id))
    current_user = result.scalar_one_or_none()

    if not current_user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # 2) Существование user_id
    result = await db.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or not active.")

    # 3) Проверка прав
    if not getattr(current_user, "is_admin", False) and current_user.id != user_id:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to edit this profile."
        )

    # 4) Проверка существования профиля
    result = await db.execute(
        select(UserProfileModel).where(UserProfileModel.user_id == user_id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400, detail="User already has a profile."
        )

    # 5) Загрузка аватара
    avatar_key = f"avatars/{user_id}_{avatar.filename}"
    try:
        await s3_client.upload_file(avatar_key, avatar.file)
        avatar_url = await s3_client.get_file_url(avatar_key)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to upload avatar. Please try again later."
        )

    # 6) Создание профиля
    profile = UserProfileModel(
        user_id=user_id,
        first_name=first_name.lower(),
        last_name=last_name.lower(),
        gender=gender,
        date_of_birth=date_of_birth,
        info=info,
        avatar=avatar_key,
    )

    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    return {
        "id": profile.id,
        "user_id": user_id,
        "first_name": profile.first_name,
        "last_name": profile.last_name,
        "gender": profile.gender,
        "date_of_birth": profile.date_of_birth,
        "info": profile.info,
        "avatar": avatar_url,
    }