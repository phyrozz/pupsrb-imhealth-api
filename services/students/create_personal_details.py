import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from utils.response import success, error
from utils.request import get_body, get_cognito_user_id
from generic_dals.personal_details_dal import PersonalDetailsDAL


def handler(event, context):
    user_id = get_cognito_user_id(event)
    if not user_id:
        return error("Unauthorized", 401)

    body = get_body(event)
    body["user_id"] = user_id

    missing = [f for f in ("email", "first_name", "last_name", "student_number", "birth_date", "year") if not body.get(f)]
    if missing:
        return error(f"Missing required fields: {missing}", 400)

    conn = get_db_connection()
    try:
        row = PersonalDetailsDAL(conn).create(body)
        return success(dict(row), 201)
    except Exception as e:
        conn.rollback()
        return error(str(e))
    finally:
        conn.close()
