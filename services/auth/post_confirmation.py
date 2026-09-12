import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from generic_dals.auth_dal import AuthDAL


def handler(event, context):
    user_attrs = event["request"]["userAttributes"]
    if not isinstance(user_attrs, dict):
        raise ValueError("Cognito userAttributes must be an object")
    email = (user_attrs.get("email") or event.get("userName") or "").strip().lower()
    if not email:
        raise ValueError("Cognito post-confirmation requires an email or username")
    is_student = user_attrs.get("custom:is_student", "true").lower() == "true"

    conn = get_db_connection()
    try:
        AuthDAL(conn).create_profile_on_confirm(email, is_student)
    finally:
        conn.close()

    return event
