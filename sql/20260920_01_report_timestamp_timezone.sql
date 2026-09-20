-- Purpose: configure the timezone used for the generated-at timestamp in PDF,
-- CSV, and XLSX reports. services/generate_report/main.py reads this value as
-- public.settings.report_timestamp_timezone once for each queued report.
--
-- Prerequisites and application order: apply 20260913_01_assessment_cooldown_settings.sql
-- first, because it creates public.settings. Apply this patch manually before
-- deploying the report worker timezone enhancement. It has no Supabase auth
-- dependency and does not read or change student, assessment, or health data.
--
-- Impact: a single INSERT into a small settings table. It takes only the normal
-- row/index locks for that statement, has no planned downtime, and is safe to
-- rerun. ON CONFLICT preserves an administrator's existing configured timezone.

BEGIN;

-- This repeats the additive table definition from the prerequisite so the patch
-- remains safe if it is reviewed/applied independently.
CREATE TABLE IF NOT EXISTS public.settings (
  key text PRIMARY KEY,
  value text NOT NULL,
  description text NOT NULL DEFAULT '',
  updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.settings (key, value, description)
VALUES (
  'report_timestamp_timezone',
  'Asia/Manila',
  'IANA timezone used by generated-at timestamps in queued PDF, CSV, and XLSX reports.'
)
ON CONFLICT (key) DO NOTHING;

COMMIT;

-- Manual verification (run separately):
-- SELECT key, value, description FROM public.settings
-- WHERE key = 'report_timestamp_timezone';
--
-- To change the timezone after review, use a valid IANA ZoneInfo name, for example:
-- UPDATE public.settings
-- SET value = 'Asia/Manila', updated_at = now()
-- WHERE key = 'report_timestamp_timezone';
--
-- Rollback: after deploying a worker version that does not require this setting,
-- run the following manually. This removes only this configuration value:
-- DELETE FROM public.settings WHERE key = 'report_timestamp_timezone';
