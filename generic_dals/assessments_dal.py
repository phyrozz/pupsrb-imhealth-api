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

    def list_assessments(self, search, scenario, status, page_size, page):
        return self._fetch_all(
            "SELECT * FROM get_assessments_table(%s, %s, %s, %s, %s)",
            (search, scenario, status, page_size, page),
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
