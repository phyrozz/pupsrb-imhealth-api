"""Offline authorization and validation checks for administrator student edits."""
import importlib
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for key in list(os.environ):
    if key.startswith(("DB_", "PG", "AWS_")):
        os.environ.pop(key, None)
os.environ["AWS_PROFILE"] = "imhealth-dev"
os.environ["AWS_DEFAULT_PROFILE"] = "imhealth-dev"

def forbidden(*args, **kwargs):
    raise AssertionError("External calls are forbidden in offline tests")

psycopg2 = types.ModuleType("psycopg2")
psycopg2.connect = Mock(side_effect=forbidden)
psycopg2.Error = type("DatabaseError", (Exception,), {})
extras = types.ModuleType("psycopg2.extras")
extras.RealDictCursor = object
psycopg2.extras = extras
sys.modules["psycopg2"] = psycopg2
sys.modules["psycopg2.extras"] = extras
boto3 = types.ModuleType("boto3")
boto3.client = boto3.resource = boto3.Session = forbidden
sys.modules["boto3"] = boto3

module = importlib.import_module("services.students.update_student")
STUDENT_ID = "c223aa20-2e20-4cb4-9f76-8e1d31decc93"

def event(body, student=False):
    return {
        "pathParameters": {"user_id": STUDENT_ID},
        "body": json.dumps(body),
        "requestContext": {"authorizer": {"claims": {
            "sub": "admin-cognito-sub", "email": "admin@example.edu",
            "email_verified": "true", "custom:is_student": str(student).lower(),
        }}},
    }

class UpdateStudentTests(unittest.TestCase):
    def setUp(self):
        self.conn = Mock()
        self.dal = Mock()
        self.dal.update_by_user_id.return_value = {"user_id": STUDENT_ID}
        self.dal.get_by_user_id.return_value = {"user_id": STUDENT_ID, "first_name": "Ada"}
        self.db = patch.object(module, "get_db_connection", return_value=self.conn)
        self.guard = patch.object(module, "require_permission", return_value=None)
        self.constructor = patch.object(module, "PersonalDetailsDAL", return_value=self.dal)
        for mock in (self.db, self.guard, self.constructor):
            mock.start()
            self.addCleanup(mock.stop)
        psycopg2.connect.reset_mock()

    def tearDown(self):
        psycopg2.connect.assert_not_called()

    def test_admin_update_requires_read_and_update_grants(self):
        request = event({"first_name": "Ada", "student_number": "2021-12345-AB-0"})
        response = module.handler(request, None)
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(module.require_permission.call_count, 2)
        self.assertEqual([call.args[2:] for call in module.require_permission.call_args_list], [("students", "read"), ("students", "update")])
        self.dal.update_by_user_id.assert_called_once_with(STUDENT_ID, {"first_name": "Ada", "student_number": "2021-12345-AB-0"})
        self.conn.close.assert_called_once()

    def test_denied_update_never_writes(self):
        module.require_permission.side_effect = [None, {"statusCode": 403, "body": "{}"}]
        response = module.handler(event({"first_name": "Ada"}), None)
        self.assertEqual(response["statusCode"], 403)
        self.dal.update_by_user_id.assert_not_called()

    def test_student_and_invalid_fields_are_rejected_without_connection(self):
        for request in (event({"first_name": "Ada"}, student=True), event({"email": "other@example.edu"}), event({"student_number": "bad"})):
            self.assertIn(module.handler(request, None)["statusCode"], (400, 403))
        module.get_db_connection.assert_not_called()

if __name__ == "__main__":
    unittest.main()
