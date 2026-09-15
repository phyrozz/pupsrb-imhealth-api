-- Purpose: add the Admin Users permission module used to list and create administrator accounts.
-- Prerequisites: apply 20260914_01_admin_module_permissions.sql first. public.admins and
-- public.admin_roles are the legacy baseline tables; this patch adds no auth.* dependency.
-- Apply manually before deploying the Admin Users API/web. The Lambda execution role must
-- separately be granted cognito-idp:AdminCreateUser and cognito-idp:AdminDeleteUser for the
-- configured administrator user pool; this patch cannot grant AWS IAM permissions.
-- Safe to rerun. It changes no existing users, roles, permission removals, or student data.
BEGIN;

INSERT INTO public.admin_modules (module_key, module_name)
VALUES ('admin_users', 'Admin Users')
ON CONFLICT (module_key) DO NOTHING;

INSERT INTO public.admin_role_permissions (role_id, module_id, permission_type_id)
SELECT r.id, m.id, t.id
FROM public.admin_roles r
JOIN public.admin_modules m ON m.module_key = 'admin_users'
JOIN public.admin_permission_types t ON t.permission_key IN ('read', 'insert', 'update', 'upload', 'download')
WHERE r.role_name = 'su_admin'
ON CONFLICT DO NOTHING;

COMMIT;

-- Manual verification:
-- SELECT r.role_name, m.module_key, t.permission_key FROM public.admin_role_permissions g
-- JOIN public.admin_roles r ON r.id=g.role_id JOIN public.admin_modules m ON m.id=g.module_id
-- JOIN public.admin_permission_types t ON t.id=g.permission_type_id WHERE m.module_key='admin_users';
-- Confirm the Lambda execution role has only the two required Cognito administrator actions
-- against this application's administrator user pool before deploying.
-- Rollback: deploy prior API/web code, then delete only admin_users grants and module rows.
-- This does not remove Cognito accounts or public.admins records created through the module.
