"""Add VISO ownership, imaging sessions, object metadata, and annotations.

The shared database already contains patients, patient_profiles and captures.
This migration references those tables and creates separate VISO-owned tables;
it does not alter or remove their existing data.
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_patient_imaging"
down_revision = "0002_create_auth_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patient_access",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("patient_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("examination", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.patient_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "patient_id", name="uq_patient_access_owner_patient"),
    )
    op.create_index("ix_patient_access_owner_id", "patient_access", ["owner_id"], unique=False)
    op.create_index("ix_patient_access_patient_id", "patient_access", ["patient_id"], unique=False)

    op.create_table(
        "imaging_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("patient_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.patient_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_imaging_sessions_owner_id", "imaging_sessions", ["owner_id"], unique=False)
    op.create_index("ix_imaging_sessions_patient_id", "imaging_sessions", ["patient_id"], unique=False)

    op.create_table(
        "stored_captures",
        sa.Column("capture_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("client_capture_id", sa.String(length=80), nullable=False),
        sa.Column("patient_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("original_name", sa.String(length=200), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.patient_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["imaging_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("capture_id"),
        sa.UniqueConstraint("owner_id", "client_capture_id", name="uq_stored_capture_owner_client_id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_stored_captures_owner_id", "stored_captures", ["owner_id"], unique=False)
    op.create_index("ix_stored_captures_patient_id", "stored_captures", ["patient_id"], unique=False)
    op.create_index("ix_stored_captures_session_id", "stored_captures", ["session_id"], unique=False)

    op.create_table(
        "annotations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("capture_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("x2", sa.Float(), nullable=True),
        sa.Column("y2", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["capture_id"], ["stored_captures.capture_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["imaging_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_annotations_owner_id", "annotations", ["owner_id"], unique=False)
    op.create_index("ix_annotations_session_id", "annotations", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_annotations_session_id", table_name="annotations")
    op.drop_index("ix_annotations_owner_id", table_name="annotations")
    op.drop_table("annotations")
    op.drop_index("ix_stored_captures_session_id", table_name="stored_captures")
    op.drop_index("ix_stored_captures_patient_id", table_name="stored_captures")
    op.drop_index("ix_stored_captures_owner_id", table_name="stored_captures")
    op.drop_table("stored_captures")
    op.drop_index("ix_imaging_sessions_patient_id", table_name="imaging_sessions")
    op.drop_index("ix_imaging_sessions_owner_id", table_name="imaging_sessions")
    op.drop_table("imaging_sessions")
    op.drop_index("ix_patient_access_patient_id", table_name="patient_access")
    op.drop_index("ix_patient_access_owner_id", table_name="patient_access")
    op.drop_table("patient_access")
