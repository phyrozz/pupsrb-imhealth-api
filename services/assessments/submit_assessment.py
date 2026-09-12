import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from utils.response import success, error
from utils.request import get_body, get_cognito_user_id, is_student
from generic_dals.assessments_dal import AssessmentsDAL


def _compute_apriori(responses: list) -> int:
    score = sum(responses)
    if score == 0:
        return 0
    elif score <= 10:
        return 2
    elif score <= 20:
        return 1
    else:
        return 3


def handler(event, context):
    user_id = get_cognito_user_id(event)
    if not user_id:
        return error("Unauthorized", 401)
    if not is_student(event):
        return error("Forbidden", 403)

    body = get_body(event)
    responses = body.get("responses", [])
    if len(responses) != 23:
        return error("responses must contain exactly 23 values", 400)

    conn = get_db_connection()
    try:
        result = AssessmentsDAL(conn).create_assessment(user_id, responses, _compute_apriori(responses))
        return success(result, 201)
    except Exception as e:
        conn.rollback()
        return error(str(e))
    finally:
        conn.close()
