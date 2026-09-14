import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.request import is_student
from utils.db import get_db_connection
from utils.response import success, error
from utils.request import get_authenticated_username, get_body, get_cognito_user_id
from generic_dals.personal_details_dal import PersonalDetailsDAL
from generic_dals.profiles_dal import ProfilesDAL

ALLOWED_FIELDS = (
    "email", "first_name", "middle_name", "last_name", "name_suffix",
    "student_number", "birth_date", "program_id", "year",
    "marital_status_id", "is_working_student",
)


def handler(event, context):
    user_id = get_cognito_user_id(event)
    username = get_authenticated_username(event)
    if not user_id or not username:
        return error("Unauthorized", 401)

    if not is_student(event):
        return error("Forbidden", 403)
    body = get_body(event)
    data = {k: v for k, v in body.items() if k in ALLOWED_FIELDS}
    if not data:
        return error("No valid fields to update", 400)

    conn = get_db_connection()
    try:
        profile = ProfilesDAL(conn).get_by_username(username)
        if not profile:
            return error("Account profile is not ready. Please sign in again.", 409)
        data.pop("email", None)
        row = PersonalDetailsDAL(conn).update_by_user_id(profile["id"], data)
        if not row:
            return error("Personal details not found", 404)
        return success(dict(row))
    except Exception as e:
        conn.rollback()
        return error(str(e))
    finally:
        conn.close()
