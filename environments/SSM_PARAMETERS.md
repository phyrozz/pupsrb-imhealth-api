# SSM Parameter Store Setup

Create the following parameters in AWS Systems Manager → Parameter Store.
Use **SecureString** type for all secrets.

Replace `{stage}` with `dev` or `prod`.

| Parameter Path | Description |
|---|---|
| `/pupsrb-imhealth/{stage}/db/host` | PostgreSQL host |
| `/pupsrb-imhealth/{stage}/db/port` | PostgreSQL port (e.g. `5432`) |
| `/pupsrb-imhealth/{stage}/db/name` | Database name |
| `/pupsrb-imhealth/{stage}/db/user` | Database user |
| `/pupsrb-imhealth/{stage}/db/password` | Database password |
| `/pupsrb-imhealth/{stage}/s3/bucket_name` | Private S3 bucket for avatars |
| `/pupsrb-imhealth/{stage}/s3/public_bucket_name` | Public S3 bucket containing the `logo.webp` email image |
| `/pupsrb-imhealth/{stage}/cognito/user_pool_id` | Cognito User Pool ID |
| `/pupsrb-imhealth/{stage}/ses/from_email` | SES sender email address |
| `/pupsrb-imhealth/{stage}/cron/secret` | Secret token for cron authorization |
