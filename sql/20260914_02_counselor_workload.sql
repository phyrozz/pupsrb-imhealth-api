-- Purpose: counselor-owned assessment workload queue. Required by the counselor-workload API and admin page.
-- Prerequisites: apply 20260914_01_admin_module_permissions.sql first. public.assessments,
-- public.admins, and public.admin_roles must match legacy/postgres_schema.sql. The API uses
-- verified Cognito email -> public.admins and does not depend on auth.* or Supabase helpers.
-- Apply manually after patch 01 and before deploying this feature. This additive change does
-- not alter assessment answers, existing counseling status, student records, or assignments.
-- Rerunnable: all objects and grants use IF NOT EXISTS/conflict guards. Small DDL locks only.
BEGIN;

CREATE TABLE IF NOT EXISTS public.assessment_workload (
  assessment_id uuid PRIMARY KEY REFERENCES public.assessments(id) ON DELETE CASCADE,
  assigned_admin_id uuid NOT NULL REFERENCES public.admins(id) ON DELETE RESTRICT,
  status text NOT NULL DEFAULT 'assigned' CHECK (status IN ('assigned', 'in_review', 'completed')),
  assigned_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS assessment_workload_assignee_status_idx
  ON public.assessment_workload (assigned_admin_id, status, assigned_at);
ALTER TABLE public.assessment_workload ENABLE ROW LEVEL SECURITY;

INSERT INTO public.admin_modules (module_key, module_name)
VALUES ('workload', 'Counselor Workload')
ON CONFLICT (module_key) DO NOTHING;

INSERT INTO public.admin_role_permissions (role_id, module_id, permission_type_id)
SELECT r.id, m.id, t.id
FROM public.admin_roles r
JOIN public.admin_modules m ON m.module_key = 'workload'
JOIN public.admin_permission_types t ON t.permission_key IN ('read', 'update')
WHERE r.role_name IN ('guidance_counselor', 'su_admin')
ON CONFLICT DO NOTHING;

COMMIT;

-- Manual verification:
-- SELECT r.role_name, m.module_key, t.permission_key FROM public.admin_role_permissions g
-- JOIN public.admin_roles r ON r.id=g.role_id JOIN public.admin_modules m ON m.id=g.module_id
-- JOIN public.admin_permission_types t ON t.id=g.permission_type_id WHERE m.module_key='workload';
-- SELECT status, count(*) FROM public.assessment_workload GROUP BY status;
-- Confirm the trusted Lambda database role can access this RLS-enabled table.
-- Rollback: deploy the prior API/web first; then DROP TABLE public.assessment_workload and
-- delete the workload rows from public.admin_role_permissions and public.admin_modules. This
-- discards only workload assignments and states, not assessments or student data.
