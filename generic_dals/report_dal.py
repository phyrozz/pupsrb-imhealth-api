"""Read-only, batched report queries against the schema baseline."""
from generic_dals import BaseDAL


class ReportDAL(BaseDAL):
    def __init__(self, conn):
        super().__init__(conn, None)

    def get_setting(self, key: str):
        """Return one application setting without exposing settings to the report request."""
        row = self._fetch_one(
            "SELECT value FROM public.settings WHERE key = %s",
            (key,),
        )
        return row["value"] if row else None

    def get_report_batch(self, filters: dict, batch_size: int, cursor=None):
        """Fetch one newest-first page using a stable assessment keyset."""
        clauses = ["TRUE"]
        params = []

        if filters.get("programs"):
            clauses.append("program.initial = ANY(%s)")
            params.append(filters["programs"])
        if filters.get("years"):
            clauses.append("pd.year = ANY(%s)")
            params.append(filters["years"])
        if filters.get("counseling_status_ids"):
            clauses.append("ar.counseling_status_id = ANY(%s)")
            params.append(filters["counseling_status_ids"])
        if filters.get("scenario_ids"):
            clauses.append("ar.apriori_result = ANY(%s)")
            params.append(filters["scenario_ids"])
        if filters.get("start_date"):
            clauses.append("a.created_at >= %s::date")
            params.append(filters["start_date"])
        if filters.get("end_date"):
            clauses.append("a.created_at < (%s::date + INTERVAL '1 day')")
            params.append(filters["end_date"])
        if filters.get("user_id"):
            clauses.append("a.user_id = %s")
            params.append(filters["user_id"])
        if cursor is not None:
            clauses.append("(a.created_at, a.id) < (%s, %s)")
            params.extend(cursor)
        params.append(batch_size)

        return self._fetch_all(
            f"""
            SELECT
                a.id AS assessment_id,
                a.created_at AS submitted_at,
                a.user_id,
                COALESCE(NULLIF(concat_ws(' ', pd.first_name, pd.middle_name,
                    pd.last_name, pd.name_suffix), ''), p.full_name, '') AS student_name,
                COALESCE(pd.student_number, '') AS student_number,
                COALESCE(pd.email, p.username, '') AS student_email,
                COALESCE(program.initial, '') AS program_initial,
                COALESCE(program.name, '') AS program_name,
                pd.year AS year_level,
                ar.apriori_result AS scenario_id,
                COALESCE(scenario.name, 'Unclassified') AS scenario_name,
                ar.counseling_status_id,
                COALESCE(status.name, '') AS counseling_status
            FROM public.assessments a
            LEFT JOIN public.apriori_results ar ON ar.assessment_id = a.id
            LEFT JOIN public.personal_details pd ON pd.user_id = a.user_id
            LEFT JOIN public.profiles p ON p.id = a.user_id
            LEFT JOIN public.programs program ON program.id = pd.program_id
            LEFT JOIN public.assessment_scenarios scenario ON scenario.id = ar.apriori_result
            LEFT JOIN public.counseling_statuses status ON status.id = ar.counseling_status_id
            WHERE {' AND '.join(clauses)}
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT %s
            """,
            tuple(params),
        )
