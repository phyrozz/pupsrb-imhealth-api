from generic_dals import BaseDAL


class AdminUsersDAL(BaseDAL):
    def __init__(self, conn):
        super().__init__(conn, "public.admins")

    def roles(self):
        return self._fetch_all("SELECT id, role_name FROM public.admin_roles ORDER BY id")

    def list_admins(self):
        return self._fetch_all(
            "SELECT a.id, a.email, a.role_id, r.role_name, a.created_at, a.updated_at "
            "FROM public.admins a JOIN public.admin_roles r ON r.id = a.role_id ORDER BY lower(a.email)"
        )

    def role_exists(self, role_id):
        return self._fetch_one("SELECT id, role_name FROM public.admin_roles WHERE id = %s", (role_id,))

    def email_exists(self, email):
        return self._fetch_one("SELECT id FROM public.admins WHERE lower(email) = lower(%s)", (email,))

    def create(self, email, role_id):
        return self._execute_write(
            "INSERT INTO public.admins (email, role_id) VALUES (%s, %s) RETURNING id, email, role_id, created_at, updated_at",
            (email, role_id),
        )
