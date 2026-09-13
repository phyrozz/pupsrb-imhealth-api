"""Fargate entry point for daily assessment-availability notifications."""
import logging
import os
import sys

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from generic_dals.schedule_assessment_dal import ScheduleAssessmentDAL
from utils.assessment_settings import get_positive_integer
from utils.db import get_db_connection


logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def send_email(ses, from_email, to_email, subject, body_text):
    ses.send_email(
        Source=from_email,
        Destination={"ToAddresses": [to_email]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Text": {"Data": body_text}},
        },
    )


def send_assessment_availability_notifications(conn, batch_size=100):
    """Notify each student once when their configured assessment cooldown ends."""
    dal = ScheduleAssessmentDAL(conn)
    cooldown_days = get_positive_integer(dal.get_setting("assessment_cooldown_days"))
    if cooldown_days is None:
        raise RuntimeError("assessment_cooldown_days is missing or invalid")

    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "ap-southeast-1"))
    from_email = os.environ["SES_FROM_EMAIL"]
    app_url = os.environ.get("APP_URL", "https://pupsrb-imhealth.vercel.app")
    cursor = None
    sent = 0
    failed = 0

    while True:
        users = dal.get_due_assessment_availability_users(cooldown_days, batch_size, cursor)
        if not users:
            break

        for user in users:
            cursor = (user["last_assessment_at"], user["user_id"])
            try:
                first_name = user["first_name"] or "there"
                send_email(
                    ses,
                    from_email,
                    user["email"],
                    "Your iMHealth assessment is available",
                    f"Hi {first_name},\n\nYou can now complete your next mental health assessment at "
                    f"{app_url}.\n\nThank you for taking care of your wellbeing.",
                )
                dal.mark_assessment_availability_notification_sent(
                    user["user_id"], user["last_assessment_at"]
                )
                sent += 1
            except Exception:
                failed += 1
                log.exception("Failed assessment availability email for user_id=%s", user["user_id"])

        if len(users) < batch_size:
            break

    log.info("assessment availability notifications complete: sent=%s failed=%s", sent, failed)
    return {"sent": sent, "failed": failed}


def main():
    conn = None
    try:
        conn = get_db_connection()
        send_assessment_availability_notifications(conn)
        log.info("assessment availability notification task complete")
    except Exception:
        log.exception("assessment availability notification task failed")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
