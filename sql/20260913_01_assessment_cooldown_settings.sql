-- Purpose: configure the minimum time between completed student assessments.
-- The assessments service reads settings.assessment_cooldown_days for every
-- submission. The initial value is seven days and may be changed to fourteen
-- days later without redeploying the service.
--
-- Prerequisites: apply after 20260912_01_internal_profile_identity.sql if both
-- patches are used. This patch has no Supabase auth dependency.
--
-- Impact: brief locks only while creating the small settings table. No existing
-- student, assessment, or health data is changed. Safe to rerun; it never
-- overwrites an administrator's later setting value.

BEGIN;

CREATE TABLE IF NOT EXISTS public.settings (
  key text PRIMARY KEY,
  value text NOT NULL,
  description text NOT NULL DEFAULT '',
  updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.settings (key, value, description)
VALUES (
  'assessment_cooldown_days',
  '7',
  'Minimum whole days a student must wait after submitting an assessment.'
)
ON CONFLICT (key) DO NOTHING;

COMMIT;

-- Manual verification (run separately):
-- SELECT key, value, description FROM public.settings
-- WHERE key = 'assessment_cooldown_days';
--
-- To change the cooldown after review, run manually:
-- UPDATE public.settings
-- SET value = '14', updated_at = now()
-- WHERE key = 'assessment_cooldown_days';
--
-- Rollback: DROP TABLE public.settings only if no other application setting has
-- been added. Removing only this setting makes the API reject new assessments
-- until it is restored.
