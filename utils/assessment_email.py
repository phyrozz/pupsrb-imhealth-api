"""Email delivery for completed student assessments."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3


def send_submission_confirmation(to_email: str, next_available_at: datetime):
    from_email = os.environ.get("SES_FROM_EMAIL")
    if not from_email:
        raise RuntimeError("SES_FROM_EMAIL is not configured")

    local_time = next_available_at.astimezone(ZoneInfo("Asia/Manila"))
    formatted_time = local_time.strftime("%B %d, %Y at %I:%M %p PHT")
    boto3.client("ses", region_name=os.environ.get("AWS_REGION", "ap-southeast-1")).send_email(
        Source=from_email,
        Destination={"ToAddresses": [to_email]},
        Message={
            "Subject": {"Data": "Your iMHealth assessment was submitted"},
            "Body": {
                "Text": {
                    "Data": (
                        "Your iMHealth assessment has been submitted successfully.\n\n"
                        f"You can complete your next assessment on {formatted_time}.\n\n"
                        "Thank you for taking care of your wellbeing."
                    )
                }
            },
        },
    )
