from generic_dals import BaseDAL


class CronDAL(BaseDAL):
    def __init__(self, conn):
        super().__init__(conn, None)

    def lock_trend_snapshot(self):
        self._fetch_one("SELECT pg_advisory_xact_lock(hashtext('mental_health_trend_snapshot'))")

    def get_scenario_change_counts(self):
        return self._fetch_one(
            """SELECT
                (SELECT count FROM public.count_scenario_increase()) AS increase_count,
                (SELECT count FROM public.count_scenario_decrease()) AS decrease_count
            """
        )

    def insert_mental_health_uptrend(self, count, day_start, next_day_start):
        self.db.execute_modification(
            """
            INSERT INTO public.mental_health_uptrend (count)
            SELECT %s
            WHERE NOT EXISTS (
                SELECT 1 FROM public.mental_health_uptrend
                WHERE created_at >= %s AND created_at < %s
            )
            """,
            (count, day_start, next_day_start),
            autocommit=False,
        )

    def insert_mental_health_downtrend(self, count, day_start, next_day_start):
        self.db.execute_modification(
            """
            INSERT INTO public.mental_health_downtrend (count)
            SELECT %s
            WHERE NOT EXISTS (
                SELECT 1 FROM public.mental_health_downtrend
                WHERE created_at >= %s AND created_at < %s
            )
            """,
            (count, day_start, next_day_start),
            autocommit=False,
        )

    def commit(self):
        self.db.commit()
