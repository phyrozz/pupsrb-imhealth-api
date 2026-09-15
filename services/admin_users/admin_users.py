import os
import re
import sys
import logging

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from generic_dals.admin_users_dal import AdminUsersDAL
from utils.admin_permissions import admin_identity, require_permission
from utils.db import get_db_connection
from utils.request import get_body
from utils.response import error, success


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
logger = logging.getLogger(__name__)


def _cognito_error_message(exc):
    code = getattr(exc, "response", {}).get("Error", {}).get("Code")
    if code == "UsernameExistsException":
        return "An account with this email already exists", 409
    if code == "AccessDeniedException":
        return "Administrator account provisioning is not authorized. Contact a system administrator.", 503
    if code == "ResourceNotFoundException":
        return "The administrator user pool is not configured correctly.", 503
    if code == "InvalidParameterException":
        return "Cognito rejected the administrator account details. Verify the user pool configuration.", 422
    if code == "TooManyRequestsException":
        return "Cognito is temporarily rate limiting account creation. Please try again shortly.", 429
    return "Unable to create the Cognito administrator account", 502


def list_handler(event, context):
    conn = None
    try:
        conn = get_db_connection()
        denied = require_permission(event, conn, "admin_users", "read")
        if denied:
            return denied
        dal = AdminUsersDAL(conn)
        return success({"admins": [dict(row) for row in dal.list_admins()], "roles": [dict(row) for row in dal.roles()]})
    except Exception:
        return error("Unable to load administrator users")
    finally:
        if conn is not None:
            conn.close()


def create_handler(event, context):
    try:
        body = get_body(event)
    except Exception:
        return error("Invalid request body", 400)
    email = str(body.get("email") or "").strip().lower() if isinstance(body, dict) else ""
    role_id = body.get("role_id") if isinstance(body, dict) else None
    if not EMAIL_PATTERN.fullmatch(email) or len(email) > 254:
        return error("A valid email is required", 400)
    if type(role_id) is not int or role_id < 1:
        return error("A valid role_id is required", 400)
    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID")
    if not user_pool_id:
        return error("Administrator user pool is not configured", 503)

    conn = None
    cognito_created = False
    cognito = None
    try:
        conn = get_db_connection()
        denied = require_permission(event, conn, "admin_users", "insert")
        if denied:
            return denied
        dal = AdminUsersDAL(conn)
        role = dal.role_exists(role_id)
        if not role:
            return error("Role not found", 400)
        identity, denied = admin_identity(event, conn)
        if denied:
            return denied
        if role.get("role_name") == "su_admin" and identity["role_name"] != "su_admin":
            return error("Only super administrators can create super administrator accounts", 403)
        if dal.email_exists(email):
            return error("An administrator with this email already exists", 409)

        cognito = boto3.client("cognito-idp")
        try:
            cognito.admin_create_user(
                UserPoolId=user_pool_id, Username=email,
                UserAttributes=[{"Name": "email", "Value": email}, {"Name": "email_verified", "Value": "true"}],
                DesiredDeliveryMediums=["EMAIL"],
            )
            cognito_created = True
        except Exception as exc:
            logger.exception(
                "Cognito administrator creation failed (error_code=%s)",
                getattr(exc, "response", {}).get("Error", {}).get("Code", "unknown"),
            )
            message, status = _cognito_error_message(exc)
            return error(message, status)

        return success(dict(dal.create(email, role_id)), 201)
    except Exception:
        logger.exception("Administrator database provisioning failed after Cognito creation")
        if cognito_created and cognito is not None:
            try:
                cognito.admin_delete_user(UserPoolId=user_pool_id, Username=email)
            except Exception:
                logger.exception("Unable to remove Cognito account after database provisioning failure")
        return error("Unable to create administrator user")
    finally:
        if conn is not None:
            conn.close()
