import sys
import os
import logging
import re
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from utils.response import success, error
from utils.request import get_authenticated_username, get_body, get_cognito_user_id
from generic_dals.personal_details_dal import PersonalDetailsDAL
from generic_dals.profiles_dal import ProfilesDAL

logger = logging.getLogger(__name__)
STUDENT_NUMBER = re.compile(r"^[0-9]{4}-[0-9]{5}-[A-Z]{2}-[0-9]$")
ALLOWED_FIELDS = {
    "first_name", "middle_name", "last_name", "name_suffix",
    "student_number", "birth_date", "program_id", "year",
    "marital_status_id", "is_working_student",
}


def handler(event, context):
    user_id = get_cognito_user_id(event)
    username = get_authenticated_username(event)
    if not user_id or not username:
        return error("Unauthorized", 401)
    try:
        data = get_body(event)
    except (ValueError, TypeError):
        return error("Invalid request body", 400)
    if not isinstance(data, dict) or not data or set(data) - ALLOWED_FIELDS:
        return error("Invalid student details", 400)
    for field in ("first_name", "last_name"):
        if field in data and (not isinstance(data[field], str) or not data[field].strip()):
            return error(f"Invalid {field}", 400)
    for field in ("middle_name", "name_suffix"):
        if field in data and data[field] is not None and not isinstance(data[field], str):
            return error(f"Invalid {field}", 400)
    if "student_number" in data and (not isinstance(data["student_number"], str) or not STUDENT_NUMBER.fullmatch(data["student_number"])):
        return error("Invalid student number", 400)
    if "birth_date" in data:
        try:
            date.fromisoformat(data["birth_date"])
        except (TypeError, ValueError):
            return error("Invalid birth date", 400)
    if "year" in data and (type(data["year"]) is not int or not 1 <= data["year"] <= 5):
        return error("Year must be between 1 and 5", 400)
    for field in ("program_id", "marital_status_id"):
        if field in data and data[field] is not None and (type(data[field]) is not int or data[field] < 1):
            return error(f"Invalid {field}", 400)
    if "is_working_student" in data and type(data["is_working_student"]) is not bool:
        return error("Invalid working student value", 400)

    conn = None
    try:
        conn = get_db_connection()
        profile = ProfilesDAL(conn).get_by_username(username)
        if not profile or not profile["is_student"]:
            return error("Account profile is not ready. Please sign in again.", 409)
        row = PersonalDetailsDAL(conn).update_by_user_id(profile["id"], data)
        if not row:
            return error("Personal details not found", 404)
        return success(dict(PersonalDetailsDAL(conn).get_by_user_id(profile["id"])))
    except Exception as exc:
        logger.exception("Unable to update student details")
        if conn is not None:
            conn.rollback()
        if getattr(exc, "pgcode", None) == "23505":
            return error("Student number is already in use.", 409)
        if getattr(exc, "pgcode", None) == "23503":
            return error("Selected program or marital status is unavailable.", 400)
        return error("Unable to update your details. Please try again later.")
    finally:
        if conn is not None:
            conn.close()
