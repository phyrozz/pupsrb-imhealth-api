import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from generic_dals.personal_details_dal import PersonalDetailsDAL
from generic_dals.profiles_dal import ProfilesDAL
from utils.db import get_db_connection
from utils.request import get_authenticated_username, get_cognito_user_id
from utils.response import error, success

logger = logging.getLogger(__name__)


def handler(event, context):
    username = get_authenticated_username(event)
    if not get_cognito_user_id(event) or not username:
        return error("Unauthorized", 401)
    conn = None
    try:
        conn = get_db_connection()
        profile = ProfilesDAL(conn).get_by_username(username)
        if not profile or not profile["is_student"]:
            return error("Student profile not found", 404)
        details = PersonalDetailsDAL(conn).get_by_user_id(profile["id"])
        if not details:
            return error("Student details not found", 404)
        return success(dict(details))
    except Exception:
        logger.exception("Unable to load student details")
        return error("Unable to load your details. Please try again later.")
    finally:
        if conn is not None:
            conn.close()
