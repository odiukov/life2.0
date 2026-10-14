"""Move legacy Garmin sleep and Yazio meal rows onto the keys of the 3b mappers.

Legacy Garmin sleep rows stored the device's local wall time labelled as UTC; legacy Yazio meals
sat at fixed UTC hours. The new mappers write true UTC instants and place Yazio slots in the
user's zone, so without this the next sync would duplicate the last days. A row is left alone
when its new key is already taken.

RELEASE REQUIREMENT: deploy only with the Task 8 writer cutover, after stopping legacy sync.
This migration auto-runs; an intermediate deployment with the legacy writer would recreate the
old keys. Task 9 operations documentation must carry this requirement forward.

Ambiguous wall times use the first occurrence, matching the mapper's local-only fold=0 default.
Legacy rows did not retain GMT epochs or UTC offsets. Sleep duration is not guaranteed elapsed
start-to-end time, and legacy end_time is offset-free and host-derived, so these fields cannot
reliably recover the fold. A historical second-occurrence session may still differ from a later
GMT-bearing payload and acquire a second key; it needs source GMT/offset evidence to reconcile.

Revision ID: c0006_sync_rekey
Revises: c0005_sync
Create Date: 2026-10-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c0006_sync_rekey"
down_revision: str | Sequence[str] | None = "c0005_sync"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ZONE = "COALESCE(tz.name, 'UTC')"
REKEY = f"""
WITH local_keys AS (
  SELECT h.id, {ZONE} AS zone, CASE
      WHEN h.source = 'garmin' THEN h.recorded_at AT TIME ZONE 'UTC'
      ELSE (h.data->>'date')::date + make_interval(hours => CASE h.data->>'meal_type'
              WHEN 'breakfast' THEN 8 WHEN 'lunch' THEN 12 WHEN 'dinner' THEN 18 ELSE 15 END)
    END AS local_at
  FROM health_logs h JOIN users u ON u.id = h.user_id
  LEFT JOIN pg_catalog.pg_timezone_names tz ON tz.name = u.timezone
  WHERE (h.source = 'garmin' AND h.type = 'sleep_session')
     OR (h.source = 'yazio' AND h.type = 'meal' AND h.data->>'date' ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}$')
), moved AS (
  SELECT l.id, COALESCE(resolved.first_at, l.local_at AT TIME ZONE l.zone) AS new_at
  FROM local_keys l
  CROSS JOIN LATERAL (
    -- Probe the adjacent days' offsets, rather than assuming a one-hour DST shift.
    -- Only candidates that round-trip to the exact wall time qualify. Normal times
    -- retain their unique instant; overlaps choose the earlier instant (fold=0).
    SELECT min(c.instant) AS first_at
    FROM (VALUES
      (l.local_at AT TIME ZONE l.zone),
      (((l.local_at - interval '24 hours') AT TIME ZONE l.zone) + interval '24 hours'),
      (((l.local_at + interval '24 hours') AT TIME ZONE l.zone) - interval '24 hours')
    ) AS c(instant)
    WHERE c.instant AT TIME ZONE l.zone = l.local_at
  ) resolved
)
UPDATE health_logs h SET recorded_at = m.new_at
FROM moved m
WHERE h.id = m.id AND h.recorded_at <> m.new_at
  AND NOT EXISTS (
    SELECT 1 FROM health_logs o
    WHERE o.user_id = h.user_id AND o.source = h.source AND o.type = h.type AND o.recorded_at = m.new_at
  )
"""


def upgrade() -> None:
    # FORCE RLS filters the owner too; lift it for this one statement inside the migration's transaction.
    op.execute("ALTER TABLE health_logs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users NO FORCE ROW LEVEL SECURITY")
    op.execute(REKEY)
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE health_logs FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Irreversible by design: the old keys were wrong. Nothing to undo for the schema."""
