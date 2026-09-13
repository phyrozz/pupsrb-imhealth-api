"""Offline tests for the daily assessment-availability notification worker."""
import importlib
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))
for key in list(os.environ):
    if key.startswith(("DB_", "PG", "AWS_")):
        os.environ.pop(key, None)
os.environ["AWS_PROFILE"] = "imhealth-dev"
os.environ["AWS_DEFAULT_PROFILE"] = "imhealth-dev"
os.environ["SES_FROM_EMAIL"] = "sender@example.edu"


def forbidden_external_call(*args, **kwargs):
    raise AssertionError("Real database and AWS calls are forbidden in offline tests")


psycopg2 = types.ModuleType("psycopg2")
psycopg2.connect = Mock(side_effect=forbidden_external_call)
psycopg2.Error = type("DatabaseError", (Exception,), {})
extras = types.ModuleType("psycopg2.extras")
extras.RealDictCursor = object
psycopg2.extras = extras
sys.modules["psycopg2"] = psycopg2
sys.modules["psycopg2.extras"] = extras
boto3 = types.ModuleType("boto3")
boto3.client = boto3.resource = boto3.Session = forbidden_external_call
sys.modules["boto3"] = boto3


schedule_assessment_main = importlib.import_module("services.schedule_assessment.main")
task_runner = importlib.import_module("services.schedule_assessment.task_runner")


class AssessmentAvailabilityNotificationTests(unittest.TestCase):
    def test_scheduled_handler_starts_the_dedicated_ecs_task(self):
        ecs = Mock()
        with patch.object(task_runner, "ECSHelper", return_value=ecs) as ecs_helper:
            response = task_runner.handler({}, None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["body"], '{"message": "Assessment scheduling task triggered"}')
        ecs_helper.assert_called_once_with(task_definition="pupsrb-imhealth-schedule-assessment")
        ecs.run_task.assert_called_once_with(
            container_name="pupsrb-imhealth-schedule-assessment",
        )

    def test_worker_marks_each_successful_delivery_once_and_pages_results(self):
        dal = Mock()
        dal.get_setting.return_value = "7"
        dal.get_due_assessment_availability_users.side_effect = [
            [{
                "user_id": "student-one",
                "email": "one@example.edu",
                "first_name": "One",
                "last_assessment_at": "2026-09-01T01:00:00Z",
            }],
            [],
        ]
        ses = Mock()
        with patch.object(schedule_assessment_main, "ScheduleAssessmentDAL", return_value=dal), \
             patch.object(schedule_assessment_main.boto3, "client", return_value=ses), \
             patch.object(schedule_assessment_main, "send_email") as send_email:
            result = schedule_assessment_main.send_assessment_availability_notifications(Mock(), batch_size=1)

        self.assertEqual(result, {"sent": 1, "failed": 0})
        send_email.assert_called_once()
        dal.mark_assessment_availability_notification_sent.assert_called_once_with(
            "student-one", "2026-09-01T01:00:00Z"
        )
        self.assertEqual(
            dal.get_due_assessment_availability_users.call_args_list[1].args,
            (7, 1, ("2026-09-01T01:00:00Z", "student-one")),
        )

    def test_failed_delivery_is_not_marked_and_retries_on_a_later_daily_run(self):
        dal = Mock()
        dal.get_setting.return_value = "7"
        dal.get_due_assessment_availability_users.return_value = [{
            "user_id": "student-one",
            "email": "one@example.edu",
            "first_name": "One",
            "last_assessment_at": "2026-09-01T01:00:00Z",
        }]
        with patch.object(schedule_assessment_main, "ScheduleAssessmentDAL", return_value=dal), \
             patch.object(schedule_assessment_main.boto3, "client", return_value=Mock()), \
             patch.object(schedule_assessment_main, "send_email", side_effect=RuntimeError("SES failure")):
            result = schedule_assessment_main.send_assessment_availability_notifications(Mock(), batch_size=100)

        self.assertEqual(result, {"sent": 0, "failed": 1})
        dal.mark_assessment_availability_notification_sent.assert_not_called()

    def test_schedule_is_daily_at_0100_utc(self):
        config = (API_ROOT / "services" / "schedule_assessment" / "serverless.yml").read_text()
        self.assertIn("rate: cron(0 1 * * ? *)", config)
        self.assertIn("handler: task_runner.handler", config)

    def test_ecs_worker_uses_dedicated_main_entry_point(self):
        dockerfile = (API_ROOT / "services" / "schedule_assessment" / "Dockerfile").read_text()
        task_definition = (
            API_ROOT / "services" / "schedule_assessment" / "ecs-task-definition.json"
        ).read_text()
        self.assertIn('CMD ["python", "services/schedule_assessment/main.py"]', dockerfile)
        self.assertIn('"family": "pupsrb-imhealth-schedule-assessment"', task_definition)


if __name__ == "__main__":
    unittest.main()
