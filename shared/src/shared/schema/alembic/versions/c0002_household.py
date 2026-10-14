"""Households: membership, invites, tenancy functions and household RLS.

Revision ID: c0002_household
Revises: c0001_initial
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "c0002_household"
down_revision: str | Sequence[str] | None = "c0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")
NEW_UUID = sa.text("gen_random_uuid()")
TSTZ = pg.TIMESTAMP(timezone=True)
UUID = pg.UUID(as_uuid=True)
ACTOR = "NULLIF(pg_catalog.current_setting('app.user_id', true), '')::uuid"
DEFINER = "SECURITY DEFINER SET search_path = public, pg_temp"

# Shared with kitchen BatchRepository and digest transactions. Acquire transaction
# locks before reading/mutating household data, then revalidate tenant membership.
# Multi-household membership moves lock keys in signed-bigint order. Actor locks
# precede all household locks; callers must not call membership functions after
# taking a household lock. These helpers never commit the caller's transaction.
# Legacy may CREATE in public: built-ins must use pg_catalog and helper calls
# must have exact argument types (including NULL::uuid) to prevent overload hijacks.
FUNCTIONS = {
    "household_lock_key(uuid)": f"""
CREATE FUNCTION household_lock_key(p_household uuid) RETURNS bigint
LANGUAGE sql IMMUTABLE STRICT {DEFINER} AS $$
  SELECT pg_catalog.hashtextextended(p_household::text, 0)
$$""",
    "household_lock(uuid)": f"""
CREATE FUNCTION household_lock(p_household uuid) RETURNS void
LANGUAGE sql STRICT {DEFINER} AS $$
  SELECT pg_catalog.pg_advisory_xact_lock(public.household_lock_key(p_household))
$$""",
    "household_lock_pair(uuid, uuid)": f"""
CREATE FUNCTION household_lock_pair(p_old uuid, p_new uuid) RETURNS void
LANGUAGE plpgsql {DEFINER} AS $$
DECLARE k bigint;
BEGIN
  FOR k IN SELECT DISTINCT public.household_lock_key(h) FROM pg_catalog.unnest(ARRAY[p_old, p_new]) h
    WHERE h IS NOT NULL ORDER BY 1 LOOP
    PERFORM pg_catalog.pg_advisory_xact_lock(k);
  END LOOP;
END $$""",
    "household_lock_actors(uuid, uuid)": f"""
CREATE FUNCTION household_lock_actors(p_first uuid, p_second uuid) RETURNS void
LANGUAGE plpgsql {DEFINER} AS $$
DECLARE k bigint;
BEGIN
  FOR k IN SELECT DISTINCT pg_catalog.hashtextextended('household-actor:' || u::text, 0)
    FROM pg_catalog.unnest(ARRAY[p_first, p_second]) u WHERE u IS NOT NULL ORDER BY 1 LOOP
    PERFORM pg_catalog.pg_advisory_xact_lock(k);
  END LOOP;
END $$""",
    "current_household_id()": f"""
CREATE FUNCTION current_household_id() RETURNS uuid
LANGUAGE sql STABLE {DEFINER} AS $$
  SELECT household_id FROM household_members WHERE user_id = {ACTOR}
$$""",
    "household_actor()": f"""
CREATE FUNCTION household_actor() RETURNS uuid
LANGUAGE plpgsql {DEFINER} AS $$
DECLARE actor uuid := {ACTOR};
BEGIN
  IF actor IS NULL THEN RAISE EXCEPTION 'no_tenant'; END IF;
  PERFORM public.household_lock_actors(actor, NULL::uuid);
  RETURN actor;
END $$""",
    "household_new_for(uuid, text, text)": f"""
