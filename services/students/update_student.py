import logging
import os
import re
import sys
from uuid import UUID

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from generic_dals.personal_details_dal import PersonalDetailsDAL
from utils.admin_permissions import require_permission
from utils.db import get_db_connection
from utils.request import get_body, get_cognito_user_id, get_path_param, is_admin
from utils.response import error, success

logger = logging.getLogger(__name__)
STUDENT_NUMBER = re.compile(r"^[0-9]{4}-[0-9]{5}-[A-Z]{2}-[0-9]$")
FIELDS = {"first_name", "middle_name", "last_name", "name_suffix", "student_number", "birth_date", "program_id", "year", "marital_status", "is_working_student"}


def handler(event, context):
    if not get_cognito_user_id(event):
        return error("Unauthorized", 401)
    if not is_admin(event):
        return error("Forbidden", 403)
    try:
        user_id = str(UUID(str(get_path_param(event, "user_id"))))
        body = get_body(event)
    except (ValueError, TypeError, AttributeError):
        return error("Invalid student ID or request body", 400)
    if not isinstance(body, dict) or not body or set(body) - FIELDS:
        return error("Invalid student details", 400)
    data = dict(body)
    for field in ("first_name", "last_name"):
        if field in data and (not isinstance(data[field], str) or not data[field].strip()):
            return error(f"Invalid {field}", 400)
    for field in ("middle_name", "name_suffix"):
        if field in data and data[field] is not None and not isinstance(data[field], str):
            return error(f"Invalid {field}", 400)
    if "student_number" in data and (not isinstance(data["student_number"], str) or not STUDENT_NUMBER.fullmatch(data["student_number"])):
        return error("Invalid student number", 400)
    if "birth_date" in data:
        from datetime import date
        try:
            date.fromisoformat(data["birth_date"])
        except (TypeError, ValueError):
            return error("Invalid birth date", 400)
    if "year" in data and (type(data["year"]) is not int or not 1 <= data["year"] <= 5):
        return error("Year must be between 1 and 5", 400)
    if "program_id" in data and data["program_id"] is not None and (type(data["program_id"]) is not int or data["program_id"] < 1):
        return error("Invalid program", 400)
    if "is_working_student" in data and type(data["is_working_student"]) is not bool:
        return error("Invalid working student value", 400)
    if "marital_status" in data and data["marital_status"] is not None and not isinstance(data["marital_status"], str):
        return error("Invalid marital status", 400)

    conn = None
    try:
        conn = get_db_connection()
        for permission in ("read", "update"):
            denied = require_permission(event, conn, "students", permission)
            if denied:
                return denied
        dal = PersonalDetailsDAL(conn)
        if "marital_status" in data:
            value = data.pop("marital_status")
            if value and value.strip():
                status = dal._fetch_one("SELECT id FROM public.marital_statuses WHERE lower(status) = lower(%s)", (value.strip(),))
                if not status:
                    return error("Invalid marital status", 400)
                data["marital_status_id"] = status["id"]
            else:
                data["marital_status_id"] = None
        row = dal.update_by_user_id(user_id, data)
        if not row:
            return error("Student not found", 404)
        return success(dict(dal.get_by_user_id(user_id)))
    except Exception as exc:
        logger.exception("Unable to update student details")
        if conn is not None:
            conn.rollback()
        if getattr(exc, "pgcode", None) == "23505":
            return error("Student number is already in use.", 409)
        if getattr(exc, "pgcode", None) == "23503":
            return error("Selected program is unavailable.", 400)
        return error("Unable to update student details. Please try again later.")
    finally:
        if conn is not None:
            conn.close()
