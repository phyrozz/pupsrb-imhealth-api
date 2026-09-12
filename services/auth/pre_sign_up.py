import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


def handler(event, context):
    event["response"]["autoConfirmUser"] = True
    event["response"]["autoVerifyEmail"] = True
    # Mark all self-registered users as students
    event["request"]["userAttributes"]["custom:is_student"] = "true"
    return event
