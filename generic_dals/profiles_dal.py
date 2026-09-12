import boto3
import os
from generic_dals import BaseDAL

S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "")


class ProfilesDAL(BaseDAL):
    def __init__(self, conn):
        super().__init__(conn, "profiles")

    def get_by_user_id(self, user_id: str):
        return self.find_by_id("id", user_id)

    def get_by_username(self, username: str):
        return self._fetch_one(
            "SELECT id, username, is_student FROM profiles WHERE lower(username) = lower(%s)",
            (username,),
        )

    def ensure_email_profile(self, email: str, is_student: bool = True):
        """Resolve legacy IDs by email; never use the Cognito subject as a DB ID."""
        email = email.strip().lower()
        matches = self._fetch_all(
            """
            SELECT DISTINCT p.id, p.username, p.is_student
            FROM public.profiles p
            LEFT JOIN public.personal_details pd ON pd.user_id = p.id
            WHERE lower(trim(p.username)) = %s
               OR lower(trim(pd.email)) = %s
               OR lower(trim(p.full_name)) = %s
            """,
            (email, email, email),
        )
        if len(matches) > 1:
            raise ValueError("Multiple profiles match this email; contact an administrator")
        if matches:
            profile = matches[0]
            if profile.get("username") and profile["username"].strip().lower() != email:
                raise ValueError("Profile email mapping needs administrator review")
            if profile["is_student"] != is_student:
                raise ValueError("Account is not registered for this user pool")
            return self._execute_write(
                "UPDATE public.profiles SET username = %s WHERE id = %s RETURNING id, username, is_student",
                (email, profile["id"]),
            )
        return self._execute_write(
            """
            INSERT INTO public.profiles (username, full_name, is_student)
            VALUES (%s, %s, %s)
            ON CONFLICT (lower(username)) DO UPDATE SET username = EXCLUDED.username
            WHERE profiles.is_student = EXCLUDED.is_student
            RETURNING id, username, is_student
            """,
            (email, email, is_student),
        )

    def update_profile(self, user_id: str, data: dict):
        return self.update("id", user_id, data)

    def update_avatar_url(self, user_id: str, avatar_url: str):
        return self.update("id", user_id, {"avatar_url": avatar_url})

    def generate_avatar_upload_url(self, user_id: str) -> dict:
        s3 = boto3.client("s3")
        key = f"avatars/{user_id}.jpg"
        url = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": S3_BUCKET, "Key": key, "ContentType": "image/jpeg"},
            ExpiresIn=300,
        )
        return {"upload_url": url, "key": key}

    def create_profile(self, user_id: str, full_name: str, is_student: bool):
        self._execute_write(
            """
            INSERT INTO profiles (id, full_name, is_student)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (user_id, full_name, is_student),
        )
