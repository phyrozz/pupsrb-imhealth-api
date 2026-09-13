"""EventBridge Lambda entry point for the scheduled assessment worker."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.ecs_helper import ECSHelper
from utils.response import success


TASK_DEFINITION = "pupsrb-imhealth-schedule-assessment"
CONTAINER_NAME = "pupsrb-imhealth-schedule-assessment"


def handler(event, context):
    """Start the dedicated Fargate worker without handling student data in Lambda."""
    ECSHelper(task_definition=TASK_DEFINITION).run_task(container_name=CONTAINER_NAME)
    return success({"message": "Assessment scheduling task triggered"})
