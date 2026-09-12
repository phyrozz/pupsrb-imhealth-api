import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from utils.response import success, error
from utils.request import get_query_param, get_cognito_user_id, is_admin
from generic_dals.dashboard_dal import DashboardDAL


def handler(event, context):
    user_id = get_cognito_user_id(event)
    if not user_id:
        return error("Unauthorized", 401)
    if not is_admin(event):
        return error("Forbidden", 403)

    scenario = get_query_param(event, "scenario", "")

    conn = get_db_connection()
    try:
        rows = DashboardDAL(conn).get_assessment_trend(scenario)
        return success([dict(r) for r in rows])
    except Exception as e:
        return error(str(e))
    finally:
        conn.close()
