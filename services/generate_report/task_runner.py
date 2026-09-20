"""Authenticated Lambda entry point for queued report generation."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.admin_permissions import require_permission
from utils.db import get_db_connection
from utils.ecs_helper import ECSHelper
from utils.request import get_authenticated_username, get_body, get_cognito_user_id, is_admin
from utils.response import error, success

try:
    # Serverless packages this service directory as the Lambda task root.
    from report_validation import validate_report_request
except ModuleNotFoundError:  # pragma: no cover - used by package-style local imports
    from services.generate_report.report_validation import validate_report_request


TASK_DEFINITION = "pupsrb-imhealth-generate-report"
CONTAINER_NAME = "pupsrb-imhealth-generate-report"


def handler(event, context):
    """Validate a request and start an isolated Fargate report worker.

    The recipient comes only from the verified Cognito email claim.  The ECS
    override intentionally contains only this small report event; Lambda
    environment values such as database settings and SES configuration stay in
    the task definition's own secrets block.
    """
    if not get_cognito_user_id(event) or not get_authenticated_username(event):
        return error("Unauthorized", 401)
    if not is_admin(event):
        return error("Forbidden", 403)

    try:
        request = validate_report_request(get_body(event))
    except (TypeError, ValueError):
        return error("Invalid report request.", 400)

    conn = None
    try:
        conn = get_db_connection()
        for module, permission in (("reports", "download"), ("assessments", "read")):
            denied = require_permission(event, conn, module, permission)
            if denied:
                return denied
        if request["report_type"] == "student":
            denied = require_permission(event, conn, "students", "read")
            if denied:
                return denied

        task_event = {**request, "recipient_email": get_authenticated_username(event)}
        ECSHelper(task_definition=TASK_DEFINITION).run_task(
            container_name=CONTAINER_NAME,
            event=task_event,
            pass_environment=False,
        )
        return success(
            {
                "message": "Report generation has started. The completed file will be emailed to you.",
                "format": request["format"],
            },
            status_code=202,
        )
    except Exception:
        return error("Unable to start report generation. Please try again later.")
    finally:
        if conn is not None:
            conn.close()
