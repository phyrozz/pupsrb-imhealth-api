import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from utils.admin_permissions import require_permission
from utils.response import success, error
from utils.request import get_body, get_path_param, get_cognito_user_id, is_admin
from generic_dals.assessments_dal import AssessmentsDAL


def handler(event, context):
    user_id = get_cognito_user_id(event)
    if not user_id:
        return error("Unauthorized", 401)
    if not is_admin(event):
        return error("Forbidden", 403)

    assessment_id = get_path_param(event, "assessment_id")
    body = get_body(event)
    counseling_status_id = body.get("counseling_status_id")
    if counseling_status_id is None:
        return error("counseling_status_id is required", 400)

    conn = get_db_connection()
    try:
        denied = require_permission(event, conn, "assessments", "update")
        if denied:
            return denied
        updated = AssessmentsDAL(conn).update_counseling_status(assessment_id, counseling_status_id)
        if not updated:
            return error("Apriori result not found", 404)
        return success(dict(updated))
    except Exception as e:
        return error(str(e))
    finally:
        conn.close()
