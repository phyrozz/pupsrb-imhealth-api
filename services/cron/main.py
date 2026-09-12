import json
import logging
import os
import sys
from datetime import datetime, timezone

import boto3

from generic_dals.cron_dal import CronDAL
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


def insert_assessment_trends(conn):
    """Snapshot current scenario increase/decrease counts into trend tables."""
    dal = CronDAL(conn)
    now = datetime.now(timezone.utc)

    for row in dal.get_recent_apriori_counts():
        scenario_id = row["apriori_result"]
        count = row["count"]
        prev_count = dal.get_previous_apriori_count(scenario_id)

        if count >= prev_count:
            dal.insert_mental_health_uptrend(scenario_id, count, now.date())
        else:
            dal.insert_mental_health_downtrend(scenario_id, count, now.date())

    dal.commit()
    log.info("insert_assessment_trends complete")


def send_reminder_emails(conn):
    """Send assessment reminder and unanswered-assessment reminder emails via SES."""
    dal = CronDAL(conn)
    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "ap-southeast-1"))
    from_email = os.environ["SES_FROM_EMAIL"]
    app_url = os.environ.get("APP_URL", "https://pupsrb-imhealth.vercel.app")

    for user in dal.get_assessment_reminder_users():
        try:
            send_email(
                ses,
                from_email,
                user["email"],
                "Time for your monthly mental health assessment",
                f"Hi {user['first_name']},\n\nIt's been a while since your last assessment. "
                f"Please take a few minutes to complete it at {app_url}.\n\nThank you.",
            )
            dal.mark_assessment_reminder_sent(user["user_id"])
        except Exception as e:
            log.error(f"Failed reminder email for {user['email']}: {e}")

    for user in dal.get_unanswered_assessment_users():
        try:
            send_email(
                ses,
                from_email,
                user["email"],
                "Complete your first mental health assessment",
                f"Hi {user['first_name']},\n\nYou haven't completed a mental health assessment yet. "
                f"Please take a moment to do so at {app_url}.\n\nThank you.",
            )
            dal.mark_unanswered_reminder_sent(user["user_id"])
        except Exception as e:
            log.error(f"Failed unanswered reminder email for {user['email']}: {e}")

    dal.commit()
    log.info("send_reminder_emails complete")


def main():
    conn = None
    try:
        task_event = os.environ.get("TASK_EVENT", "{}")
        event = json.loads(task_event)
        task = event.get("task")  # None = run all

        conn = get_db_connection()

        if task is None or task == "insert_assessment_trends":
            insert_assessment_trends(conn)

        if task is None or task == "send_reminder_emails":
            send_reminder_emails(conn)

        log.info(json.dumps({"event": "complete", "task": task, "timestamp": datetime.now(timezone.utc).isoformat()}))

    except Exception as e:
        log.error(json.dumps({"event": "error", "error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}))
        sys.exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
