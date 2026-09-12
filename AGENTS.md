# Current backend

Follow the workspace root `AGENTS.md`. Only AWS profile `imhealth-dev` and Serverless stage `dev` are permitted. No database connections, including connections made indirectly by live endpoints, Lambda, Cognito triggers, or ECS jobs.

The backend engineer owns this Python AWS Lambda / Serverless Framework application. Follow the existing separation between `services/<domain>/` handlers, `generic_dals/`, `models/`, `constants/`, and `utils/`. Add routes to the appropriate service's `serverless.yml`; reuse request/response helpers and current Cognito authorization. Review actual per-service runtime and dependencies rather than assuming a Node.js backend because the source application uses Next.js.

Migrate server behavior from `../legacy/`. Preserve authorization, validation, scoring, pagination, reports, and scheduled-task behavior. Coordinate payloads and errors with the frontend engineer. Use parameterized SQL and compare queries with `../legacy/postgres_schema.sql`. Existing `schema.sql` and `migrate_supabase_to_cognito.sql` do not establish that changes are already applied.

Put any necessary new database patches in `sql/` for manual application by the user; never execute them. Follow `sql/README.md`. Do not modify real development/production secrets or run the existing deployment/SSM scripts as part of local verification.

`utils/db.py` uses lazy connections: DAL execution can still call `psycopg2.connect`. Replace both the DAL boundary and the underlying connection entry point before running handler tests. Mock `boto3` and email/ECS calls before they can resolve credentials or access networks. Use offline Python syntax/static checks and meaningful targeted tests. Do not execute handlers, Serverless configuration resolution, packaging, or jobs without reviewing their side effects first.
