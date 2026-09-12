import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from utils.response import success, error
from utils.request import get_path_param, get_cognito_user_id
from generic_dals.assessments_dal import AssessmentsDAL


def handler(event, context):
    user_id = get_cognito_user_id(event)
    if not user_id:
        return error("Unauthorized", 401)

    assessment_id = get_path_param(event, "assessment_id")

    conn = get_db_connection()
    try:
        result = AssessmentsDAL(conn).get_apriori_result(assessment_id, user_id)
        if not result:
            return error("Apriori result not found", 404)
        return success(dict(result))
    except Exception as e:
        return error(str(e))
    finally:
        conn.close()
