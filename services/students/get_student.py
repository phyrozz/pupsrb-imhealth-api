import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from utils.response import success, error
from utils.request import get_path_param, get_cognito_user_id, is_admin
from generic_dals.personal_details_dal import PersonalDetailsDAL


def handler(event, context):
    user_id = get_cognito_user_id(event)
    if not user_id:
        return error("Unauthorized", 401)
    if not is_admin(event):
        return error("Forbidden", 403)

    conn = get_db_connection()
    try:
        student = PersonalDetailsDAL(conn).get_by_user_id(get_path_param(event, "user_id"))
        if not student:
            return error("Student not found", 404)
        return success(dict(student))
    except Exception as e:
        return error(str(e))
    finally:
        conn.close()
