from generic_dals import BaseDAL


class CounselorWorkloadDAL(BaseDAL):
    def __init__(self, conn):
        super().__init__(conn, "public.assessment_workload")

    def list_items(self, admin_id, scope):
        clauses = {"mine": "w.assigned_admin_id = %s", "unassigned": "w.assessment_id IS NULL"}
        where = clauses.get(scope, "true")
        params = () if scope in ("all", "unassigned") else (admin_id,)
        return self._fetch_all(
            f"""
            SELECT a.id AS assessment_id, a.created_at, a.user_id,
                   COALESCE(pd.first_name, p.full_name, '') AS first_name,
                   COALESCE(pd.last_name, '') AS last_name, COALESCE(pd.student_number, '') AS student_number,
                   COALESCE(s.name, 'Unclassified') AS result_scenario,
                   w.status AS workload_status, w.assigned_at, w.updated_at,
                   w.assigned_admin_id, assignee.email AS assigned_to
            FROM public.assessments a
            LEFT JOIN public.assessment_workload w ON w.assessment_id = a.id
            LEFT JOIN public.admins assignee ON assignee.id = w.assigned_admin_id
            LEFT JOIN public.personal_details pd ON pd.user_id = a.user_id
            LEFT JOIN public.profiles p ON p.id = a.user_id
            LEFT JOIN public.apriori_results ar ON ar.assessment_id = a.id
            LEFT JOIN public.assessment_scenarios s ON s.id = ar.apriori_result
            WHERE {where}
            ORDER BY a.created_at ASC, a.id ASC
            """,
            params,
        )

    def counselors(self):
        return self._fetch_all(
            "SELECT a.id, a.email FROM public.admins a JOIN public.admin_roles r ON r.id = a.role_id WHERE r.role_name = %s ORDER BY a.email",
            ("guidance_counselor",),
        )

    def claim(self, assessment_id, admin_id):
        return self._execute_write(
            """
            INSERT INTO public.assessment_workload (assessment_id, assigned_admin_id, status)
            SELECT a.id, %s, 'assigned' FROM public.assessments a WHERE a.id = %s
            ON CONFLICT (assessment_id) DO NOTHING
            RETURNING *
            """,
            (admin_id, assessment_id),
        )

    def update_mine(self, assessment_id, admin_id, status):
        return self._execute_write(
            "UPDATE public.assessment_workload SET status = %s WHERE assessment_id = %s AND assigned_admin_id = %s RETURNING *",
            (status, assessment_id, admin_id),
        )

    def manage(self, assessment_id, assigned_admin_id, status):
        return self._execute_write(
            """
            INSERT INTO public.assessment_workload (assessment_id, assigned_admin_id, status)
            SELECT a.id, assignee.id, %s
            FROM public.assessments a
            JOIN public.admins assignee ON assignee.id = %s
            JOIN public.admin_roles role ON role.id = assignee.role_id AND role.role_name = 'guidance_counselor'
            WHERE a.id = %s
            ON CONFLICT (assessment_id) DO UPDATE SET assigned_admin_id = EXCLUDED.assigned_admin_id, status = EXCLUDED.status
            RETURNING *
            """,
            (status, assigned_admin_id, assessment_id),
        )
