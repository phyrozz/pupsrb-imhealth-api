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


if __name__ == "__main__":
    unittest.main()
