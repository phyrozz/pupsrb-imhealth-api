from generic_dals import BaseDAL


class AssessmentsDAL(BaseDAL):
    def __init__(self, conn):
        super().__init__(conn, "assessments")

    def create_assessment(self, user_id: str, responses: list, scenario_id: int) -> dict:
        assessment = self.db.execute_modification_returning_one(
            "INSERT INTO assessments (user_id, responses) VALUES (%s, %s) RETURNING *",
            (user_id, responses),
            autocommit=False,
        )
        apriori = self.db.execute_modification_returning_one(
            "INSERT INTO apriori_results (assessment_id, user_id, apriori_result) VALUES (%s, %s, %s) RETURNING *",
            (assessment["id"], user_id, scenario_id),
            autocommit=False,
        )
        self.db.execute_modification(
            """
            INSERT INTO assessment_reminders (id, last_assessment_at, reminder_sent, unanswered_reminder_sent)
            VALUES (%s, now(), false, false)
            ON CONFLICT (id) DO UPDATE
            SET last_assessment_at = now(), reminder_sent = false, unanswered_reminder_sent = false
            """,
            (user_id,),
            autocommit=False,
        )
        self.db.commit()
        return {"assessment": assessment, "apriori_result": apriori}

    def get_latest_responses(self, user_id: str):
        row = self._fetch_one(
            "SELECT responses FROM assessments WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        )
        return row["responses"] if row else None

    def acquire_submission_lock(self, user_id: str):
        """Serialize one student's submissions inside the current transaction."""
        self._fetch_one(
            "SELECT pg_advisory_xact_lock(hashtext(%s)) AS locked",
            (str(user_id),),
        )

    def get_cooldown_days(self):
        row = self._fetch_one(
            "SELECT value FROM public.settings WHERE key = %s",
            ("assessment_cooldown_days",),
        )
        return row["value"] if row else None

    def get_next_submission_at(self, user_id: str, cooldown_days: int):
        row = self._fetch_one(
            """
            SELECT MAX(created_at) + make_interval(days => %s) AS next_available_at
            FROM public.assessments
            WHERE user_id = %s
            """,
            (cooldown_days, user_id),
        )
        return row["next_available_at"] if row else None

    def list_assessments(self, search, scenario, status, user_id, page_size, page):
        """Return submitted assessments without relying on a mutable SQL function.

        The legacy table function used inner joins for the result and personal-details
        rows.  That made a successfully inserted assessment invisible while either
        companion row was absent (for example during test-student setup).  The
        assessment itself is the list's source of truth, so optional display data is
        joined with LEFT JOINs instead.
        """
        return self._fetch_all(
            """
            SELECT
                COUNT(*) OVER () AS total_count,
                a.id,
                a.created_at,
                a.user_id,
                COALESCE(pd.first_name, p.full_name, '') AS first_name,
                COALESCE(pd.middle_name, '') AS middle_name,
                COALESCE(pd.last_name, '') AS last_name,
                COALESCE(pd.name_suffix, '') AS name_suffix,
                COALESCE(pd.student_number, '') AS student_number,
                COALESCE(s.name, 'Unclassified') AS result_scenario,
                ar.apriori_result AS result_scenario_id,
                COALESCE(cs.name, '') AS counseling_status,
                ar.counseling_status_id,
                COALESCE(program.initial, '') AS program_initial,
                pd.year,
                COALESCE(pd.email, p.username, '') AS email,
                pd.birth_date,
                COALESCE(marital_status.status, '') AS marital_status,
                COALESCE(pd.is_working_student, false) AS is_working_student
            FROM public.assessments a
            LEFT JOIN public.apriori_results ar ON ar.assessment_id = a.id
            LEFT JOIN public.personal_details pd ON pd.user_id = a.user_id
            LEFT JOIN public.profiles p ON p.id = a.user_id
            LEFT JOIN public.assessment_scenarios s ON s.id = ar.apriori_result
            LEFT JOIN public.counseling_statuses cs ON cs.id = ar.counseling_status_id
            LEFT JOIN public.programs program ON program.id = pd.program_id
            LEFT JOIN public.marital_statuses marital_status ON marital_status.id = pd.marital_status_id
            WHERE (
                %s = '' OR concat_ws(' ', pd.first_name, pd.middle_name,
                pd.last_name, pd.name_suffix, pd.student_number, p.full_name,
                p.username) ILIKE '%%' || %s || '%%'
            )
              AND (%s = '' OR s.name = %s)
              AND (%s = '' OR COALESCE(cs.name, '') = %s)
              AND (%s IS NULL OR a.user_id = %s)
            ORDER BY a.created_at DESC, a.id DESC
            OFFSET %s
            LIMIT %s
            """,
            (
                search, search, scenario, scenario, status, status, user_id, user_id,
                (page - 1) * page_size, page_size,
            ),
        )

    def get_assessment_trend(self, scenario):
        return self._fetch_all("SELECT * FROM get_answered_assessments_trend(%s)", (scenario,))

    def get_apriori_result(self, assessment_id, user_id):
        return self._fetch_one(
            """
            SELECT ar.*, s.name AS scenario_name, cs.name AS counseling_status
            FROM apriori_results ar
            JOIN assessment_scenarios s ON s.id = ar.apriori_result
            LEFT JOIN counseling_statuses cs ON cs.id = ar.counseling_status_id
            WHERE ar.assessment_id = %s AND (ar.user_id = %s OR EXISTS (
                SELECT 1 FROM admins WHERE lower(email) = lower(
                    (SELECT email FROM personal_details WHERE user_id = %s)
                )
            ))
            """,
            (assessment_id, user_id, user_id),
        )

    def update_counseling_status(self, assessment_id, counseling_status_id):
        return self._execute_write(
            "UPDATE apriori_results SET counseling_status_id = %s WHERE assessment_id = %s RETURNING *",
            (counseling_status_id, assessment_id),
        )
