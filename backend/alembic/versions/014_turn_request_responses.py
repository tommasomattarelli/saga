"""Persist committed action responses for exact idempotent replay."""

from alembic import op
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB

revision = "014_turn_request_responses"
down_revision = "013_turn_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("turn_requests", Column("response_payload", JSONB, nullable=True))
    op.create_check_constraint(
        "ck_turn_requests_response_state",
        "turn_requests",
        "response_payload IS NULL OR (state = 'committed' AND jsonb_typeof(response_payload) = 'object')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_turn_requests_response_state", "turn_requests", type_="check")
    op.drop_column("turn_requests", "response_payload")