CREATE FUNCTION household_new_for(p_user uuid, p_name text, p_timezone text) RETURNS uuid
LANGUAGE plpgsql {DEFINER} AS $$
DECLARE hid uuid;
BEGIN
  INSERT INTO households (name, timezone) VALUES (p_name, p_timezone) RETURNING id INTO hid;
  INSERT INTO household_members (household_id, user_id, role, display_name)
    VALUES (hid, p_user, 'owner', p_name);
  RETURN hid;
END $$""",
    "household_promote_owner(uuid)": f"""
CREATE FUNCTION household_promote_owner(p_household uuid) RETURNS void
LANGUAGE plpgsql {DEFINER} AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM household_members WHERE household_id = p_household AND role = 'owner') THEN
    UPDATE household_members SET role = 'owner'
    WHERE (household_id, user_id) = (
      SELECT household_id, user_id FROM household_members
      WHERE household_id = p_household ORDER BY joined_at, user_id LIMIT 1);
  END IF;
END $$""",
    "household_item_count(uuid)": f"""
CREATE FUNCTION household_item_count(p_household uuid) RETURNS int
LANGUAGE plpgsql STABLE {DEFINER} AS $$
DECLARE t record; n int := 0; c int;
BEGIN
  FOR t IN SELECT table_name, item_filter FROM household_tables WHERE item_filter IS NOT NULL LOOP
    EXECUTE pg_catalog.format('SELECT pg_catalog.count(*) FROM public.%I WHERE household_id = $1 AND (%s)', t.table_name, t.item_filter)
      INTO c USING p_household;
    n := n + c;
  END LOOP;
  RETURN n;
END $$""",
    "household_rate_limited(uuid)": f"""
CREATE FUNCTION household_rate_limited(p_user uuid) RETURNS boolean
LANGUAGE plpgsql {DEFINER} AS $$
BEGIN
  -- Opportunistic global retention, without waiting on another cleanup's rows.
  DELETE FROM household_join_attempts WHERE id IN (
    SELECT id FROM household_join_attempts
    WHERE attempted_at < pg_catalog.now() - interval '24 hours' FOR UPDATE SKIP LOCKED);

  RETURN (SELECT pg_catalog.count(*) >= 5 FROM household_join_attempts
  WHERE user_id = p_user AND NOT succeeded AND attempted_at > pg_catalog.now() - interval '1 hour');
END $$""",
    "household_ensure(text, text)": f"""
CREATE FUNCTION household_ensure(p_name text, p_timezone text) RETURNS uuid
LANGUAGE plpgsql {DEFINER} AS $$
DECLARE actor uuid := public.household_actor(); hid uuid; u record;
BEGIN
  INSERT INTO users (id, name, timezone) VALUES (actor, p_name, p_timezone)
    ON CONFLICT (id) DO NOTHING;
  SELECT household_id INTO hid FROM household_members WHERE user_id = actor;
  IF hid IS NOT NULL THEN RETURN hid; END IF;
  SELECT name, timezone INTO u FROM users WHERE id = actor;
  BEGIN
    hid := public.household_new_for(actor, u.name, u.timezone);
  EXCEPTION WHEN unique_violation THEN
    SELECT household_id INTO hid FROM household_members WHERE user_id = actor;
  END;
  RETURN hid;
END $$""",
    "household_update(text, text, time)": f"""
CREATE FUNCTION household_update(p_name text, p_timezone text, p_digest_time time) RETURNS text
LANGUAGE plpgsql {DEFINER} AS $$
DECLARE actor uuid := public.household_actor(); m record;
BEGIN
  SELECT household_id, role INTO m FROM household_members WHERE user_id = actor;
  PERFORM public.household_lock(m.household_id);
  SELECT household_id, role INTO m FROM household_members WHERE user_id = actor;
  IF m.household_id IS NULL THEN RETURN 'no_household'; END IF;
  IF m.role <> 'owner' THEN RETURN 'not_owner'; END IF;
  UPDATE households SET
    name = COALESCE(p_name, name),
    timezone = COALESCE(p_timezone, timezone),
    digest_time = COALESCE(p_digest_time, digest_time)
  WHERE id = m.household_id;
  RETURN 'ok';
