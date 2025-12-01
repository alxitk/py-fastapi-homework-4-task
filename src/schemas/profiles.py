from datetime import date
from fastapi import Form, UploadFile, File
from pydantic import BaseModel, field_validator, HttpUrl
from validation import validate_name, validate_gender, validate_birth_date


class ProfileRequestSchema(BaseModel):
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: UploadFile

    @field_validator("first_name")
    def validate_first_name(cls, value):
        return validate_name(value)

    @field_validator("last_name")
    def validate_last_name(cls, value):
        return validate_name(value)

    @field_validator("gender")
    def validate_gender_field(cls, value):
        return validate_gender(value)

    @field_validator("date_of_birth")
    def validate_date_of_birth(cls, value):
        return validate_birth_date(value)

    @field_validator("info")
    def validate_info(cls, value):
        if not value.strip():
            raise ValueError("Info cannot be empty")
        return value


    @classmethod
    def as_form(
        cls,
        first_name: str = Form(...),
        last_name: str = Form(...),
        gender: str = Form(...),
        date_of_birth: date = Form(...),
        info: str = Form(...),
        avatar: UploadFile = File(...),
    ):
        return cls(
            first_name=first_name,
            last_name=last_name,
            gender=gender,
            date_of_birth=date_of_birth,
            info=info,
            avatar=avatar,
        )


class ProfileResponseSchema(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: str