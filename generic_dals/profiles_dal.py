import boto3
import os
from generic_dals import BaseDAL

S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "")


class ProfilesDAL(BaseDAL):
    def __init__(self, conn):
        super().__init__(conn, "profiles")

    def get_by_user_id(self, user_id: str):
        return self.find_by_id("id", user_id)

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
