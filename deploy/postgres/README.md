# PostgreSQL roles and migrations

The `migrate` service runs on every `docker compose up`. It uses the configured PostgreSQL administrator to create or update two roles:

- `app_owner` owns the schema and runs Alembic migrations.
- `app_rw` is the runtime role. Services set `app.user_id` for each tenant transaction, and row-level security restricts user data.

Set `APP_OWNER_PASSWORD` and `APP_RW_PASSWORD` in `.env` using letters, digits, `_` or `-`. The bootstrap revokes `CREATE` on `public` from `PUBLIC` and `app_rw`. Runtime code cannot change the schema or write Alembic's version table. All services connect as `app_rw`.

When upgrading from before 3c, the migrate job reassigns objects owned by the retired runtime role to `app_owner`, drops the old role and its remaining grants, then applies the current schema. Remove the old legacy-role password entry from `.env`; it is no longer read. The role retirement applies to this deployment's single application database. If a cluster has other databases with grants to that old role, bootstrap fails visibly so those grants can be handled by the administrator.

Alembic owns the four LangGraph checkpoint tables. Revision `c0010_chat` recreates them using the schema pinned to `langgraph-checkpoint-postgres` 3.1.3. Earlier checkpoint rows lacked user ownership and are intentionally removed during this migration. The new orchestrator verifies the checkpoint schema version at startup and does not run the library's `setup()`.

Integration tests use a disposable PostgreSQL 16 container and require Docker. Unit tests do not start it.