END $$""",
    "household_invite_preview(bytea)": f"""
CREATE FUNCTION household_invite_preview(p_code_hash bytea)
RETURNS TABLE(status text, household_name text, member_count int, items_to_move int)
LANGUAGE plpgsql {DEFINER} AS $$
#variable_conflict use_column
DECLARE actor uuid := public.household_actor(); inv record; mine uuid; mine_count int;
BEGIN
  IF public.household_rate_limited(actor) THEN
    RETURN QUERY SELECT 'rate_limited'::text, NULL::text, NULL::int, NULL::int; RETURN;
  END IF;
  SELECT * INTO inv FROM household_invites i WHERE i.code_hash = p_code_hash;
  SELECT m.household_id INTO mine FROM household_members m WHERE m.user_id = actor;
  PERFORM public.household_lock_pair(mine, inv.household_id);
  SELECT * INTO inv FROM household_invites i WHERE i.code_hash = p_code_hash;
  IF inv.id IS NULL OR inv.redeemed_at IS NOT NULL OR inv.expires_at <= pg_catalog.now() THEN
    INSERT INTO household_join_attempts (user_id, succeeded) VALUES (actor, false);
    RETURN QUERY SELECT 'invalid'::text, NULL::text, NULL::int, NULL::int; RETURN;
  END IF;
  SELECT m.household_id INTO mine FROM household_members m WHERE m.user_id = actor;
  IF mine = inv.household_id THEN
    RETURN QUERY SELECT 'own'::text, NULL::text, NULL::int, NULL::int; RETURN;
  END IF;
  SELECT pg_catalog.count(*) INTO mine_count FROM household_members m WHERE m.household_id = mine;
  RETURN QUERY
    SELECT 'ok'::text, h.name,
      (SELECT pg_catalog.count(*)::int FROM household_members m WHERE m.household_id = h.id),
      CASE WHEN mine_count = 1 THEN public.household_item_count(mine) ELSE 0 END
    FROM households h WHERE h.id = inv.household_id;
END $$""",
    "household_join(bytea)": f"""
CREATE FUNCTION household_join(p_code_hash bytea)
RETURNS TABLE(status text, household_id uuid)
LANGUAGE plpgsql {DEFINER} AS $$
#variable_conflict use_column
DECLARE actor uuid := public.household_actor(); inv record; me record; n int; t record; dn text;
BEGIN
  IF public.household_rate_limited(actor) THEN
    RETURN QUERY SELECT 'rate_limited'::text, NULL::uuid; RETURN;
  END IF;
  SELECT * INTO inv FROM household_invites i WHERE i.code_hash = p_code_hash;
  SELECT m.household_id, m.role, m.display_name INTO me
    FROM household_members m WHERE m.user_id = actor;
  PERFORM public.household_lock_pair(me.household_id, inv.household_id);
  SELECT * INTO inv FROM household_invites i WHERE i.code_hash = p_code_hash FOR UPDATE;
  IF inv.id IS NULL OR inv.redeemed_at IS NOT NULL OR inv.expires_at <= pg_catalog.now() THEN
    INSERT INTO household_join_attempts (user_id, succeeded) VALUES (actor, false);
    RETURN QUERY SELECT 'invalid'::text, NULL::uuid; RETURN;
  END IF;
  SELECT m.household_id, m.role, m.display_name INTO me
    FROM household_members m WHERE m.user_id = actor FOR UPDATE;
  IF me.household_id = inv.household_id THEN
    RETURN QUERY SELECT 'own'::text, NULL::uuid; RETURN;
  END IF;
  dn := me.display_name;
  IF dn IS NULL THEN SELECT name INTO dn FROM users WHERE id = actor; END IF;
  IF me.household_id IS NOT NULL THEN
    SELECT pg_catalog.count(*) INTO n FROM household_members m WHERE m.household_id = me.household_id;
    DELETE FROM household_members m WHERE m.user_id = actor;
    IF n = 1 THEN
      FOR t IN SELECT table_name FROM household_tables WHERE move_on_join LOOP
        EXECUTE pg_catalog.format('UPDATE public.%I SET household_id = $1 WHERE household_id = $2', t.table_name)
          USING inv.household_id, me.household_id;
      END LOOP;
      DELETE FROM households h WHERE h.id = me.household_id;
    ELSIF me.role = 'owner' THEN
      PERFORM public.household_promote_owner(me.household_id);
    END IF;
  END IF;
  INSERT INTO household_members (household_id, user_id, role, display_name)
    VALUES (inv.household_id, actor, 'member', COALESCE(dn, 'member'));
  UPDATE household_invites i SET redeemed_at = pg_catalog.now(), redeemed_by = actor WHERE i.id = inv.id;
  INSERT INTO household_join_attempts (user_id, succeeded) VALUES (actor, true);
  RETURN QUERY SELECT 'ok'::text, inv.household_id;
