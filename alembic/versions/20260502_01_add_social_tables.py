"""add_social_tables

Adds the /social vertical: venues, happy_hour_specials, parking_spots,
user_submissions, ad_placements. All new tables, no existing ones touched.

Revision ID: 20260502_01_social
Revises:
Create Date: 2026-05-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260502_01_social"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "social_venues",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(160), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("venue_type", sa.String(32), nullable=False, index=True),
        sa.Column("neighborhood", sa.String(96), nullable=False, index=True),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("lat", sa.Float, nullable=True),
        sa.Column("lng", sa.Float, nullable=True),
        sa.Column("phone", sa.String(48), nullable=True),
        sa.Column("website", sa.String(512), nullable=True),
        sa.Column("instagram", sa.String(128), nullable=True),
        sa.Column("price_tier", sa.Integer, nullable=False, server_default="2"),
        sa.Column(
            "vibe_tags",
            postgresql.ARRAY(sa.String(48)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("hours_json", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("featured", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_verified_at", sa.DateTime, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_social_venues_neighborhood_type",
        "social_venues",
        ["neighborhood", "venue_type"],
    )
    op.create_index(
        "ix_social_venues_vibe_tags",
        "social_venues",
        ["vibe_tags"],
        postgresql_using="gin",
    )

    op.create_table(
        "happy_hour_specials",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "venue_id",
            sa.Integer,
            sa.ForeignKey("social_venues.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "days_of_week",
            postgresql.ARRAY(sa.Integer),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("start_time", sa.Time, nullable=True),
        sa.Column("end_time", sa.Time, nullable=True),
        sa.Column("deal_type", sa.String(24), nullable=False, server_default="drink"),
        sa.Column("discount_value", sa.String(120), nullable=True),
        sa.Column("dine_in_only", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("industry_only", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "requires_membership", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column("effective_from", sa.Date, nullable=True),
        sa.Column("effective_until", sa.Date, nullable=True),
        sa.Column("source", sa.String(24), nullable=False, server_default="manual"),
        sa.Column("source_url", sa.String(512), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_verified_at", sa.DateTime, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_happy_hour_specials_venue_active",
        "happy_hour_specials",
        ["venue_id", "active"],
    )
    op.create_index(
        "ix_happy_hour_specials_days",
        "happy_hour_specials",
        ["days_of_week"],
        postgresql_using="gin",
    )

    op.create_table(
        "parking_spots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("lat", sa.Float, nullable=True),
        sa.Column("lng", sa.Float, nullable=True),
        sa.Column("parking_type", sa.String(24), nullable=False, server_default="lot"),
        sa.Column("nightly_rate", sa.String(48), nullable=True),
        sa.Column("event_rate", sa.String(48), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "near_neighborhood", sa.String(96), nullable=True, index=True
        ),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "user_submissions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("submission_type", sa.String(32), nullable=False, index=True),
        sa.Column("payload_json", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("submitter_email", sa.String(255), nullable=True),
        sa.Column("submitter_ip", sa.String(64), nullable=True),
        sa.Column(
            "status", sa.String(24), nullable=False, server_default="pending", index=True
        ),
        sa.Column("review_notes", sa.Text, nullable=True),
        sa.Column("reviewed_by", sa.String(96), nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "ad_placements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("advertiser_name", sa.String(160), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("placement_slot", sa.String(48), nullable=False, index=True),
        sa.Column("target_neighborhood", sa.String(96), nullable=True),
        sa.Column("target_vibe_tag", sa.String(48), nullable=True),
        sa.Column("creative_url", sa.String(512), nullable=True),
        sa.Column("click_url", sa.String(512), nullable=True),
        sa.Column("headline", sa.String(160), nullable=True),
        sa.Column("subheadline", sa.String(255), nullable=True),
        sa.Column("starts_at", sa.DateTime, nullable=True),
        sa.Column("ends_at", sa.DateTime, nullable=True),
        sa.Column("monthly_rate_cents", sa.Integer, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("impressions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("ad_placements")
    op.drop_table("user_submissions")
    op.drop_table("parking_spots")
    op.drop_index("ix_happy_hour_specials_days", table_name="happy_hour_specials")
    op.drop_index(
        "ix_happy_hour_specials_venue_active", table_name="happy_hour_specials"
    )
    op.drop_table("happy_hour_specials")
    op.drop_index("ix_social_venues_vibe_tags", table_name="social_venues")
    op.drop_index("ix_social_venues_neighborhood_type", table_name="social_venues")
    op.drop_table("social_venues")
