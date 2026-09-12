from generic_dals import BaseDAL
from generic_dals.profiles_dal import ProfilesDAL


class AuthDAL(BaseDAL):
    def __init__(self, conn):
        super().__init__(conn, "profiles")

    def create_profile_on_confirm(self, email: str, is_student: bool):
        """Create or refresh the internal profile associated with a Cognito email."""
        return ProfilesDAL(self.db).ensure_email_profile(email, is_student)
