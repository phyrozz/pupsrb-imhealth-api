# pupsrb-imhealth-api

Serverless Python API for PUP-iMHealth. Migrated from Next.js + Supabase API to AWS Lambda + API Gateway + PostgreSQL direct connection.

## Structure

```
pupsrb-imhealth-api/
├── constants/          # Shared constants
├── utils/              # Shared utility functions
├── models/             # Data models / dataclasses
├── generic_dals/       # Generic data access layer helpers
├── services/
│   ├── auth/           # Cognito triggers (pre sign-up, post confirmation)
│   ├── profile/        # Get/update profile, avatar upload
│   ├── students/       # List, get, import CSV, personal details CRUD
│   ├── assessments/    # Submit, list, apriori results, counseling status
│   ├── dashboard/      # Stats, charts, trend data
│   └── cron/           # Insert assessment trends, send reminder emails
└── requirements.txt
```

## Program lookup for student sign-up

The students service exposes public `GET /programs` before Cognito sign-up. It accepts optional `q`,
`page` (default `1`), and `page_size` (default `25`, capped at `50`) query parameters. `q` searches
program initials and names case-insensitively; blank `q` has no filter. Invalid `page` or `page_size`
returns HTTP 400 with a safe message. A successful response is:

```json
{
  "items": [{ "id": 1, "initial": "BSIT", "name": "Bachelor of Science in Information Technology" }],
  "page": 1,
  "page_size": 25,
  "total": 1,
  "has_more": false
}
```

Items are ordered by `initial`, `name`, then `id`. Failures return HTTP 500 with
`{ "message": "Unable to load programs. Please try again later." }`.
The route has the existing CORS configuration and no Cognito authorizer; other student routes retain their authorization.
It reads only `id`, `initial`, and `name` from the existing `public.programs` table in `legacy/postgres_schema.sql`.
That baseline permits anonymous program reads. No schema patch is required.

Run the lookup's offline tests with `python -m unittest discover -s tests -p test_programs.py`.
The tests use fake connections and block real database and AWS entry points before importing application code.

## Student identity and onboarding

Cognito authenticates students by email. The API resolves that trusted token email to
`profiles.username` and uses the database's `profiles.id` for `personal_details`,
assessment history, assessment inserts, and reminders. Cognito `sub` is not a database profile ID.
New profiles store the normalized email in both `username` and `full_name`.

After email confirmation and the first authenticated sign-in, the web app sends the
pending registration details to `POST /students/personal-details`. This student-authorized
endpoint provisions the profile when necessary, so onboarding does not depend on an
attached Cognito post-confirmation trigger. Pending details are removed only after a
successful save; assessment submission is blocked while saving or after a save failure.

The designated baseline still makes `profiles.id` depend on Supabase `auth.users` and
`auth.uid()`. Review and manually apply [the internal identity patch](sql/20260912_01_internal_profile_identity.sql)
before deploying this provisioning flow. Existing profile IDs and their dependent data
must be preserved. Neither deployment nor patch application is established by offline tests.

## Assessment cooldown and confirmation email

Student assessment submission reads `public.settings.assessment_cooldown_days` as a
string and validates it as a positive whole number. The generic settings table can
therefore support other value types in the future. A per-student database transaction
lock prevents repeat submissions during the
configured cooldown. The initial setting is seven days. Review and manually apply
[the cooldown settings patch](sql/20260913_01_assessment_cooldown_settings.sql) after
the internal identity patch. Changing the setting later requires only a database
setting update; it does not require an API deployment.

After a successful submission, the assessments service sends a confirmation email
through SES using `SES_FROM_EMAIL`, resolved from `/pupsrb-imhealth/dev/ses/from_email`.
The message includes the next available assessment time in Philippine time.

The schedule-assessment service starts a Fargate worker every day at **01:00 UTC**. The worker
reads the same cooldown setting, finds students whose latest assessment is now
eligible, and sends one SES availability email per assessment. It uses the existing
`assessment_reminders.reminder_sent` marker, which submission resets, so a student
is not emailed again on subsequent days. The EventBridge-triggered Lambda only
starts the task; Fargate performs the paginated student scan and email delivery,
avoiding Lambda's 15-minute execution limit. The worker must be included in the
`pupsrb-imhealth-schedule-assessment` ECS task image when this code is deployed. Its
EventBridge Lambda entry point is `services/schedule_assessment/task_runner.py`; the
Fargate container entry point is `services/schedule_assessment/main.py`.

## ECS task deployment

`deploy-ecs.ps1` and `deploy-ecs.sh` deploy an ECS task image for a service in
the development account only. They create the ECR repository if necessary, push
the service image as `:latest`, and always register a new Fargate task-definition
revision that references that tag. They also create the service's CloudWatch log
group if it is absent. They do not start a task.

