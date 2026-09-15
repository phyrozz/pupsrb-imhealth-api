"""Offline tests for administrator creation and Cognito rollback behavior."""
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
    if key.startswith(("DB_", "PG", "AWS_", "COGNITO_")):
        os.environ.pop(key, None)
os.environ["AWS_PROFILE"] = os.environ["AWS_DEFAULT_PROFILE"] = "imhealth-dev"
os.environ["COGNITO_USER_POOL_ID"] = "synthetic-pool"

def forbidden(*args, **kwargs):
    raise AssertionError("External calls are forbidden")

pg = types.ModuleType("psycopg2"); pg.connect = Mock(side_effect=forbidden); pg.Error = Exception
extras = types.ModuleType("psycopg2.extras"); extras.RealDictCursor = object
sys.modules["psycopg2"] = pg; sys.modules["psycopg2.extras"] = extras
boto = types.ModuleType("boto3"); boto.client = Mock(); sys.modules["boto3"] = boto
admin_users = importlib.import_module("services.admin_users.admin_users")

def event(body):
    return {"body": json.dumps(body), "requestContext": {"authorizer": {"claims": {
        "sub": "subject", "email": "owner@example.edu", "email_verified": "true", "custom:is_student": "false"}}}}

class AdminUserTests(unittest.TestCase):
    def setUp(self):
        self.conn, self.dal, self.cognito = Mock(), Mock(), Mock()
        self.dal.role_exists.return_value = {"id": 1, "role_name": "guidance_counselor"}
        self.dal.email_exists.return_value = None
        self.dal.create.return_value = {"id": "admin-id", "email": "new@example.edu", "role_id": 1}
        self.identity = {"admin_id": "owner-id", "role_id": 3, "role_name": "su_admin"}
        self.connection = patch.object(admin_users, "get_db_connection", return_value=self.conn)
        self.dal_constructor = patch.object(admin_users, "AdminUsersDAL", return_value=self.dal)
        self.permitted = patch.object(admin_users, "require_permission", return_value=None)
        self.identity_patch = patch.object(admin_users, "admin_identity", return_value=(self.identity, None))
        self.client = patch.object(admin_users.boto3, "client", return_value=self.cognito)
        self.logger = patch.object(admin_users.logger, "exception")
        for patcher in (self.connection, self.dal_constructor, self.permitted, self.identity_patch, self.client, self.logger): patcher.start(); self.addCleanup(patcher.stop)

    def test_creates_cognito_then_database_admin(self):
        response = admin_users.create_handler(event({"email": " NEW@EXAMPLE.EDU ", "role_id": 1}), None)
        self.assertEqual(response["statusCode"], 201)
        self.cognito.admin_create_user.assert_called_once_with(UserPoolId="synthetic-pool", Username="new@example.edu", UserAttributes=[{"Name": "email", "Value": "new@example.edu"}, {"Name": "email_verified", "Value": "true"}], DesiredDeliveryMediums=["EMAIL"])
        self.dal.create.assert_called_once_with("new@example.edu", 1)
        self.cognito.admin_delete_user.assert_not_called()

    def test_database_failure_removes_new_cognito_user(self):
        self.dal.create.side_effect = RuntimeError("database failure")
        response = admin_users.create_handler(event({"email": "new@example.edu", "role_id": 1}), None)
        self.assertEqual(response["statusCode"], 500)
        self.cognito.admin_delete_user.assert_called_once_with(UserPoolId="synthetic-pool", Username="new@example.edu")

    def test_non_super_admin_cannot_create_super_admin(self):
        self.dal.role_exists.return_value = {"id": 3, "role_name": "su_admin"}
        self.identity["role_name"] = "guidance_counselor"
        response = admin_users.create_handler(event({"email": "new@example.edu", "role_id": 3}), None)
        self.assertEqual(response["statusCode"], 403)
        self.cognito.admin_create_user.assert_not_called()

    def test_invalid_input_never_opens_database_or_cognito(self):
        response = admin_users.create_handler(event({"email": "not-email", "role_id": 1}), None)
        self.assertEqual(response["statusCode"], 400)
        admin_users.get_db_connection.assert_not_called()
        self.cognito.admin_create_user.assert_not_called()

    def test_access_denied_explains_required_cognito_authorization(self):
        failure = Exception("denied"); failure.response = {"Error": {"Code": "AccessDeniedException"}}
        self.cognito.admin_create_user.side_effect = failure
        response = admin_users.create_handler(event({"email": "new@example.edu", "role_id": 1}), None)
        self.assertEqual(response["statusCode"], 503)
        self.assertIn("not authorized", json.loads(response["body"])["message"])

    def tearDown(self):
        pg.connect.assert_not_called()

if __name__ == "__main__":
    unittest.main()
