import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from generic_dals.assessments_dal import AssessmentsDAL
from generic_dals.profiles_dal import ProfilesDAL
from utils.db import get_db_connection
from utils.assessment_settings import get_positive_integer
from utils.request import get_authenticated_username, get_cognito_user_id
from utils.response import error, success


def _as_iso8601(value: datetime | None):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


def handler(event, context):
    if not get_cognito_user_id(event):
        return error("Unauthorized", 401)
    email = get_authenticated_username(event)
    if not email:
        return error("Unauthorized", 401)

    conn = get_db_connection()
    try:
        profile = ProfilesDAL(conn).ensure_email_profile(email)
        if not profile:
            return error("Account profile is not ready. Please sign in again.", 409)
        assessments = AssessmentsDAL(conn)
        cooldown_days = get_positive_integer(assessments.get_cooldown_days())
        if cooldown_days is None:
            return error("Assessment scheduling is not configured. Please try again later.", 503)
        next_available_at = assessments.get_next_submission_at(profile["id"], cooldown_days)
        available = next_available_at is None or next_available_at <= datetime.now(timezone.utc)
        return success({
            "available": available,
            "next_available_at": None if available else _as_iso8601(next_available_at),
        })
    except ValueError as exc:
        conn.rollback()
        return error(str(exc), 409)
    except Exception:
        conn.rollback()
        return error("Unable to load assessment availability. Please try again later.")
    finally:
        conn.close()
