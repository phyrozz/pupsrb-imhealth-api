import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.ecs_helper import ECSHelper
from utils.request import get_body
from utils.response import success, error


def handler(event, context):
    body = get_body(event)
    task = body.get("task")  # "insert_assessment_trends" | "send_reminder_emails" | None (runs all)

    ecs = ECSHelper(task_definition="pupsrb-imhealth-cron")
    ecs.run_task(container_name="pupsrb-imhealth-cron", event={"task": task})

    return success({"message": "ECS task triggered", "task": task})
