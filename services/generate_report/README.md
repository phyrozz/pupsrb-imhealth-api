# Generate report worker

`POST /generate-report` validates the authenticated administrator's request,
starts the dedicated Fargate task, and returns `202`. The worker reads
`TASK_EVENT`, queries the current PostgreSQL schema in keyset batches, renders a
PDF, CSV, or XLSX file locally, emails it to the verified Cognito email, and
deletes the temporary file.

## Request contract

```json
{
  "report_type": "program",
  "format": "xlsx",
  "filters": {
    "programs": ["BSIT-SR"],
    "years": [1, 2],
    "counseling_status_ids": [2],
    "scenario_ids": [1, 3],
    "start_date": "2026-01-01",
    "end_date": "2026-12-31",
    "recommendations": "Optional referral note"
  }
}
```

Use `report_type: "student"` with a UUID `filters.user_id`; it requires the
additional `students/read` grant. Program reports reject `user_id`.

The caller needs `reports/download` and `assessments/read`. Student reports
also need `students/read`. The recipient is never accepted in the request body;
it is the caller's verified Cognito email claim.

## Manual deployment configuration

No AWS resources, IAM policies, images, task definitions, SSM values, or
database changes were applied by this implementation. Before a manual `dev`
deployment, replace the three placeholders in `ecs-task-definition.json` with
the development ECR image and the existing development ECS execution and task
role ARNs, then register that definition.

Apply `sql/20260920_01_report_timestamp_timezone.sql` manually before deploying
the worker update. It creates the server-controlled
`settings.report_timestamp_timezone` value with an `Asia/Manila` baseline. The
worker validates it as an IANA timezone, reads it once per report, and uses that
same zone for the generated-at metadata and submitted timestamps in PDF, CSV,
and XLSX output.

The task execution role needs the same scoped SSM read access for the six
`/pupsrb-imhealth/dev/db/*` and `/pupsrb-imhealth/dev/ses/from_email`
parameters as the scheduled-assessment worker, ECR image pull access, and the
specified CloudWatch Logs group. The task role needs only the database network
path and scoped `ses:SendRawEmail` access from the configured
`SES_FROM_EMAIL`. The existing Lambda role needs scoped `ecs:RunTask` for this
task definition and `iam:PassRole` for these two ECS roles.

The ECS task definition itself obtains database and SES settings through SSM.
The Lambda uses `pass_environment=False`, so its environment is not forwarded
through an ECS override. The only override value is `TASK_EVENT`.

Amazon SES attachment size limits still apply. Very large exports may need a
narrower date range or a later object-storage delivery design.
