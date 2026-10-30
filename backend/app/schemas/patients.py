"""Patient and examination request/response validation."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from typing_extensions import Annotated


PatientKey = Annotated[str, StringConstraints(
    min_length=1, max_length=64, strip_whitespace=True, pattern=r"^[A-Za-z0-9._-]+$"
)]


class PatientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: PatientKey
    patient_name: str = Field(min_length=1, max_length=200)
    age: int | None = Field(default=None, ge=0, le=125)
    examination: str = Field(default="Ophthalmic Examination", min_length=1, max_length=160)

    @field_validator("patient_name", "examination")
    @classmethod
    def require_nonblank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank.")
        return value


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patient_id: str
    patient_name: str
    age: int | None
    examination: str
    status: Literal["active", "inactive", "archived"]
    created_at: datetime


class AnnotationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["marker", "text", "line"]
    x: float = Field(ge=0, le=1000, allow_inf_nan=False)
    y: float = Field(ge=0, le=600, allow_inf_nan=False)
    x2: float | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    y2: float | None = Field(default=None, ge=0, le=600, allow_inf_nan=False)
    note: str | None = Field(default=None, max_length=1000)


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID | None = None
    comments: str = Field(default="", max_length=20_000)
    annotations: list[AnnotationInput] = Field(default_factory=list, max_length=500)


class SessionResponse(BaseModel):
    id: UUID
    patient_id: str
    status: str
    comments: str
    started_at: datetime


class CaptureResponse(BaseModel):
    id: UUID
    image_id: UUID
    patient_id: str
    image_url: str
    created_at: datetime
    kind: Literal["image", "video"]
    content_type: str
    size_bytes: int
    deletable: bool = True


class UploadCaptureResponse(CaptureResponse):
    session_id: UUID


class SavedProfileResponse(BaseModel):
    session_id: UUID
    comments: str
    captures: list[CaptureResponse]
    saved: bool = True


class ProfileResponse(BaseModel):
    patient: PatientResponse
    session_id: UUID | None
    comments: str
    captures: list[CaptureResponse]
    annotations: list[AnnotationInput]


class DownloadResponse(BaseModel):
    url: str
