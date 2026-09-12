import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from generic_dals.programs_dal import ProgramsDAL
from utils.db import get_db_connection
from utils.response import error, success

logger = logging.getLogger(__name__)


def _positive_integer(value, parameter: str, default: int):
    """Parse API Gateway query parameters without accepting zero or decimals."""
    if value is None:
        return default, None
    value = str(value).strip()
    if not value.isdecimal() or int(value) < 1:
        return None, error(f"Invalid {parameter} parameter.", 400)
    return int(value), None


def handler(event, context):
    """Public program lookup used before a student signs up with Cognito."""
    query_params = event.get("queryStringParameters") or {}
    page, invalid_response = _positive_integer(query_params.get("page"), "page", 1)
    if invalid_response:
        return invalid_response
    page_size, invalid_response = _positive_integer(
        query_params.get("page_size"), "page_size", 25
    )
    if invalid_response:
        return invalid_response
    page_size = min(page_size, 50)
    query = str(query_params.get("q") or "").strip()

    conn = None
    try:
        conn = get_db_connection()
        result = ProgramsDAL(conn).list_programs(query, page_size, page)
        total = result["total"]
        return success(
            {
                "items": [dict(row) for row in result["items"]],
                "page": page,
                "page_size": page_size,
                "total": total,
                "has_more": page * page_size < total,
            }
        )
    except Exception:
        return error("Unable to load programs. Please try again later.")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                logger.warning("Unable to close program lookup database connection")
