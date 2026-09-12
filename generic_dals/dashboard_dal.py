from generic_dals import BaseDAL


class DashboardDAL(BaseDAL):
    def __init__(self, conn):
        super().__init__(conn, None)

    def get_stats(self) -> dict:
        students = self._fetch_one("SELECT * FROM count_students()")
        working = self._fetch_one("SELECT * FROM count_working_student()")
        increase = self._fetch_one("SELECT * FROM count_scenario_increase()")
        decrease = self._fetch_one("SELECT * FROM count_scenario_decrease()")
        return {
            "total_students": students["total"],
            "answered_assessments_total": students["answered_assessments_total"],
            "working_student_count": working["count"],
            "working_student_total": working["total"],
            "scenario_increase_count": increase["count"],
            "scenario_decrease_count": decrease["count"],
        }

    def get_scenario_chart(self):
        return self._fetch_all("SELECT * FROM count_apriori_results_by_scenario()")

    def get_program_chart(self):
        return self._fetch_all("SELECT * FROM count_students_by_program()")

    def get_assessment_trend(self, scenario):
        return self._fetch_all("SELECT * FROM get_answered_assessments_trend(%s)", (scenario,))

    def get_mental_health_trend(self) -> dict:
        uptrend = self._fetch_all("SELECT count, created_at FROM mental_health_uptrend ORDER BY created_at")
        downtrend = self._fetch_all("SELECT count, created_at FROM mental_health_downtrend ORDER BY created_at")
        return {"uptrend": uptrend, "downtrend": downtrend}

    def get_student_assessment_trend(self, user_id):
        return self._fetch_all("SELECT * FROM get_answered_assessments_trend_by_student(%s)", (user_id,))
