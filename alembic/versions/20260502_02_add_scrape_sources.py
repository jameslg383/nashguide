"""add_scrape_sources

Adds the `scrape_sources` table — URLs the social-scraper agent should visit
on a schedule. Output always lands in `user_submissions` (never live tables).

Revision ID: 20260502_02_scrape_sources
Revises: 20260502_01_social
Create Date: 2026-05-02
"""
from alembic import op
import sqlalchemy as sa


revision = "20260502_02_scrape_sources"
down_revision = "20260502_01_social"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scrape_sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("url", sa.String(512), nullable=False, unique=True, index=True),
        sa.Column("label", sa.String(160), nullable=True),
        sa.Column("source_type", sa.String(24), nullable=False, server_default="venue_page"),
        sa.Column("frequency", sa.String(16), nullable=False, server_default="weekly"),
        sa.Column(
            "venue_id",
            sa.Integer,
            sa.ForeignKey("social_venues.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_scraped_at", sa.DateTime, nullable=True),
        sa.Column("last_status", sa.String(48), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("last_specials_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("scrape_sources")
