import sys
import os
import logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from utils.admin_permissions import require_permission
from utils.response import success, error
from utils.request import get_authenticated_username, get_body, get_cognito_user_id, is_admin
from generic_dals.personal_details_dal import PersonalDetailsDAL

logger = logging.getLogger(__name__)

def handler(event, context):
    user_id = get_cognito_user_id(event)
    if not user_id:
        return error("Unauthorized", 401)
    if not is_admin(event):
        return error("Forbidden", 403)
    email = get_authenticated_username(event)
    if not email:
        return error("Unauthorized", 401)

    conn = None
    try:
        conn = get_db_connection()
        denied = require_permission(event, conn, "students", "upload")
        if denied:
            return denied
        denied = require_permission(event, conn, "students", "insert")
        if denied:
            return denied
        dal = PersonalDetailsDAL(conn)
        if not dal.is_admin_by_email(email):
            return error("Forbidden", 403)

        body = get_body(event)
        csv_data = body.get("csv", "")
        if not csv_data:
            return error("csv field is required", 400)

        result = dal.import_csv(csv_data)
        return success(result)
    except Exception:
        logger.exception("Student CSV import failed")
        if conn is not None:
            conn.rollback()
        return error("Unable to import students. Please try again later.")
    finally:
        if conn is not None:
            conn.close()
