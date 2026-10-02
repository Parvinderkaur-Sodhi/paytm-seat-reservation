"""allow seat reuse after cancellation

Revision ID: c1a493e560bb
Revises: e2902f5f40c3
Create Date: 2026-10-03 00:06:40.844523

"""
from alembic import op


revision = "c1a493e560bb"
down_revision = "e2902f5f40c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "reservation_seats_seat_id_key",
        "reservation_seats",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "reservation_seats_seat_id_key",
        "reservation_seats",
        ["seat_id"],
    )