import os
import sys
from uuid import UUID

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from generic_dals.counselor_workload_dal import CounselorWorkloadDAL
from utils.admin_permissions import admin_identity, require_permission
from utils.db import get_db_connection
from utils.request import get_body, get_path_param
from utils.response import error, success


VALID_SCOPES = {"mine", "unassigned", "all"}
VALID_STATUSES = {"assigned", "in_review", "completed"}


def _assessment_id(event):
    try:
        return str(UUID(str(get_path_param(event, "assessment_id"))))
    except (TypeError, ValueError, AttributeError):
        return None


def _workload_identity(event, conn, permission):
    denied = require_permission(event, conn, "workload", permission)
    if denied:
        return None, denied
    identity, denied = admin_identity(event, conn)
    if denied:
        return None, denied
    if identity["role_name"] not in {"guidance_counselor", "su_admin"}:
        return None, error("Forbidden", 403)
    return identity, None


def list_handler(event, context):
    conn = None
    try:
        conn = get_db_connection()
        identity, denied = _workload_identity(event, conn, "read")
        if denied:
            return denied
        scope = str((event.get("queryStringParameters") or {}).get("scope") or "mine")
        if scope not in VALID_SCOPES or (scope == "all" and identity["role_name"] != "su_admin"):
            return error("Invalid or unauthorized workload scope", 400)
        dal = CounselorWorkloadDAL(conn)
        payload = {"items": [dict(row) for row in dal.list_items(identity["admin_id"], scope)]}
        if identity["role_name"] == "su_admin":
            payload["counselors"] = [dict(row) for row in dal.counselors()]
        return success(payload)
    except Exception:
        return error("Unable to load counselor workload")
    finally:
        if conn is not None:
            conn.close()


def claim_handler(event, context):
    assessment_id = _assessment_id(event)
    if not assessment_id:
        return error("Invalid assessment_id", 400)
    conn = None
    try:
        conn = get_db_connection()
        identity, denied = _workload_identity(event, conn, "update")
        if denied:
            return denied
        if identity["role_name"] != "guidance_counselor":
            return error("Only guidance counselors can claim workload", 403)
        row = CounselorWorkloadDAL(conn).claim(assessment_id, identity["admin_id"])
        return success(dict(row)) if row else error("Assessment is already assigned or unavailable", 409)
    except Exception:
        return error("Unable to claim workload")
    finally:
        if conn is not None:
            conn.close()


def update_handler(event, context):
    assessment_id = _assessment_id(event)
    if not assessment_id:
        return error("Invalid assessment_id", 400)
    try:
        body = get_body(event)
    except Exception:
        return error("Invalid request body", 400)
    status = body.get("status") if isinstance(body, dict) else None
    if status not in VALID_STATUSES:
        return error("Invalid workload status", 400)
    conn = None
    try:
        conn = get_db_connection()
        identity, denied = _workload_identity(event, conn, "update")
        if denied:
            return denied
        dal = CounselorWorkloadDAL(conn)
        if identity["role_name"] == "su_admin" and "assigned_admin_id" in body:
            try:
                assigned_admin_id = str(UUID(str(body["assigned_admin_id"])))
            except (TypeError, ValueError, AttributeError):
                return error("Invalid assigned_admin_id", 400)
            row = dal.manage(assessment_id, assigned_admin_id, status)
        else:
            row = dal.update_mine(assessment_id, identity["admin_id"], status)
        return success(dict(row)) if row else error("Workload item not found or not assigned to you", 404)
    except Exception:
        return error("Unable to update workload")
    finally:
        if conn is not None:
            conn.close()
