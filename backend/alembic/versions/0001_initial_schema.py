from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "sources",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("canonical_url", sa.String(length=2048), nullable=False, unique=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("owner_subject", sa.String(length=255), nullable=False),
        sa.Column("owner_organization", sa.String(length=255), nullable=False),
        sa.Column("current_version_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema=None,
    )

    op.create_index(op.f("ix_sources_canonical_url"), "sources", ["canonical_url"], unique=True)

    op.create_table(
        "source_versions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_id", sa.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("change_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extracted_content_ref", sa.Text(), nullable=False),
        sa.Column("parse_status", sa.String(length=32), nullable=False),
        sa.CheckConstraint("parse_status IN ('interpretable', 'uninterpretable')", name="ck_source_versions_parse_status"),
        sa.UniqueConstraint("source_id", "content_fingerprint", name="uq_source_versions_source_fingerprint"),
    )
    op.create_index("ix_source_versions_source_id", "source_versions", ["source_id"])

    op.create_table(
        "source_approvals",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_version_id", sa.UUID(as_uuid=True), sa.ForeignKey("source_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("approver_subject", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disable_reason", sa.Text(), nullable=True),
        sa.Column("effective_context", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("effective_date_start", sa.Date(), nullable=True),
        sa.Column("effective_date_end", sa.Date(), nullable=True),
        sa.CheckConstraint("status IN ('candidate', 'pending_review', 'approved', 'disabled', 'rejected', 'superseded')", name="ck_source_approvals_status"),
        sa.CheckConstraint(
            "status != 'approved' OR (approver_subject IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_source_approvals_approved_fields",
        ),
        sa.CheckConstraint(
            "status != 'disabled' OR (disabled_at IS NOT NULL AND disable_reason IS NOT NULL)",
            name="ck_source_approvals_disabled_fields",
        ),
        sa.CheckConstraint(
            "effective_date_start IS NULL OR effective_date_end IS NULL "
            "OR effective_date_start <= effective_date_end",
            name="ck_source_approvals_effective_date_range",
        ),
    )
    op.create_index("ix_source_approvals_source_version_id", "source_approvals", ["source_version_id"])

    op.create_table(
        "source_fragments",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_version_id", sa.UUID(as_uuid=True), sa.ForeignKey("source_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("locator", sa.String(length=512), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("extraction_status", sa.String(length=32), nullable=False),
        sa.Column("lexical_search_vector", sa.Text(), nullable=True),
        sa.Column("embedding_reference", sa.Text(), nullable=True),
        sa.Column("display_excerpt", sa.Text(), nullable=True),
    )
    op.create_index("ix_source_fragments_source_version_id", "source_fragments", ["source_version_id"])

    op.create_table(
        "referrals",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("campus", sa.String(length=64), nullable=True),
        sa.Column("term", sa.String(length=64), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("source_approval_id", sa.UUID(as_uuid=True), sa.ForeignKey("source_approvals.id", ondelete="RESTRICT"), nullable=False),
    )
    op.create_index("ix_referrals_source_approval_id", "referrals", ["source_approval_id"])

    op.create_table(
        "user_role_assignments",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("institutional_subject", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("assigned_by", sa.String(length=255), nullable=False),
        sa.UniqueConstraint("institutional_subject", "role", name="uq_user_role_assignments_subject_role"),
        sa.CheckConstraint(
            "role IN ('reviewer', 'source_owner', 'admin', 'conflict_resolver')",
            name="ck_user_role_assignments_role",
        ),
    )

    op.create_table(
        "reviewer_audit_events",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("actor_subject", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("correlation_id", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("before_status", sa.String(length=32), nullable=True),
        sa.Column("after_status", sa.String(length=32), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint(
            "role IN ('reviewer', 'source_owner', 'admin', 'conflict_resolver')",
            name="ck_reviewer_audit_events_role",
        ),
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_id", sa.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by", sa.String(length=255), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("job_type IN ('fetch', 'parse', 'embed', 'change_check')", name="ck_ingestion_jobs_job_type"),
        sa.CheckConstraint("status IN ('queued', 'claimed', 'completed', 'failed')", name="ck_ingestion_jobs_status"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_ingestion_jobs_attempt_count"),
    )
    op.create_index("ix_ingestion_jobs_source_id", "ingestion_jobs", ["source_id"])
    op.create_index("ix_ingestion_jobs_available_at", "ingestion_jobs", ["available_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_ingestion_jobs_available_at"), table_name="ingestion_jobs")
    op.drop_index(op.f("ix_ingestion_jobs_source_id"), table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_table("reviewer_audit_events")
    op.drop_table("user_role_assignments")
    op.drop_table("referrals")
    op.drop_table("source_fragments")
    op.drop_table("source_approvals")
    op.drop_table("source_versions")
    op.drop_index(op.f("ix_sources_canonical_url"), table_name="sources")
    op.drop_table("sources")
    op.execute("DROP EXTENSION IF EXISTS vector")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
