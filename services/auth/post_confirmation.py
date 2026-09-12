import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from generic_dals.auth_dal import AuthDAL


def handler(event, context):
    user_attrs = {a["Name"]: a["Value"] for a in event["request"]["userAttributes"]}
    user_id = user_attrs.get("sub")
    full_name = user_attrs.get("name") or user_attrs.get("email")
    is_student = user_attrs.get("custom:is_student", "true").lower() == "true"

    conn = get_db_connection()
    try:
        AuthDAL(conn).create_profile_on_confirm(user_id, full_name, is_student)
    finally:
        conn.close()

    return event
