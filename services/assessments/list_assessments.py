import sys
import os
from uuid import UUID
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from utils.response import success, error
from utils.request import get_authenticated_username, get_query_param, get_cognito_user_id, is_admin
from generic_dals.assessments_dal import AssessmentsDAL
from generic_dals.personal_details_dal import PersonalDetailsDAL


MAX_PAGE_SIZE = 100


def _positive_int(value, default, parameter):
    if value is None or str(value).strip() == "":
        return default
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {parameter} parameter.")
    if parsed < 1:
        raise ValueError(f"Invalid {parameter} parameter.")
    return parsed


def handler(event, context):
    user_id = get_cognito_user_id(event)
    username = get_authenticated_username(event)
    if not user_id or not username:
        return error("Unauthorized", 401)
    if not is_admin(event):
        return error("Forbidden", 403)

    search = str(get_query_param(event, "search", "") or "").strip()
    scenario = str(get_query_param(event, "scenario", "") or "").strip()
    status = str(get_query_param(event, "status", "") or "").strip()
    requested_user_id = get_query_param(event, "user_id")
    if requested_user_id is not None and str(requested_user_id).strip() != "":
        try:
            requested_user_id = str(UUID(str(requested_user_id).strip()))
        except (TypeError, ValueError, AttributeError):
            return error("Invalid user_id parameter.", 400)
    else:
        requested_user_id = None
    try:
        page = _positive_int(get_query_param(event, "page", "1"), 1, "page")
        page_size = min(_positive_int(get_query_param(event, "page_size", "20"), 20, "page_size"), MAX_PAGE_SIZE)
    except ValueError as exc:
        return error(str(exc), 400)

    conn = get_db_connection()
    try:
        # The Cognito pool claim only distinguishes a student pool from an admin
        # pool. Verify the account against the database's baseline admins table
        # before exposing all students' sensitive assessment history.
        if not PersonalDetailsDAL(conn).is_admin_by_email(username):
            return error("Forbidden", 403)
        rows = AssessmentsDAL(conn).list_assessments(
            search, scenario, status, requested_user_id, page_size, page
        )
        return success([dict(r) for r in rows])
    except Exception:
        return error("Unable to load assessments. Please try again later.")
    finally:
        conn.close()
