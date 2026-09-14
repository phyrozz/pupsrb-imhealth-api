from generic_dals import BaseDAL


class PermissionsDAL(BaseDAL):
    def __init__(self, conn):
        super().__init__(conn, "public.admin_role_permissions")

    def identity(self, email):
        rows = self._fetch_all("SELECT a.role_id, r.role_name FROM public.admins a JOIN public.admin_roles r ON r.id=a.role_id WHERE lower(trim(a.email))=%s", (email,))
        return rows[0] if len(rows) == 1 else None

    def permissions(self, role_id):
        rows = self._fetch_all("SELECT m.module_key, t.permission_key FROM public.admin_role_permissions g JOIN public.admin_modules m ON m.id=g.module_id JOIN public.admin_permission_types t ON t.id=g.permission_type_id WHERE g.role_id=%s", (role_id,))
        result = {}
        for row in rows:
            result.setdefault(row["module_key"], []).append(row["permission_key"])
        return result

    def matrix(self):
        return {
            "roles": self._fetch_all("SELECT id, role_name FROM public.admin_roles ORDER BY id"),
            "modules": self._fetch_all("SELECT id, module_key, module_name FROM public.admin_modules ORDER BY id"),
            "permission_types": self._fetch_all("SELECT id, permission_key, permission_name FROM public.admin_permission_types ORDER BY id"),
            "grants": self._fetch_all("SELECT role_id, module_id, permission_type_id FROM public.admin_role_permissions ORDER BY role_id,module_id,permission_type_id"),
        }

    def replace(self, role_id, grants):
        # Serialize replacements on the role, validate inside the same transaction.
        try:
            role = self._fetch_one("SELECT id,role_name FROM public.admin_roles WHERE id=%s FOR UPDATE", (role_id,))
            if not role:
                raise ValueError("Role not found")
            if role["role_name"] == "su_admin":
                raise ValueError("Super administrator permissions cannot be changed")
            matrix = self.matrix()
            modules = {r["id"]: r["module_key"] for r in matrix["modules"]}
            types = {r["id"] for r in matrix["permission_types"]}
            for module_id, type_id in grants:
                if module_id not in modules or type_id not in types:
                    raise ValueError("Unknown module or permission type")
                if modules[module_id] == "permissions":
                    raise ValueError("Only super administrators may manage permissions")
            self.db.execute_modification("DELETE FROM public.admin_role_permissions WHERE role_id=%s", (role_id,))
            for module_id, type_id in grants:
                self.db.execute_modification("INSERT INTO public.admin_role_permissions(role_id,module_id,permission_type_id) VALUES(%s,%s,%s)", (role_id,module_id,type_id))
            self.db.conn.commit()
        except Exception:
            self.db.conn.rollback()
            raise
