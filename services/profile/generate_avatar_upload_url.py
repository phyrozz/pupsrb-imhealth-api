import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from utils.response import success, error
from utils.request import get_cognito_user_id
from generic_dals.profiles_dal import ProfilesDAL


def handler(event, context):
    user_id = get_cognito_user_id(event)
    if not user_id:
        return error("Unauthorized", 401)

    conn = get_db_connection()
    try:
        result = ProfilesDAL(conn).generate_avatar_upload_url(user_id)
        return success(result)
    except Exception as e:
        return error(str(e))
    finally:
        conn.close()
