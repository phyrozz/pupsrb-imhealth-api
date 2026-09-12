import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.response import success, error
from utils.request import get_body, get_cognito_user_id, is_admin


def handler(event, context):
    user_id = get_cognito_user_id(event)
    if not user_id:
        return error("Unauthorized", 401)
    if not is_admin(event):
        return error("Forbidden", 403)

    body = get_body(event)
    # TODO: implement email sending logic
    return success({"message": "Status update email sent"})