The scripts read the existing development task execution and task role ARNs from
`/pupsrb-imhealth/dev/iam/ecs_task_execution_role_arn` and
`/pupsrb-imhealth/dev/iam/ecs_task_role_arn`. They do not read database values.

```powershell
.\deploy-ecs.ps1 -ServiceName schedule_assessment
```

```bash
./deploy-ecs.sh schedule_assessment
```

Each ECS service needs `services/<name>/Dockerfile` and
`services/<name>/ecs-task-definition.json`. The schedule-assessment template supplies database
and SES values to the container through SSM parameter references; the supplied
execution role must be allowed to read those parameters, and its task role must
allow SES delivery. Its logs are sent to `/ecs/pupsrb-imhealth-schedule-assessment-dev`.

## AWS Services Used

- **Lambda + API Gateway** — API endpoints
- **Cognito** — Authentication (triggers in `services/auth`)
- **S3** — Profile avatar storage
- **SES / Resend** — Transactional emails (cron reminders, status updates)
- **RDS / PostgreSQL** — Direct DB connection (replaces Supabase API)

## Environment Variables

Each service reads from Lambda environment variables:

| Variable | Description |
|---|---|
| `DB_HOST` | PostgreSQL host |
| `DB_PORT` | PostgreSQL port (default 5432) |
| `DB_NAME` | Database name |
| `DB_USER` | Database user |
| `DB_PASSWORD` | Database password |
| `S3_BUCKET_NAME` | S3 bucket for avatars |
| `COGNITO_USER_POOL_ID` | Cognito User Pool ID |
| `SES_FROM_EMAIL` | Sender email address |
| `CRON_SECRET` | Secret for cron authorization |

## Deployment

Each service is deployed independently:

```bash
cd services/<service_name>
serverless deploy --stage prod
```


## Administrator module permissions

Apply `sql/20260914_01_admin_module_permissions.sql` manually before deploying this code.
The patch is pending until the user applies it. Its RLS configuration requires the trusted
application database role to own/bypass RLS on the new tables and have appropriate SQL
privileges; verify this manually. Missing tables or grants fail closed with an error.
No database connections, cloud invocation, or SQL application were used for local verification.

Verified Cognito email resolves exactly one `admins` row and its `admin_roles` role; client
role claims do not grant privileges. Student own-record operations remain student-only and
are outside this administrator matrix. Public program lookups and own profile/avatar actions
remain outside the matrix. There are no new student administration CRUD endpoints.

| Action | Required administrator grants |
| --- | --- |
| List/get student | students/read |
| Import student CSV | students/upload and students/insert |
| List/get assessment | assessments/read |
| Change counseling status or existing email stub | assessments/update |
| Dashboard aggregates | dashboard/read |
| Named student's dashboard assessment trend | dashboard/read and assessments/read |
| Browser report page/export | reports/read and reports/download, plus source endpoint grants |
| View/edit permission matrix | permissions/read or permissions/update, and database su_admin role |

`GET /admin/permissions/me` returns `{role_id, role_name, permissions}` with permission
arrays keyed by module. `GET /admin/permissions` returns roles, modules, permission_types,
and grants. `PUT /admin/permissions/roles/{role_id}` accepts
`{grants: [{module_id, permission_type_id}]}` and replaces that role's grants atomically;
empty arrays revoke all grants, duplicate pairs collapse, and unknown identifiers are rejected.
Only `su_admin` manages the matrix; its own seeded permissions are immutable in the API to
preserve recovery access. Other roles cannot receive permission-management grants.

Read, insert, update, upload, download types are available for each module. A flag only gates
an action listed above; unsupported actions are not introduced. Browser PDF export is local,
so download grants control the UI, and cannot prevent copying already-readable information.
The status-email endpoint remains its existing placeholder and sends no real email.

## Counselor workload

Apply `sql/20260914_02_counselor_workload.sql` after the role-permissions patch and before
deploying the Counselor Workload page. It adds an assignment record per submitted assessment;
unassigned assessments have no workload row. Guidance counselors with `workload/read` and
`workload/update` can view their queue, claim an unassigned assessment, and change the state
of only their own items. `su_admin` can view all items and assign or reassign them to a
guidance counselor. The states `assigned`, `in_review`, and `completed` describe workload
progress only; they deliberately do not change the separate counseling status.

The protected routes are `GET /counselor-workload`, `POST /counselor-workload/{assessment_id}/claim`,
and `PUT /counselor-workload/{assessment_id}`. The user must manually verify the trusted
application database role can access the new RLS-enabled table. No patch application or live
database verification is performed locally.
