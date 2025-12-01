from fastapi import APIRouter, status, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import date

from database.models.accounts import UserProfileModel, UserModel
from database import get_db
from config.dependencies import get_s3_storage_client, get_jwt_auth_manager
from security.http import get_token
from storages import S3StorageInterface
from exceptions import TokenExpiredError, InvalidTokenError
from schemas.profiles import ProfileResponseSchema
from validation import validate_name, validate_gender, validate_birth_date, validate_image

router = APIRouter()


@router.post("/users/{user_id}/profile/", status_code=status.HTTP_201_CREATED)
async def create_profile(
        user_id: int,
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
    try:
        payload = jwt_manager.decode_access_token(token)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id_from_token = payload.get("user_id")
    if user_id_from_token is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    try:
        user_id_from_token = int(user_id_from_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    result = await db.execute(
        select(UserModel).where(UserModel.id == user_id_from_token)
    )
    current_user = result.scalar_one_or_none()

    if not current_user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if not current_user.is_active:
        raise HTTPException(status_code=401, detail="User account is inactive")

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
        raise HTTPException(status_code=400, detail="User already has a profile.")

    try:
        validated_first_name = validate_name(first_name)
        validated_last_name = validate_name(last_name)
        validated_gender = validate_gender(gender)

        try:
            parsed_date = date.fromisoformat(date_of_birth)
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD")

        validated_date = validate_birth_date(parsed_date)

        if not info.strip():
            raise ValueError("Info cannot be empty")

        validate_image(avatar)

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    avatar_key = f"avatars/{user_id}_{avatar.filename}"
    try:
        avatar.file.seek(0)
        await s3_client.upload_file(avatar_key, avatar.file)
        avatar_url = await s3_client.get_file_url(avatar_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to upload avatar.")

    profile = UserProfileModel(
        user_id=user_id,
        first_name=validated_first_name,
        last_name=validated_last_name,
        gender=validated_gender,
        date_of_birth=validated_date,
        info=info.strip(),
        avatar=avatar_key,
    )

    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    return ProfileResponseSchema(
        id=profile.id,
        user_id=user_id,
        first_name=validated_first_name,
        last_name=validated_last_name,
        gender=validated_gender,
        date_of_birth=validated_date,
        info=info.strip(),
        avatar=avatar_url,
    )