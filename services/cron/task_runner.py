import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.ecs_helper import ECSHelper
from utils.request import get_body, get_cognito_user_id
from utils.response import success, error


def _start_trend_task():
    ecs = ECSHelper(task_definition="pupsrb-imhealth-cron")
    ecs.run_task(
        container_name="pupsrb-imhealth-cron",
        event={"task": "insert_assessment_trends"},
        pass_environment=False,
    )
    return success({"message": "ECS task triggered", "task": "insert_assessment_trends"})


def handler(event, context):
    if not get_cognito_user_id(event):
        return error("Unauthorized", 401)

    body = get_body(event)
    task = body.get("task")
    if task not in (None, "insert_assessment_trends"):
        return error("Unknown cron task", 400)

    return _start_trend_task()


def scheduled_handler(event, context):
    """EventBridge invokes this entry point directly under its Lambda permission."""
    return _start_trend_task()
