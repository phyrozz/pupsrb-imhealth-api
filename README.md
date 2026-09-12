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