END $$""",
    "household_leave()": f"""
CREATE FUNCTION household_leave() RETURNS TABLE(status text, household_id uuid)
LANGUAGE plpgsql {DEFINER} AS $$
#variable_conflict use_column
DECLARE actor uuid := public.household_actor(); me record; n int; tz text; fresh uuid;
BEGIN
  SELECT m.household_id INTO me FROM household_members m WHERE m.user_id = actor;
  PERFORM public.household_lock(me.household_id);
  SELECT m.household_id, m.role, m.display_name INTO me
    FROM household_members m WHERE m.user_id = actor FOR UPDATE;
  IF me.household_id IS NULL THEN RETURN QUERY SELECT 'no_household'::text, NULL::uuid; RETURN; END IF;
  SELECT pg_catalog.count(*) INTO n FROM household_members m WHERE m.household_id = me.household_id;
  IF n = 1 THEN RETURN QUERY SELECT 'sole_member'::text, NULL::uuid; RETURN; END IF;
  SELECT h.timezone INTO tz FROM households h WHERE h.id = me.household_id;
  DELETE FROM household_members m WHERE m.user_id = actor;
  IF me.role = 'owner' THEN PERFORM public.household_promote_owner(me.household_id); END IF;
  fresh := public.household_new_for(actor, me.display_name, tz);
  RETURN QUERY SELECT 'ok'::text, fresh;
END $$""",
    "household_remove_member(uuid)": f"""
CREATE FUNCTION household_remove_member(p_user uuid) RETURNS text
LANGUAGE plpgsql {DEFINER} AS $$
DECLARE actor uuid := {ACTOR}; me record; target record; tz text;
BEGIN
  IF actor IS NULL THEN RAISE EXCEPTION 'no_tenant'; END IF;
  PERFORM public.household_lock_actors(actor, p_user);
  SELECT household_id, role INTO me FROM household_members WHERE user_id = actor;
  PERFORM public.household_lock(me.household_id);
  SELECT household_id, role INTO me FROM household_members WHERE user_id = actor;
  IF me.household_id IS NULL THEN RETURN 'no_household'; END IF;
  IF me.role <> 'owner' THEN RETURN 'not_owner'; END IF;
  IF p_user = actor THEN RETURN 'self'; END IF;
  SELECT user_id, display_name INTO target FROM household_members
    WHERE household_id = me.household_id AND user_id = p_user FOR UPDATE;
  IF target.user_id IS NULL THEN RETURN 'not_member'; END IF;
  SELECT timezone INTO tz FROM households WHERE id = me.household_id;
  DELETE FROM household_members WHERE user_id = p_user;
  PERFORM public.household_new_for(p_user, target.display_name, tz);
  RETURN 'ok';
