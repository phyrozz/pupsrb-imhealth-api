import sys
import os
import logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from utils.response import success, error
from utils.request import get_authenticated_username, get_cognito_user_id, is_admin
from generic_dals.personal_details_dal import PersonalDetailsDAL

logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 100


def _integer_query_param(value, parameter: str, default: int, minimum: int):
    """Parse an integer query parameter without relying on SQL casts."""
    if value is None or str(value).strip() == "":
        return default, None
    value = str(value).strip()
    if not value.isdecimal() or int(value) < minimum:
        return None, error(f"Invalid {parameter} parameter.", 400)
    return int(value), None


def handler(event, context):
    user_id = get_cognito_user_id(event)
    if not user_id:
        return error("Unauthorized", 401)
    if not is_admin(event):
        return error("Forbidden", 403)

    email = get_authenticated_username(event)
    if not email:
        return error("Unauthorized", 401)

    query_params = event.get("queryStringParameters") or {}
    result_count, invalid_response = _integer_query_param(
        query_params.get("result_count"), "result_count", "", 0
    )
    if invalid_response:
        return invalid_response
    page_size, invalid_response = _integer_query_param(
        query_params.get("page_size"), "page_size", 20, 1
    )
    if invalid_response:
        return invalid_response
    page, invalid_response = _integer_query_param(
        query_params.get("page"), "page", 1, 1
    )
    if invalid_response:
        return invalid_response
    page_size = min(page_size, MAX_PAGE_SIZE)

    conn = None
    try:
        conn = get_db_connection()
        dal = PersonalDetailsDAL(conn)
        # The baseline identifies administrators by email, while Cognito's sub
        # is intentionally not a database profile ID. This read has no mutation.
        if not dal.is_admin_by_email(email):
            return error("Forbidden", 403)

        rows = dal.list_students(
            str(result_count),
            str(query_params.get("program") or "").strip(),
            str(query_params.get("search") or "").strip(),
            str(page_size),
            str(page),
        )
        return success([dict(r) for r in rows])
    except Exception:
        return error("Unable to load students. Please try again later.")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                logger.warning("Unable to close student list database connection")
