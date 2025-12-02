from fastapi import APIRouter, status, HTTPException, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.models.accounts import UserProfileModel, UserModel
from database import get_db
from config.dependencies import get_s3_storage_client, get_jwt_auth_manager
from security.http import get_token
from storages import S3StorageInterface
from exceptions import TokenExpiredError, InvalidTokenError
from schemas.profiles import ProfileRequestSchema, ProfileResponseSchema

router = APIRouter()


@router.post("/users/{user_id}/profile/", response_model=ProfileResponseSchema,
             status_code=status.HTTP_201_CREATED)
async def create_profile(
    user_id: int,
    form: ProfileRequestSchema = Depends(ProfileRequestSchema.as_form),
    avatar: UploadFile = File(...),
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_db),
    s3_client: S3StorageInterface = Depends(get_s3_storage_client),
    jwt_manager=Depends(get_jwt_auth_manager),
):
    try:
        payload = jwt_manager.decode_access_token(token)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id_from_token = payload.get("user_id")
    if not user_id_from_token:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id_from_token = int(user_id_from_token)

    result = await db.execute(
        select(UserModel).where(UserModel.id == user_id_from_token)
    )
    current_user = result.scalar_one_or_none()

    if not current_user or not current_user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    target_user_result = await db.execute(
        select(UserModel).where(UserModel.id == user_id)
    )
    target_user = target_user_result.scalar_one_or_none()

    if not target_user or not target_user.is_active:
        raise HTTPException(
            status_code=401,
            detail="User not found or not active."
        )

    is_admin = current_user.group_id == 3
    if not is_admin and current_user.id != user_id:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to edit this profile."
        )

    result = await db.execute(
        select(UserProfileModel).where(UserProfileModel.user_id == user_id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="User already has a profile."
        )

    avatar_key = f"avatars/{user_id}_{avatar.filename}"
    try:
        avatar.file.seek(0)
        await s3_client.upload_file(avatar_key, avatar.file)
        avatar_url = await s3_client.get_file_url(avatar_key)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to upload avatar. Please try again later."
        )

    profile = UserProfileModel(
        user_id=user_id,
        first_name=form.first_name,
        last_name=form.last_name,
        gender=form.gender,
        date_of_birth=form.date_of_birth,
        info=form.info.strip(),
        avatar=avatar_key,
    )

    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    return ProfileResponseSchema(
        id=profile.id,
        user_id=user_id,
        first_name=form.first_name,
        last_name=form.last_name,
        gender=form.gender,
        date_of_birth=form.date_of_birth,
        info=form.info.strip(),
        avatar=avatar_url,
    )
