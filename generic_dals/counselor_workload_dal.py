from generic_dals import BaseDAL


class CounselorWorkloadDAL(BaseDAL):
    def __init__(self, conn):
        super().__init__(conn, "public.assessment_workload")

    def list_items(self, admin_id, scope, page=1, page_size=30):
        clauses = {"mine": "w.assigned_admin_id = %s", "unassigned": "w.assessment_id IS NULL"}
        where = clauses.get(scope, "true")
        params = () if scope in ("all", "unassigned") else (admin_id,)
        params += (page_size + 1, (page - 1) * page_size)
        return self._fetch_all(
            f"""
            WITH assessment_history AS (
                SELECT a.id, a.user_id, a.created_at,
                       ar.apriori_result AS scenario_id,
                       LAG(ar.apriori_result) OVER (
                           PARTITION BY a.user_id ORDER BY a.created_at, a.id
                       ) AS previous_scenario_id
                FROM public.assessments a
                LEFT JOIN public.apriori_results ar ON ar.assessment_id = a.id
            )
            SELECT a.id AS assessment_id, a.created_at, a.user_id,
                   COALESCE(pd.first_name, p.full_name, '') AS first_name,
                   COALESCE(pd.middle_name, '') AS middle_name,
                   COALESCE(pd.last_name, '') AS last_name,
                   COALESCE(pd.name_suffix, '') AS name_suffix,
                   COALESCE(pd.student_number, '') AS student_number,
                   COALESCE(pd.email, p.username, '') AS email,
                   COALESCE(program.initial, '') AS program_initial,
                   pd.year, pd.birth_date,
                   COALESCE(marital_status.status, '') AS marital_status,
                   COALESCE(pd.is_working_student, false) AS is_working_student,
                   COALESCE(s.name, 'Unclassified') AS result_scenario,
                   previous_s.name AS previous_scenario,
                   (a.previous_scenario_id IS NOT NULL AND a.scenario_id IS NOT NULL
                    AND a.scenario_id > a.previous_scenario_id) AS scenario_increased,
                   w.status AS workload_status, w.assigned_at, w.updated_at,
                   w.assigned_admin_id, assignee.email AS assigned_to
            FROM assessment_history a
            LEFT JOIN public.assessment_workload w ON w.assessment_id = a.id
            LEFT JOIN public.admins assignee ON assignee.id = w.assigned_admin_id
            LEFT JOIN public.personal_details pd ON pd.user_id = a.user_id
            LEFT JOIN public.profiles p ON p.id = a.user_id
            LEFT JOIN public.programs program ON program.id = pd.program_id
            LEFT JOIN public.marital_statuses marital_status ON marital_status.id = pd.marital_status_id
            LEFT JOIN public.assessment_scenarios s ON s.id = a.scenario_id
            LEFT JOIN public.assessment_scenarios previous_s ON previous_s.id = a.previous_scenario_id
            WHERE {where}
            ORDER BY scenario_increased DESC, a.created_at ASC, a.id ASC
            LIMIT %s OFFSET %s
            """,
            params,
        )

    def counselors(self):
        return self._fetch_all(
            "SELECT a.id, a.email FROM public.admins a JOIN public.admin_roles r ON r.id = a.role_id WHERE r.role_name = %s ORDER BY a.email",
            ("guidance_counselor",),
        )

    def can_view_assessment(self, assessment_id, admin_id):
        row = self._fetch_one(
            """
            SELECT EXISTS (
                SELECT 1
                FROM public.assessments a
                LEFT JOIN public.assessment_workload w ON w.assessment_id = a.id
                WHERE a.id = %s
                  AND (w.assessment_id IS NULL OR w.assigned_admin_id = %s)
            ) AS allowed
            """,
            (assessment_id, admin_id),
        )
        return bool(row and row["allowed"])

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
