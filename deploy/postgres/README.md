# PostgreSQL roles

The `migrate` service (`python -m shared.schema`) runs on every `docker compose up`:

1. As the bootstrap superuser (`POSTGRES_USER`), it creates or updates three roles:
   - `app_owner` owns the schema and applies Alembic migrations;
   - `app_rw` (NOBYPASSRLS) is used by migrated services; every transaction sets
     `app.user_id`, and row-level security limits it to that user's rows;
   - `app_legacy` (BYPASSRLS) is used by services not yet migrated; it disappears when the
     last one moves to `app_rw`.
2. As `app_owner`, it runs `alembic upgrade heads`.

Passwords come from `APP_OWNER_PASSWORD`, `APP_RW_PASSWORD`, `APP_LEGACY_PASSWORD` in `.env`
(letters, digits, `_` and `-` only).

Bootstrap uses the configured administrator only for `ensure_roles`. Alembic always
connects as `app_owner`, including in the test container. The controlled roles
are reset to `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION`; only
`app_legacy` retains `BYPASSRLS`. Bootstrap revokes public schema creation from
`PUBLIC` and `app_rw`. Both application roles receive table DML, while
`app_legacy` temporarily retains schema creation for LangGraph checkpoints.
Alembic migration history (`alembic_version`) is owner-only: application roles
have all privileges revoked on that control table after the application grants.

Every tenant table has `ENABLE` and `FORCE ROW LEVEL SECURITY`, including
`users` and the text-keyed `telemetry_consent`. UUID tenant keys compare against
`NULLIF(current_setting('app.user_id', true), '')::uuid`; consent compares text
without a UUID cast. Missing or cleared transaction-local tenants see no rows.
The development consent seed `owner` is read through the administrator or
legacy connection, or through an explicitly selected tenant.

`c0001_initial` starts the `core` Alembic branch. Future domain branches use a
separate root with `branch_labels = ("nutrition",)` (or the domain name),
`down_revision = None`, and `depends_on = "c0001_initial"`. Subsequent domain
revisions link to their preceding domain revision. Nutrition adds no tables in
this foundation, so no empty domain revision is created. `upgrade heads`
applies every domain head after its core dependency.

This initial revision targets a fresh database after the approved development
data reset; it does not translate an earlier migration history. On
Compose startup every database consumer waits for the migrate service to finish
successfully. Services use `app_legacy` until their migration to tenant-aware
`app_rw` transactions. Runtime `init_db_pool()` never changes the schema.

Integration tests require a running Docker daemon. A missing or unreachable
Docker daemon fails the integration suite, including CI. Tests use a disposable
PostgreSQL 16 container, not the developer's database. Unit tests do not start it.
