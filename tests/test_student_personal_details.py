"""Offline self-profile authorization checks; real database and AWS calls fail."""
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
    raise AssertionError("External call attempted during offline test")

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

get_details = importlib.import_module("services.students.get_personal_details")
update_details = importlib.import_module("services.students.update_personal_details")

def event(body=None, student=True, verified=True):
    return {
        "body": json.dumps(body or {}),
        "requestContext": {"authorizer": {"claims": {
            "sub": "cognito-id-not-database-id", "email": "Student@Example.edu",
            "email_verified": str(verified).lower(), "custom:is_student": str(student).lower(),
        }}},
    }

class SelfProfileTests(unittest.TestCase):
    def setUp(self):
        self.conn = Mock()
        self.profiles = Mock()
        self.details = Mock()
        self.profiles.get_by_username.return_value = {"id": "database-profile-id", "is_student": True}
        self.details.get_by_user_id.return_value = {"user_id": "database-profile-id", "first_name": "Ada"}
        self.details.update_by_user_id.return_value = {"user_id": "database-profile-id"}
        for module in (get_details, update_details):
            for name, value in (("get_db_connection", self.conn), ("ProfilesDAL", self.profiles), ("PersonalDetailsDAL", self.details)):
                mocked = patch.object(module, name, return_value=value)
                mocked.start()
                self.addCleanup(mocked.stop)
        psycopg2.connect.reset_mock()

    def tearDown(self):
        psycopg2.connect.assert_not_called()

    def test_get_resolves_only_verified_student_profile(self):
        response = get_details.handler(event(), None)
        self.assertEqual(response["statusCode"], 200)
        self.profiles.get_by_username.assert_called_with("student@example.edu")
        self.details.get_by_user_id.assert_called_with("database-profile-id")

    def test_update_uses_profile_id_and_rejects_identity_field(self):
        response = update_details.handler(event({"first_name": "Grace"}), None)
        self.assertEqual(response["statusCode"], 200)
        self.details.update_by_user_id.assert_called_once_with("database-profile-id", {"first_name": "Grace"})
        self.assertEqual(update_details.handler(event({"email": "other@example.edu"}), None)["statusCode"], 400)

    def test_unverified_identity_never_opens_connection(self):
        for request in (event(verified=False),):
            self.assertEqual(get_details.handler(request, None)["statusCode"], 401)
            self.assertEqual(update_details.handler(request, None)["statusCode"], 401)
        get_details.get_db_connection.assert_not_called()
        update_details.get_db_connection.assert_not_called()

    def test_non_student_profile_is_rejected(self):
        self.profiles.get_by_username.return_value = {"id": "database-profile-id", "is_student": False}
        self.assertEqual(get_details.handler(event(), None)["statusCode"], 404)
        self.assertEqual(update_details.handler(event({"first_name": "Grace"}), None)["statusCode"], 409)
        self.details.update_by_user_id.assert_not_called()

if __name__ == "__main__":
    unittest.main()
