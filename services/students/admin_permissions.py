import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from generic_dals.permissions_dal import PermissionsDAL
from utils.admin_permissions import admin_identity, require_permission
from utils.db import get_db_connection
from utils.request import get_body, get_cognito_user_id, get_authenticated_username, is_admin
from utils.response import success, error


def handler(event, context):
    if not get_cognito_user_id(event) or not get_authenticated_username(event):
        return error("Unauthorized", 401)
    if not is_admin(event):
        return error("Forbidden", 403)
    conn = None
    try:
        conn = get_db_connection()
        dal = PermissionsDAL(conn)
        identity, denied = admin_identity(event, conn)
        if denied:
            return denied
        path = event.get("path", "")
        method = event.get("httpMethod", "GET")
        if path.rstrip("/").endswith("/me") and method == "GET":
            return success({**identity, "permissions": dal.permissions(identity["role_id"])})
        denied = require_permission(event, conn, "permissions", "update" if method == "PUT" else "read")
        if denied:
            return denied
        if method == "GET":
            return success(dal.matrix())
        if method != "PUT":
            return error("Method not allowed", 405)
        role_id = (event.get("pathParameters") or {}).get("role_id")
        if not str(role_id).isdecimal() or int(role_id) < 1:
            return error("Invalid role_id", 400)
        body = get_body(event)
        if not isinstance(body, dict) or set(body) != {"grants"} or not isinstance(body["grants"], list):
            return error("grants must be an array", 400)
        grants = set()
        for grant in body["grants"]:
            if not isinstance(grant, dict) or set(grant) != {"module_id", "permission_type_id"}:
                return error("Invalid grant", 400)
            values = (grant["module_id"], grant["permission_type_id"])
            if any(type(v) is not int or v < 1 for v in values):
                return error("Grant identifiers must be positive integers", 400)
            grants.add(values)
        dal.replace(int(role_id), sorted(grants))
        return success({"message": "Permissions updated"})
    except (ValueError, TypeError) as exc:
        return error(str(exc), 400)
    except Exception:
        return error("Unable to load or save permissions")
    finally:
        if conn is not None:
            conn.close()
