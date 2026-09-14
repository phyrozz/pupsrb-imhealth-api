import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.admin_permissions import require_permission
from utils.request import get_authenticated_username, is_student
from generic_dals.profiles_dal import ProfilesDAL
from utils.db import get_db_connection
from utils.response import success, error
from utils.request import get_path_param, get_cognito_user_id
from generic_dals.assessments_dal import AssessmentsDAL


def handler(event, context):
    user_id = get_cognito_user_id(event)
    username = get_authenticated_username(event)
    if not user_id or not username:
        return error("Unauthorized", 401)

    assessment_id = get_path_param(event, "assessment_id")

    conn = get_db_connection()
    try:
        if is_student(event):
            profile = ProfilesDAL(conn).get_by_username(username)
            if not profile or not profile.get("is_student"):
                return error("Forbidden", 403)
            result = AssessmentsDAL(conn).get_apriori_result(assessment_id, profile["id"])
        else:
            denied = require_permission(event, conn, "assessments", "read")
            if denied:
                return denied
            result = AssessmentsDAL(conn).get_apriori_result(assessment_id, None, admin=True)
        if not result:
            return error("Apriori result not found", 404)
        return success(dict(result))
    except Exception as e:
        return error(str(e))
    finally:
        conn.close()
