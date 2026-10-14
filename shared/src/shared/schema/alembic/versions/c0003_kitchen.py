"""Kitchen inventory, operation log, clarifications and digest runs.

Revision ID: c0003_kitchen
Revises: c0002_household
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "c0003_kitchen"
down_revision: str | Sequence[str] | None = "c0002_household"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")
NEW_UUID = sa.text("gen_random_uuid()")
TSTZ = pg.TIMESTAMP(timezone=True)
UUID = pg.UUID(as_uuid=True)
SCOPED = "household_id = (SELECT public.current_household_id())"
TABLES = {
    "kitchen_batches": ("true", "status = 'active'"),
    "kitchen_operation_groups": ("true", None),
    "kitchen_clarifications": ("false", None),
    "kitchen_digest_runs": ("false", None),
}
DUE = """
CREATE FUNCTION kitchen_digests_due(p_now timestamptz)
RETURNS TABLE(household_id uuid, owner_id uuid, member_ids uuid[], timezone text, local_date date)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT h.id, o.user_id, pg_catalog.array_agg(m.user_id ORDER BY m.joined_at, m.user_id), h.timezone,
         pg_catalog.timezone(h.timezone, p_now)::date
  FROM public.households h
  JOIN public.household_members o ON o.household_id = h.id AND o.role = 'owner'
  JOIN public.household_members m ON m.household_id = h.id
  WHERE pg_catalog.timezone(h.timezone, p_now)::time >= h.digest_time
    AND NOT EXISTS (
      SELECT 1 FROM public.kitchen_digest_runs r
      WHERE r.household_id = h.id AND r.local_date = pg_catalog.timezone(h.timezone, p_now)::date)
  GROUP BY h.id, o.user_id, h.timezone
$$"""


def _household_fk() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "household_id",
        UUID,
        sa.ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
        server_default=sa.text("public.current_household_id()"),
    )


def _user_fk() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "kitchen_batches",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        _household_fk(),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit", sa.Text, nullable=False),
        sa.Column("location", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("opened", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("opened_on", sa.Date),
        sa.Column("added_at", TSTZ, nullable=False),
        sa.Column("added_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("expires_on", sa.Date, nullable=False),
        sa.Column("expiry_source", sa.Text, nullable=False),
        sa.Column("next_check_on", sa.Date, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("last_group_id", UUID),
        sa.CheckConstraint("quantity >= 0", name="kitchen_batches_quantity_check"),
        sa.CheckConstraint("unit IN ('pcs', 'g', 'ml', 'pack')", name="kitchen_batches_unit_check"),
        sa.CheckConstraint(
            "location IN ('fridge', 'freezer', 'pantry')", name="kitchen_batches_location_check"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'consumed', 'discarded')", name="kitchen_batches_status_check"
        ),
    )
    op.create_index(
        "kitchen_batches_expiry_idx", "kitchen_batches", ["household_id", "status", "expires_on"]
    )
    op.create_index(
        "kitchen_batches_name_idx", "kitchen_batches", ["household_id", "status", "name"]
    )
    op.create_table(
        "kitchen_operation_groups",
        sa.Column("insertion_order", sa.BigInteger, sa.Identity(always=True), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        _household_fk(),
        _user_fk(),
        sa.Column("created_at", TSTZ, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("changes", pg.JSONB, nullable=False),
        sa.Column("undone_at", TSTZ),
        sa.Column("undone_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.create_index(
        "kitchen_operation_groups_user_idx",
        "kitchen_operation_groups",
        ["household_id", "user_id", "created_at"],
    )
    op.create_table(
        "kitchen_clarifications",
        _household_fk(),
        _user_fk(),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.Column("expires_at", TSTZ, nullable=False),
        sa.PrimaryKeyConstraint("household_id", "user_id", name="kitchen_clarifications_pkey"),
    )
    op.create_table(
        "kitchen_digest_runs",
        _household_fk(),
        sa.Column("local_date", sa.Date, nullable=False),
        sa.Column("sent_at", TSTZ, nullable=False, server_default=NOW),
        sa.PrimaryKeyConstraint("household_id", "local_date", name="kitchen_digest_runs_pkey"),
    )
    for table, (moves, item_filter) in TABLES.items():
        filter_sql = "NULL" if item_filter is None else "'" + item_filter.replace("'", "''") + "'"
        op.execute(f"INSERT INTO household_tables VALUES ('{table}', {moves}, {filter_sql})")
        op.execute(f"REVOKE ALL ON {table} FROM app_legacy")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY household_scope ON {table} USING ({SCOPED}) WITH CHECK ({SCOPED})"
        )
    op.execute(DUE)
    op.execute("REVOKE ALL ON FUNCTION kitchen_digests_due(timestamptz) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION kitchen_digests_due(timestamptz) TO app_rw")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS kitchen_digests_due(timestamptz)")
    for table in reversed(list(TABLES)):
        op.execute(f"DELETE FROM household_tables WHERE table_name = '{table}'")
        op.drop_table(table)
