import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from utils.admin_permissions import require_permission
from utils.response import success, error
from utils.request import get_cognito_user_id, is_admin
from generic_dals.dashboard_dal import DashboardDAL


def handler(event, context):
    user_id = get_cognito_user_id(event)
    if not user_id:
        return error("Unauthorized", 401)
    if not is_admin(event):
        return error("Forbidden", 403)

    conn = get_db_connection()
    try:
        denied = require_permission(event, conn, "dashboard", "read")
        if denied:
            return denied
        result = DashboardDAL(conn).get_mental_health_trend()
        return success({
            "uptrend": [dict(r) for r in result["uptrend"]],
            "downtrend": [dict(r) for r in result["downtrend"]],
        })
    except Exception as e:
        return error(str(e))
    finally:
        conn.close()
