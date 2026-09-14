from generic_dals.permissions_dal import PermissionsDAL
from utils.request import get_authenticated_username, get_cognito_user_id, is_admin
from utils.response import error


def admin_identity(event, conn):
    if not get_cognito_user_id(event) or not get_authenticated_username(event):
        return None, error("Unauthorized", 401)
    if not is_admin(event):
        return None, error("Forbidden", 403)
    identity = PermissionsDAL(conn).identity(get_authenticated_username(event))
    if not identity:
        return None, error("Forbidden", 403)
    return identity, None


def require_permission(event, conn, module, permission):
    identity, denied = admin_identity(event, conn)
    if denied:
        return denied
    if module == "permissions" and identity["role_name"] != "su_admin":
        return error("Forbidden", 403)
    grants = PermissionsDAL(conn).permissions(identity["role_id"])
    if permission not in grants.get(module, []):
        return error("Forbidden", 403)
    return None
