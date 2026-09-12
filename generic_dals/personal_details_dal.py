import csv
import io
from generic_dals import BaseDAL


class PersonalDetailsDAL(BaseDAL):
    def __init__(self, conn):
        super().__init__(conn, "personal_details")

    def get_by_user_id(self, user_id: str):
        return self._fetch_one(
            """
            SELECT pd.*, p.initial AS program_initial, p.name AS program_name,
                   ms.status AS marital_status
            FROM personal_details pd
            LEFT JOIN programs p ON p.id = pd.program_id
            LEFT JOIN marital_statuses ms ON ms.id = pd.marital_status_id
            WHERE pd.user_id = %s
            """,
            (user_id,),
        )

    def list_students(self, result_count, program, search, page_size, page):
        return self._fetch_all(
            "SELECT * FROM get_users_with_multiple_assessments(%s, %s, %s, %s, %s)",
            (result_count, program, search, page_size, page),
        )

    def create(self, data: dict):
        return self.insert(data)

    def update_by_user_id(self, user_id: str, data: dict):
        return self.update("user_id", user_id, data)

    def is_admin(self, user_id: str) -> bool:
        return self._fetch_one(
            "SELECT 1 FROM admins a JOIN profiles p ON lower(p.id::text) = lower(a.id::text) WHERE p.id = %s",
            (user_id,),
        ) is not None

    def import_csv(self, csv_data: str) -> dict:
        reader = csv.DictReader(io.StringIO(csv_data))
        inserted = 0
        skipped = 0
        for row in reader:
            row = {k.strip(): v.strip() for k, v in row.items() if k}
            try:
                affected = self.db.execute_modification(
                    """
                    INSERT INTO personal_details
                        (user_id, email, first_name, middle_name, last_name, name_suffix,
                         student_number, birth_date, program_id, year, marital_status_id, is_working_student)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (student_number) DO NOTHING
                    """,
                    (
                        row.get("user_id"),
                        row.get("email"),
                        row.get("first_name"),
                        row.get("middle_name") or None,
                        row.get("last_name"),
                        row.get("name_suffix") or None,
                        row.get("student_number"),
                        row.get("birth_date"),
                        row.get("program_id") or None,
                        row.get("year"),
                        row.get("marital_status_id") or None,
                        row.get("is_working_student", "false").lower() == "true",
                    ),
                    autocommit=False,
                )
                inserted += 1 if affected else 0
                skipped += 0 if affected else 1
            except Exception:
                skipped += 1
        self.db.commit()
        return {"inserted": inserted, "skipped": skipped}
