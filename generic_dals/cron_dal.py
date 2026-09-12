from generic_dals import BaseDAL


class CronDAL(BaseDAL):
    def __init__(self, conn):
        super().__init__(conn, None)

    def get_recent_apriori_counts(self):
        return self._fetch_all(
            """
            SELECT apriori_result, COUNT(*) AS count
            FROM apriori_results
            WHERE created_at >= now() - interval '24 hours'
            GROUP BY apriori_result
            """
        )

    def get_previous_apriori_count(self, scenario_id):
        row = self._fetch_one(
            """
            SELECT COUNT(*) AS prev_count
            FROM apriori_results
            WHERE apriori_result = %s
              AND created_at >= now() - interval '48 hours'
              AND created_at < now() - interval '24 hours'
            """,
            (scenario_id,),
        )
        return row["prev_count"] if row else 0

    def insert_mental_health_uptrend(self, scenario_id, count, snapshot_date):
        self.db.execute_modification(
            """
            INSERT INTO mental_health_uptrend (scenario_id, count, snapshot_date)
            VALUES (%s, %s, %s)
            """,
            (scenario_id, count, snapshot_date),
            autocommit=False,
        )

    def insert_mental_health_downtrend(self, scenario_id, count, snapshot_date):
        self.db.execute_modification(
            """
            INSERT INTO mental_health_downtrend (scenario_id, count, snapshot_date)
            VALUES (%s, %s, %s)
            """,
            (scenario_id, count, snapshot_date),
            autocommit=False,
        )

    def get_assessment_reminder_users(self):
        return self._fetch_all(
            """
            SELECT ar.id AS user_id, pd.email, pd.first_name
            FROM assessment_reminders ar
            JOIN personal_details pd ON pd.user_id = ar.id
            WHERE ar.reminder_sent = false
              AND ar.last_assessment_at < now() - interval '30 days'
            """
        )

    def mark_assessment_reminder_sent(self, user_id):
        self.db.execute_modification(
            "UPDATE assessment_reminders SET reminder_sent = true WHERE id = %s",
            (user_id,),
            autocommit=False,
        )

    def get_unanswered_assessment_users(self):
        return self._fetch_all(
            """
            SELECT p.id AS user_id, pd.email, pd.first_name
            FROM profiles p
            JOIN personal_details pd ON pd.user_id = p.id
            LEFT JOIN assessment_reminders ar ON ar.id = p.id
            WHERE ar.id IS NULL
              AND p.created_at < now() - interval '7 days'
            """
        )

    def mark_unanswered_reminder_sent(self, user_id):
        self.db.execute_modification(
            """
            INSERT INTO assessment_reminders (id, last_assessment_at, reminder_sent, unanswered_reminder_sent)
            VALUES (%s, now(), false, true)
            ON CONFLICT (id) DO UPDATE SET unanswered_reminder_sent = true
            """,
            (user_id,),
            autocommit=False,
        )

    def commit(self):
        self.db.commit()