END $$""",
}
PUBLIC_FUNCTIONS = (
    "household_lock_key(uuid)",
    "household_lock(uuid)",
    "current_household_id()",
    "household_ensure(text, text)",
    "household_update(text, text, time)",
    "household_invite_preview(bytea)",
    "household_join(bytea)",
    "household_leave()",
    "household_remove_member(uuid)",
)
SCOPED = "household_id = (SELECT current_household_id())"


def upgrade() -> None:
    op.create_table(
        "households",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("timezone", sa.Text, nullable=False, server_default=sa.text("'UTC'")),
        sa.Column("digest_time", sa.Time, nullable=False, server_default=sa.text("'18:00'")),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
    )
    op.create_table(
        "household_members",
        sa.Column(
            "household_id", UUID, sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("joined_at", TSTZ, nullable=False, server_default=NOW),
        sa.PrimaryKeyConstraint("household_id", "user_id", name="household_members_pkey"),
        sa.UniqueConstraint("user_id", name="household_members_user_id_key"),
        sa.CheckConstraint("role IN ('owner', 'member')", name="household_members_role_check"),
    )
    op.create_index(
        "household_members_one_owner",
        "household_members",
        ["household_id"],
        unique=True,
        postgresql_where=sa.text("role = 'owner'"),
    )
    # SQL-language bodies are validated now, so the function follows household_members.
    op.execute(FUNCTIONS["current_household_id()"])
    op.create_table(
        "household_invites",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column(
            "household_id",
            UUID,
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
            server_default=sa.text("current_household_id()"),
        ),
        sa.Column("code_hash", sa.LargeBinary, nullable=False),
        sa.Column(
            "created_by", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("expires_at", TSTZ, nullable=False),
        sa.Column("redeemed_at", TSTZ),
        sa.Column("redeemed_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.UniqueConstraint("code_hash", name="household_invites_code_hash_key"),
    )
    op.create_table(
        "household_join_attempts",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempted_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("succeeded", sa.Boolean, nullable=False),
    )
    op.create_index(
        "household_join_attempts_user_idx", "household_join_attempts", ["user_id", "attempted_at"]
    )
    op.create_table(
        "household_tables",
        sa.Column("table_name", sa.Text, primary_key=True),
        sa.Column("move_on_join", sa.Boolean, nullable=False),
        sa.Column("item_filter", sa.Text),
    )
    op.execute("INSERT INTO household_tables VALUES ('household_invites', false, NULL)")
    for signature, ddl in FUNCTIONS.items():
        if signature != "current_household_id()":
            op.execute(ddl)
    for signature in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    for signature in PUBLIC_FUNCTIONS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO app_rw")

    # Default privileges granted DML to app_rw/app_legacy; narrow them.
    op.execute(
        "REVOKE ALL ON households, household_members, household_invites, "
        "household_join_attempts, household_tables FROM app_rw, app_legacy"
    )
    op.execute("GRANT SELECT ON households, household_members TO app_rw")
    op.execute("GRANT SELECT, INSERT, DELETE ON household_invites TO app_rw")

    # ENABLE without FORCE: app_owner (migrations and the functions above) is not filtered.
    for table in (
        "households",
        "household_members",
        "household_invites",
        "household_join_attempts",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY household_self ON households FOR SELECT "
        "USING (id = (SELECT current_household_id()))"
    )
    op.execute(f"CREATE POLICY household_scope ON household_members FOR SELECT USING ({SCOPED})")
    op.execute(
        f"CREATE POLICY household_scope ON household_invites USING ({SCOPED}) WITH CHECK ({SCOPED})"
    )


def downgrade() -> None:
    for signature in reversed(list(FUNCTIONS)):
        if signature != "current_household_id()":
            op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    for table in ("household_tables", "household_join_attempts", "household_invites"):
        op.drop_table(table)
    op.drop_index("household_members_one_owner", table_name="household_members")
    op.drop_table("household_members")  # drops the policy that uses current_household_id()
    op.drop_table("households")
    op.execute("DROP FUNCTION IF EXISTS current_household_id()")
