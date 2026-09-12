from generic_dals import BaseDAL


class AuthDAL(BaseDAL):
    def __init__(self, conn):
        super().__init__(conn, "profiles")

    def create_profile_on_confirm(self, user_id: str, full_name: str, is_student: bool):
        self._execute_write(
            """
            INSERT INTO profiles (id, full_name, is_student)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (user_id, full_name, is_student),
        )
