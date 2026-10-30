"""Comments stored in the existing patient_profiles table."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PatientProfile(Base):
    __tablename__ = "patient_profiles"

    patient_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("patients.patient_id", ondelete="CASCADE"), primary_key=True
    )
    comments: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
