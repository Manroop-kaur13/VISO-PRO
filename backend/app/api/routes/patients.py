"""Protected patient, imaging-session, capture and annotation APIs."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.db.models import (
    Annotation,
    ImagingSession,
    Patient,
    PatientAccess,
    PatientProfile,
    StoredCapture,
    User,
)
from app.db.session import get_db
from app.schemas.patients import (
    AnnotationInput,
    CaptureResponse,
    DownloadResponse,
    PatientCreate,
    PatientResponse,
    ProfileResponse,
    ProfileUpdate,
    SavedProfileResponse,
    SessionResponse,
    UploadCaptureResponse,
)
from app import storage

router = APIRouter(prefix="/api", tags=["patients and imaging"])
IMAGE_LIMIT_BYTES = 15 * 1024 * 1024
VIDEO_LIMIT_BYTES = 25 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ("jpg", "image"),
    "image/png": ("png", "image"),
    "image/webp": ("webp", "image"),
    "video/webm": ("webm", "video"),
    "video/mp4": ("mp4", "video"),
}


def _get_access(patient_id: str, user: User, db: Session) -> tuple[Patient, PatientAccess]:
    row = db.execute(
        select(Patient, PatientAccess)
        .join(PatientAccess, PatientAccess.patient_id == Patient.patient_id)
        .where(Patient.patient_id == patient_id, PatientAccess.owner_id == user.id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Patient record not found.")
    return row[0], row[1]


def _patient_response(patient: Patient, access: PatientAccess) -> PatientResponse:
    return PatientResponse(
        patient_id=patient.patient_id,
        patient_name=patient.patient_name,
        age=patient.age,
        examination=access.examination,
        status=access.status,
        created_at=patient.created_at,
    )


def _get_session(session_id: UUID, patient: Patient, user: User, db: Session) -> ImagingSession:
    imaging_session = db.scalar(
        select(ImagingSession).where(
            ImagingSession.id == session_id,
            ImagingSession.patient_id == patient.patient_id,
            ImagingSession.owner_id == user.id,
        )
    )
    if imaging_session is None:
        raise HTTPException(status_code=404, detail="Imaging session not found.")
    return imaging_session


def _new_session(patient: Patient, user: User, db: Session) -> ImagingSession:
    imaging_session = ImagingSession(patient_id=patient.patient_id, owner_id=user.id)
    db.add(imaging_session)
    db.flush()
    return imaging_session


def _stored_capture_response(asset: StoredCapture, patient_id: str) -> CaptureResponse:
    try:
        url = storage.signed_download_url(asset.storage_key)
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail="Image storage is unavailable.") from exc
    return CaptureResponse(
        id=asset.capture_id,
        image_id=asset.capture_id,
        patient_id=patient_id,
        image_url=url,
        created_at=asset.captured_at,
        kind=asset.kind,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        deletable=True,
    )


def _all_capture_responses(patient: Patient, user: User, db: Session) -> list[CaptureResponse]:
    stored = db.scalars(
        select(StoredCapture)
        .where(StoredCapture.patient_id == patient.patient_id, StoredCapture.owner_id == user.id)
        .order_by(StoredCapture.captured_at.desc())
    ).all()
    # Legacy URL-only rows remain in PostgreSQL but are excluded because they
    # carry no verifiable private-delivery metadata.
    results = [_stored_capture_response(item, patient.patient_id) for item in stored]
    return sorted(results, key=lambda item: item.created_at, reverse=True)


def _annotation_response(annotation: Annotation) -> AnnotationInput:
    return AnnotationInput(
        kind=annotation.kind,
        x=annotation.x,
        y=annotation.y,
        x2=annotation.x2,
        y2=annotation.y2,
        note=annotation.note,
    )


@router.get("/patients", response_model=list[PatientResponse])
def list_patients(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[PatientResponse]:
    rows = db.execute(
        select(Patient, PatientAccess)
        .join(PatientAccess, PatientAccess.patient_id == Patient.patient_id)
        .where(PatientAccess.owner_id == user.id)
        .order_by(Patient.patient_name)
    ).all()
    return [_patient_response(patient, access) for patient, access in rows]


@router.post("/patients", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def create_patient(
    body: PatientCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientResponse:
    patient = Patient(
        patient_id=body.patient_id,
        patient_name=body.patient_name.strip(),
        age=body.age,
    )
    access = PatientAccess(
        patient_id=body.patient_id,
        owner_id=user.id,
        examination=body.examination.strip(),
        status="active",
    )
    db.add_all([patient, access])
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A patient with this ID already exists in the shared database.",
        ) from exc
    db.refresh(patient)
    return _patient_response(patient, access)


@router.get("/patients/{patient_id}/sessions", response_model=list[SessionResponse])
def list_sessions(
    patient_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SessionResponse]:
    patient, _ = _get_access(patient_id, user, db)
    sessions = db.scalars(
        select(ImagingSession)
        .where(ImagingSession.patient_id == patient.patient_id, ImagingSession.owner_id == user.id)
        .order_by(ImagingSession.started_at.desc())
    ).all()
    return [
        SessionResponse(
            id=item.id,
            patient_id=patient.patient_id,
            status=item.status,
            comments=item.notes,
            started_at=item.started_at,
        )
        for item in sessions
    ]


@router.get("/patients/{patient_id}/profile", response_model=ProfileResponse)
def get_profile(
    patient_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileResponse:
    patient, access = _get_access(patient_id, user, db)
    profile = db.get(PatientProfile, patient.patient_id)
    imaging_session = db.scalar(
        select(ImagingSession)
        .where(ImagingSession.patient_id == patient.patient_id, ImagingSession.owner_id == user.id)
        .order_by(ImagingSession.started_at.desc())
    )
    annotations: list[Annotation] = []
    if imaging_session is not None:
        annotations = db.scalars(
            select(Annotation).where(
                Annotation.session_id == imaging_session.id, Annotation.owner_id == user.id
            )
        ).all()
    return ProfileResponse(
        patient=_patient_response(patient, access),
        session_id=imaging_session.id if imaging_session else None,
        comments=profile.comments if profile else (imaging_session.notes if imaging_session else ""),
        captures=_all_capture_responses(patient, user, db),
        annotations=[_annotation_response(item) for item in annotations],
    )


@router.put("/patients/{patient_id}/profile", response_model=SavedProfileResponse)
def save_profile(
    patient_id: str,
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedProfileResponse:
    patient, _ = _get_access(patient_id, user, db)
    imaging_session = (
        _get_session(body.session_id, patient, user, db)
        if body.session_id
        else _new_session(patient, user, db)
    )
    imaging_session.notes = body.comments
    profile = db.get(PatientProfile, patient.patient_id)
    if profile is None:
        db.add(PatientProfile(patient_id=patient.patient_id, comments=body.comments))
    else:
        profile.comments = body.comments
    db.execute(delete(Annotation).where(Annotation.session_id == imaging_session.id, Annotation.owner_id == user.id))
    for item in body.annotations:
        db.add(
            Annotation(
                session_id=imaging_session.id,
                owner_id=user.id,
                kind=item.kind,
                x=item.x,
                y=item.y,
                x2=item.x2,
                y2=item.y2,
                note=item.note,
            )
        )
    db.commit()
    return SavedProfileResponse(
        session_id=imaging_session.id,
        comments=body.comments,
        captures=_all_capture_responses(patient, user, db),
    )


@router.post(
    "/patients/{patient_id}/captures",
    response_model=UploadCaptureResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_capture(
    patient_id: str,
    file: UploadFile = File(...),
    client_capture_id: str = Form(min_length=1, max_length=80),
    session_id: UUID | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadCaptureResponse:
    patient, _ = _get_access(patient_id, user, db)
    existing = db.scalar(
        select(StoredCapture).where(
            StoredCapture.owner_id == user.id,
            StoredCapture.client_capture_id == client_capture_id,
        )
    )
    if existing is not None:
        if existing.patient_id != patient.patient_id:
            raise HTTPException(status_code=409, detail="Capture ID is already in use.")
        response = _stored_capture_response(existing, patient.patient_id)
        return UploadCaptureResponse(**response.model_dump(), session_id=existing.session_id)

    detected_type = (file.content_type or "").lower().split(";")[0].strip()
    type_info = ALLOWED_CONTENT_TYPES.get(detected_type)
    if type_info is None:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG, WebP, WebM, and MP4 files are allowed.")
    extension, media_kind = type_info
    maximum = IMAGE_LIMIT_BYTES if media_kind == "image" else VIDEO_LIMIT_BYTES
    contents = file.file.read(maximum + 1)
    if not contents:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    if len(contents) > maximum:
        raise HTTPException(status_code=413, detail="Uploaded file exceeds the allowed size.")
    if not _content_matches_type(contents, detected_type):
        raise HTTPException(status_code=415, detail="File content does not match its declared type.")
    if not storage.storage_is_configured():
        raise HTTPException(status_code=503, detail="Image storage is not configured.")

    imaging_session = _get_session(session_id, patient, user, db) if session_id else _new_session(patient, user, db)
    capture_id = uuid4()
    object_key = f"records/{imaging_session.id}/{capture_id}.{extension}"
    now = datetime.now(timezone.utc)
    try:
        storage_key = storage.put_object(object_key, contents, detected_type)
        asset = StoredCapture(
            capture_id=capture_id,
            client_capture_id=client_capture_id,
            session_id=imaging_session.id,
            patient_id=patient.patient_id,
            owner_id=user.id,
            storage_key=storage_key,
            content_type=detected_type,
            original_name=f"capture_{capture_id}.{extension}",
            size_bytes=len(contents),
            kind=media_kind,
            captured_at=now,
            created_at=now,
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
    except storage.StorageError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Image storage is unavailable.") from exc
    except IntegrityError as exc:
        db.rollback()
        try:
            storage.delete_object(storage_key)
        except storage.StorageError:
            pass
        raise HTTPException(status_code=409, detail="Capture ID is already in use.") from exc
    except Exception:
        db.rollback()
        try:
            storage.delete_object(storage_key)
        except storage.StorageError:
            pass
        raise
    response = _stored_capture_response(asset, patient.patient_id)
    return UploadCaptureResponse(**response.model_dump(), session_id=imaging_session.id)


@router.get("/patients/{patient_id}/captures", response_model=list[CaptureResponse])
def list_captures(
    patient_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CaptureResponse]:
    patient, _ = _get_access(patient_id, user, db)
    return _all_capture_responses(patient, user, db)


@router.get("/patients/{patient_id}/captures/{image_id}/download", response_model=DownloadResponse)
def download_capture(
    patient_id: str,
    image_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DownloadResponse:
    patient, _ = _get_access(patient_id, user, db)
    asset = db.scalar(
        select(StoredCapture).where(
            StoredCapture.capture_id == image_id,
            StoredCapture.patient_id == patient.patient_id,
            StoredCapture.owner_id == user.id,
        )
    )
    if asset is None:
        # Legacy URL-only rows cannot be proven private, so they are intentionally
        # not downloadable through this endpoint.
        raise HTTPException(status_code=404, detail="Capture not found.")
    try:
        url = storage.signed_download_url(asset.storage_key, as_attachment=True)
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail="Image storage is unavailable.") from exc
    return DownloadResponse(url=url)


@router.delete("/patients/{patient_id}/captures/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_capture(
    patient_id: str,
    image_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    patient, _ = _get_access(patient_id, user, db)
    asset = db.scalar(
        select(StoredCapture).where(
            StoredCapture.capture_id == image_id,
            StoredCapture.patient_id == patient.patient_id,
            StoredCapture.owner_id == user.id,
        )
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Capture not found.")
    storage_key = asset.storage_key
    try:
        storage.delete_object(storage_key)
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail="Image storage is unavailable; the capture record was retained.") from exc
    db.delete(asset)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _content_matches_type(contents: bytes, content_type: str) -> bool:
    if content_type == "image/jpeg":
        return contents.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return contents.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(contents) >= 12 and contents[:4] == b"RIFF" and contents[8:12] == b"WEBP"
    if content_type == "video/webm":
        return contents.startswith(b"\x1a\x45\xdf\xa3")
    if content_type == "video/mp4":
        return len(contents) >= 12 and contents[4:8] == b"ftyp"
    return False
