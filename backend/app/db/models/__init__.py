"""Import model classes here so Alembic can discover their tables."""

from app.db.models.user import User
from app.db.models.auth_session import AuthSession
from app.db.models.annotation import Annotation
from app.db.models.image_asset import LegacyCapture, StoredCapture
from app.db.models.imaging_session import ImagingSession
from app.db.models.patient import Patient
from app.db.models.patient_access import PatientAccess
from app.db.models.patient_profile import PatientProfile

__all__ = [
    "Annotation", "AuthSession", "ImagingSession", "LegacyCapture", "Patient",
    "PatientAccess", "PatientProfile", "StoredCapture", "User",
]
