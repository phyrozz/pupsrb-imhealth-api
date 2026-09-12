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
