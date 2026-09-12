import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from utils.response import success, error
from utils.request import get_body, get_cognito_user_id
from generic_dals.profiles_dal import ProfilesDAL


def handler(event, context):
    user_id = get_cognito_user_id(event)
    if not user_id:
        return error("Unauthorized", 401)

    body = get_body(event)
    avatar_url = body.get("avatar_url")
    if not avatar_url:
        return error("avatar_url is required", 400)

    conn = get_db_connection()
    try:
        updated = ProfilesDAL(conn).update_avatar_url(user_id, avatar_url)
        return success(dict(updated))
    except Exception as e:
        conn.rollback()
        return error(str(e))
    finally:
        conn.close()
