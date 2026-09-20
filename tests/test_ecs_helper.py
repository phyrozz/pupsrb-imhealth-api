"""Offline tests for ECS launch configuration parsing."""
import os
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

boto3 = types.ModuleType("boto3")
boto3.client = Mock()
sys.modules["boto3"] = boto3

spec = importlib.util.spec_from_file_location(
    "ecs_helper", API_ROOT / "utils" / "ecs_helper.py"
)
ecs_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ecs_helper)


class ECSHelperTests(unittest.TestCase):
    def test_comma_separated_subnets_and_security_groups_are_supported(self):
        with patch.dict(os.environ, {
            "CLUSTER": "cluster",
            "SUBNETS": "subnet-one,subnet-two",
            "SECURITY_GROUPS": "sg-one",
        }, clear=False), patch.object(ecs_helper.boto3, "client", return_value=Mock()):
            helper = ecs_helper.ECSHelper(task_definition="task-definition")

        self.assertEqual(helper.subnets, ["subnet-one", "subnet-two"])
        self.assertEqual(helper.security_groups, ["sg-one"])

    def test_json_array_configuration_is_supported(self):
        with patch.dict(os.environ, {
            "CLUSTER": "cluster",
            "SUBNETS": '["subnet-one", "subnet-two"]',
            "SECURITY_GROUPS": '["sg-one"]',
        }, clear=False), patch.object(ecs_helper.boto3, "client", return_value=Mock()):
            helper = ecs_helper.ECSHelper(task_definition="task-definition")

        self.assertEqual(helper.subnets, ["subnet-one", "subnet-two"])
        self.assertEqual(helper.security_groups, ["sg-one"])

    def test_invalid_json_scalar_is_rejected_with_a_configuration_error(self):
        with patch.dict(os.environ, {"SUBNETS": '"subnet-one"'}, clear=False):
            with self.assertRaisesRegex(ValueError, "SUBNETS"):
                ecs_helper.get_identifier_list("SUBNETS")

    def test_report_style_launch_can_pass_only_the_explicit_task_event(self):
        ecs = Mock()
        ecs.run_task.return_value = {"tasks": [{"taskArn": "task-arn"}], "failures": []}
        with patch.dict(os.environ, {
            "CLUSTER": "cluster",
            "SUBNETS": "subnet-one",
            "SECURITY_GROUPS": "sg-one",
            "DB_PASSWORD": "must-not-be-forwarded",
            "SES_FROM_EMAIL": "must-not-be-forwarded@example.edu",
        }, clear=False), patch.object(ecs_helper.boto3, "client", return_value=ecs):
            helper = ecs_helper.ECSHelper(task_definition="task-definition")
            helper.run_task(
                "report-container",
                event={"format": "csv"},
                pass_environment=False,
            )

        environment = ecs.run_task.call_args.kwargs["overrides"]["containerOverrides"][0]["environment"]
        self.assertEqual(environment, [{"name": "TASK_EVENT", "value": '{"format":"csv"}'}])

    def test_failed_or_empty_ecs_launch_is_reported_to_the_caller(self):
        ecs = Mock()
        ecs.run_task.return_value = {"tasks": [], "failures": [{"reason": "MISSING"}]}
        with patch.dict(os.environ, {
            "CLUSTER": "cluster", "SUBNETS": "subnet-one", "SECURITY_GROUPS": "sg-one",
        }, clear=False), patch.object(ecs_helper.boto3, "client", return_value=ecs):
            helper = ecs_helper.ECSHelper(task_definition="task-definition")
            with self.assertRaisesRegex(RuntimeError, "ECS task did not start"):
                helper.run_task("report-container", event={"format": "csv"}, pass_environment=False)

    def test_existing_callers_keep_their_environment_forwarding_by_default(self):
        ecs = Mock()
        ecs.run_task.return_value = {"tasks": [{"taskArn": "task-arn"}], "failures": []}
        with patch.dict(os.environ, {
            "CLUSTER": "cluster", "SUBNETS": "subnet-one", "SECURITY_GROUPS": "sg-one",
            "EXISTING_TASK_SETTING": "available",
        }, clear=False), patch.object(ecs_helper.boto3, "client", return_value=ecs):
            helper = ecs_helper.ECSHelper(task_definition="task-definition")
            helper.run_task("existing-container")

        environment = ecs.run_task.call_args.kwargs["overrides"]["containerOverrides"][0]["environment"]
        self.assertIn({"name": "EXISTING_TASK_SETTING", "value": "available"}, environment)


if __name__ == "__main__":
    unittest.main()
