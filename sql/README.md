# Manual PostgreSQL patches

Write necessary database patches in this folder on the current host. **The user reviews and applies every patch manually. Agents must never connect to a database or execute a SQL file.** No patch is required merely to add the Codex configuration.

The current schema baseline designated by the user is `../../legacy/postgres_schema.sql`. Existing API SQL files must be compared with that baseline; do not assume they have been applied. Assess Supabase `auth.users`, `auth.uid()`, `auth.jwt()`, triggers, policies, and identifier relationships explicitly when proposing Cognito-related changes.

Use a descriptive ordered filename such as `YYYYMMDD_01_description.sql`. Review existing names first to avoid collisions. Each patch must include:

- Purpose and the feature/code that depends on it.
- Required schema state, dependencies, application order, and manual prerequisites.
- Transaction boundaries where PostgreSQL supports them; explain operations that must run outside a transaction.
- Safe rerun behavior or an explicit one-time-only warning, plus preservation/backfill rules for existing data.
- Expected lock, downtime, and data-loss implications where applicable.
- Commented verification queries for the user to run manually and a rollback plan or an explanation of why rollback is unsafe.

Prefer additive, minimal changes and explicit object qualification. Do not include credentials, real student/health data, or a full replacement schema unless specifically requested. Destructive changes must be clearly identified and never silently bundled with unrelated migration work. List pending patch paths and application order in the implementation handoff; static review does not establish that a patch has been applied.
