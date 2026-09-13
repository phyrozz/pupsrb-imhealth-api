from generic_dals import BaseDAL


class ScheduleAssessmentDAL(BaseDAL):
    def __init__(self, conn):
        super().__init__(conn, None)

    def get_setting(self, key: str):
        row = self._fetch_one(
            "SELECT value FROM public.settings WHERE key = %s",
            (key,),
        )
        return row["value"] if row else None

    def get_due_assessment_availability_users(
        self,
        cooldown_days: int,
        batch_size: int,
        cursor: tuple | None = None,
    ):
        """Return one stable page of students due their post-cooldown notification."""
        cursor_clause = ""
        params = [cooldown_days]
        if cursor:
            cursor_clause = """
              AND (COALESCE(ar.last_assessment_at, latest.last_assessment_at), p.id)
                    > (%s, %s)
            """
            params.extend(cursor)
        params.append(batch_size)
        return self._fetch_all(
            f"""
            WITH latest AS (
                SELECT user_id, MAX(created_at) AS last_assessment_at
                FROM public.assessments
                GROUP BY user_id
            )
            SELECT p.id AS user_id,
                   pd.email,
                   pd.first_name,
                   COALESCE(ar.last_assessment_at, latest.last_assessment_at) AS last_assessment_at
            FROM public.profiles p
            JOIN latest ON latest.user_id = p.id
            JOIN public.personal_details pd ON pd.user_id = p.id
            LEFT JOIN public.assessment_reminders ar ON ar.id = p.id
            WHERE p.is_student = true
              AND (ar.id IS NULL OR ar.reminder_sent = false)
              AND COALESCE(ar.last_assessment_at, latest.last_assessment_at)
                    <= now() - make_interval(days => %s)
              {cursor_clause}
            ORDER BY COALESCE(ar.last_assessment_at, latest.last_assessment_at), p.id
            LIMIT %s
            """,
            tuple(params),
        )

    def mark_assessment_availability_notification_sent(self, user_id, last_assessment_at):
        """Mark the notification only when this is still the student's latest reminder row."""
        return self.db.execute_modification(
            """
            INSERT INTO public.assessment_reminders
                (id, last_assessment_at, reminder_sent, unanswered_reminder_sent)
            VALUES (%s, %s, true, false)
            ON CONFLICT (id) DO UPDATE
            SET reminder_sent = true
            WHERE assessment_reminders.last_assessment_at = EXCLUDED.last_assessment_at
            """,
            (user_id, last_assessment_at),
            autocommit=True,
        )
