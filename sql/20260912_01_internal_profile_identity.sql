-- Purpose: make public.profiles own internal UUIDs rather than Cognito/Supabase
-- auth.users IDs. The Cognito email is stored in profiles.username and is the
-- lookup key used by AuthDAL, personal-details, and assessment handlers.
--
-- Prerequisites: prepare API code that writes profile usernames from verified
-- Cognito email, pause signup/assessment writes during rollout. The baseline is
-- legacy/postgres_schema.sql, where pgcrypto is enabled and profiles.id has
-- DEFAULT auth.uid() plus a foreign key to auth.users(id).
--
-- Application order: this patch first, then deploy the auth, students, and
-- assessments services together. Do not run against a database without a
-- verified public.profiles table and pgcrypto extension.
--
-- Impact: brief ACCESS EXCLUSIVE locks on public.profiles while its default and
-- foreign key are changed. No rows are deleted and existing profile IDs remain.
-- Review duplicate emails before applying; ambiguous mappings abort transaction.
-- Existing blank usernames are backfilled from personal_details.email or an
-- email-shaped full_name; existing names, roles, UUIDs and health data survive.
-- New profiles receive gen_random_uuid() IDs that are intentionally distinct
-- from Cognito subjects. The statements are safe to re-run for the baseline.

BEGIN;

LOCK TABLE public.profiles IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.personal_details IN SHARE MODE;

-- Fail rather than silently select/merge two students with the same email.
DO $$
BEGIN
  IF EXISTS (
    SELECT p.id FROM public.profiles p
    JOIN public.personal_details pd ON pd.user_id = p.id
    WHERE nullif(trim(p.username), '') IS NOT NULL
      AND lower(trim(p.username)) <> lower(trim(pd.email))
  ) OR EXISTS (
    SELECT p.id FROM public.profiles p
    WHERE nullif(trim(p.username), '') IS NOT NULL
      AND trim(p.full_name) ~ '^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$'
      AND lower(trim(p.username)) <> lower(trim(p.full_name))
  ) OR EXISTS (
    SELECT p.id FROM public.profiles p
    JOIN public.personal_details pd ON pd.user_id = p.id
    WHERE trim(p.full_name) ~ '^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$'
      AND lower(trim(pd.email)) <> lower(trim(p.full_name))
  ) THEN
    RAISE EXCEPTION 'Conflicting profile email sources; resolve manually before applying identity patch';
  END IF;
  IF EXISTS (
    SELECT email FROM (
      SELECT p.id, lower(trim(p.username)) AS email FROM public.profiles p
      WHERE nullif(trim(p.username), '') IS NOT NULL
      UNION
      SELECT p.id, lower(trim(pd.email)) FROM public.profiles p
      JOIN public.personal_details pd ON pd.user_id = p.id
      UNION
      SELECT p.id, lower(trim(p.full_name)) FROM public.profiles p
      WHERE trim(p.full_name) ~ '^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$'
    ) candidates GROUP BY email HAVING count(DISTINCT id) > 1
  ) THEN
    RAISE EXCEPTION 'Ambiguous profile emails; resolve manually before applying identity patch';
  END IF;
END $$;

UPDATE public.profiles p
SET username = lower(trim(coalesce(
  (SELECT pd.email FROM public.personal_details pd WHERE pd.user_id = p.id),
  CASE WHEN trim(p.full_name) ~ '^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$'
       THEN p.full_name END
)))
WHERE nullif(trim(p.username), '') IS NULL
  AND (EXISTS (SELECT 1 FROM public.personal_details pd WHERE pd.user_id = p.id)
       OR trim(p.full_name) ~ '^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$');

UPDATE public.profiles SET username = lower(trim(username))
WHERE username IS NOT NULL AND username <> lower(trim(username));

CREATE UNIQUE INDEX IF NOT EXISTS profiles_username_lower_unique
  ON public.profiles (lower(username));

CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE public.profiles
  DROP CONSTRAINT IF EXISTS profiles_id_fkey;

ALTER TABLE public.profiles
  ALTER COLUMN id SET DEFAULT gen_random_uuid();

COMMIT;

-- Manual verification (run separately after application):
-- SELECT column_default
-- FROM information_schema.columns
-- WHERE table_schema = 'public' AND table_name = 'profiles' AND column_name = 'id';
--
-- SELECT conname
-- FROM pg_constraint
-- WHERE conrelid = 'public.profiles'::regclass AND contype = 'f';
--
-- SELECT id, username, full_name FROM public.profiles ORDER BY created_at DESC LIMIT 10;
-- SELECT lower(username), count(*) FROM public.profiles
-- WHERE username IS NOT NULL GROUP BY lower(username) HAVING count(*) > 1;
-- SELECT p.id, p.username, pd.email FROM public.profiles p
-- JOIN public.personal_details pd ON pd.user_id = p.id
-- WHERE lower(trim(p.username)) IS DISTINCT FROM lower(trim(pd.email));

-- Rollback: restoring the auth.users foreign key is unsafe until every existing
-- profile ID has a matching auth.users row. If that prerequisite is met, run:
-- BEGIN;
-- DROP INDEX IF EXISTS public.profiles_username_lower_unique;
-- ALTER TABLE public.profiles ALTER COLUMN id SET DEFAULT auth.uid();
-- ALTER TABLE public.profiles ADD CONSTRAINT profiles_id_fkey
--   FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE;
-- COMMIT;
-- Email normalization/backfill cannot be reversed without a pre-patch backup.
-- Supabase auth trigger and RLS policies using auth.uid()/auth.jwt() remain;
-- API DB role must already have trusted backend access under existing policies.
-- This patch does not grant privileges or disable RLS. New Cognito profiles are
-- independent of auth.users; old auth trigger remains for legacy compatibility.
