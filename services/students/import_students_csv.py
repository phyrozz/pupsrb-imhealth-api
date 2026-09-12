import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from utils.response import success, error
from utils.request import get_body, get_cognito_user_id, is_admin
from generic_dals.personal_details_dal import PersonalDetailsDAL


def handler(event, context):
    user_id = get_cognito_user_id(event)
    if not user_id:
        return error("Unauthorized", 401)
    if not is_admin(event):
        return error("Forbidden", 403)

    conn = get_db_connection()
    try:
        dal = PersonalDetailsDAL(conn)
        if not dal.is_admin(user_id):
            return error("Forbidden", 403)

        body = get_body(event)
        csv_data = body.get("csv", "")
        if not csv_data:
            return error("csv field is required", 400)

        result = dal.import_csv(csv_data)
        return success(result)
    except Exception as e:
        conn.rollback()
        return error(str(e))
    finally:
        conn.close()
