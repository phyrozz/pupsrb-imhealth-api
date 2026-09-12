import sys
import os
import logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from utils.response import success, error
from utils.request import get_authenticated_username, get_body, get_cognito_user_id
from generic_dals.personal_details_dal import PersonalDetailsDAL
from generic_dals.profiles_dal import ProfilesDAL

logger = logging.getLogger(__name__)


def handler(event, context):
    user_id = get_cognito_user_id(event)
    username = get_authenticated_username(event)
    if not user_id or not username:
        return error("Unauthorized", 401)

    body = get_body(event)
    body["email"] = username
    missing = [f for f in ("email", "first_name", "last_name", "student_number", "birth_date", "year") if not body.get(f)]
    if missing:
        return error(f"Missing required fields: {missing}", 400)

    conn = get_db_connection()
    try:
        profile = ProfilesDAL(conn).ensure_email_profile(username)
        if not profile:
            return error("Account profile is not ready. Please sign in again.", 409)
        body["user_id"] = profile["id"]
        body["email"] = profile["username"]
        marital_status = body.get("marital_status")
        if marital_status:
            if not isinstance(marital_status, str):
                return error("Invalid marital status", 400)
            status = ProfilesDAL(conn)._fetch_one(
                "SELECT id FROM public.marital_statuses WHERE lower(status) = lower(%s)",
                (marital_status.strip(),),
            )
            if not status:
                return error("Invalid marital status", 400)
            body["marital_status_id"] = status["id"]
        row = PersonalDetailsDAL(conn).create(body)
        return success(dict(row), 201)
    except ValueError as e:
        conn.rollback()
        return error(str(e), 409)
    except Exception:
        logger.exception("Student registration details could not be saved")
        conn.rollback()
        return error("Unable to save student details. Please try again later.")
    finally:
        conn.close()
