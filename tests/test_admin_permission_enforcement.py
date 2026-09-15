"""Offline security coverage for identifiable administrator assessment reads."""
import importlib
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
os.environ["AWS_PROFILE"] = os.environ["AWS_DEFAULT_PROFILE"] = "imhealth-dev"


def forbidden(*args, **kwargs):
    raise AssertionError("Database and AWS connections are forbidden")


pg = types.ModuleType("psycopg2")
pg.connect = Mock(side_effect=forbidden)
pg.Error = type("DatabaseError", (Exception,), {})
extras = types.ModuleType("psycopg2.extras")
extras.RealDictCursor = object
pg.extras = extras
sys.modules["psycopg2"] = pg
sys.modules["psycopg2.extras"] = extras
aws = types.ModuleType("boto3")
aws.client = aws.resource = aws.Session = forbidden
sys.modules["boto3"] = aws

trend = importlib.import_module("services.dashboard.get_student_assessment_trend")
result = importlib.import_module("services.assessments.get_apriori_result")
authorization = importlib.import_module("utils.admin_permissions")
manager = importlib.import_module("services.admin_permissions.admin_permissions")


def event(student=False):
    return {"pathParameters": {"user_id": "synthetic-student", "assessment_id": "synthetic-assessment"},
            "requestContext": {"authorizer": {"claims": {
                "sub": "cognito-subject", "email": "Synthetic@Example.edu", "email_verified": "true",
                "custom:is_student": "true" if student else "false"}}}}


class PermissionEnforcementTests(unittest.TestCase):
    def tearDown(self):
        pg.connect.assert_not_called()

    def test_identifiable_trend_requires_both_module_grants(self):
        for grants, expected in (({}, 403), ({"dashboard": ["read"]}, 403),
                                 ({"dashboard": ["read"], "assessments": ["read"]}, 200)):
            with self.subTest(grants=grants):
                conn, identity, data = Mock(), Mock(), Mock()
                identity.identity.return_value = {"role_id": 1, "role_name": "guidance_counselor"}
                identity.permissions.return_value = grants
                data.get_student_assessment_trend.return_value = []
                with patch.object(trend, "get_db_connection", return_value=conn), \
                     patch.object(authorization, "PermissionsDAL", return_value=identity), \
                     patch.object(trend, "DashboardDAL", return_value=data):
                    response = trend.handler(event(), None)
                self.assertEqual(response["statusCode"], expected)
                if expected == 403:
                    data.get_student_assessment_trend.assert_not_called()
                else:
                    data.get_student_assessment_trend.assert_called_once_with("synthetic-student")
                conn.close.assert_called_once()

    def test_student_result_uses_internal_profile_identity(self):
        conn, profiles, assessments = Mock(), Mock(), Mock()
        profiles.get_by_username.return_value = {"id": "internal-profile", "is_student": True}
        assessments.get_apriori_result.return_value = {"assessment_id": "synthetic-assessment"}
        with patch.object(result, "get_db_connection", return_value=conn), \
             patch.object(result, "ProfilesDAL", return_value=profiles), \
             patch.object(result, "AssessmentsDAL", return_value=assessments), \
             patch.object(result, "require_permission") as require:
            response = result.handler(event(True), None)
        self.assertEqual(response["statusCode"], 200)
        profiles.get_by_username.assert_called_once_with("synthetic@example.edu")
        assessments.get_apriori_result.assert_called_once_with("synthetic-assessment", "internal-profile")
        require.assert_not_called()

    def test_admin_without_assessment_read_never_queries_result(self):
        conn, identity, assessments = Mock(), Mock(), Mock()
        identity.identity.return_value = {"role_id": 2, "role_name": "clinician"}
        identity.permissions.return_value = {}
        with patch.object(result, "get_db_connection", return_value=conn), \
             patch.object(authorization, "PermissionsDAL", return_value=identity), \
             patch.object(result, "AssessmentsDAL", return_value=assessments):
            response = result.handler(event(), None)
        self.assertEqual(response["statusCode"], 403)
        assessments.get_apriori_result.assert_not_called()

    def test_student_claim_cannot_open_result_for_admin_profile(self):
        conn, profiles, assessments = Mock(), Mock(), Mock()
        profiles.get_by_username.return_value = {"id": "admin-profile", "is_student": False}
        with patch.object(result, "get_db_connection", return_value=conn), \
             patch.object(result, "ProfilesDAL", return_value=profiles), \
             patch.object(result, "AssessmentsDAL", return_value=assessments):
            response = result.handler(event(True), None)
        self.assertEqual(response["statusCode"], 403)
        assessments.get_apriori_result.assert_not_called()

    def test_management_handler_read_contracts_and_role_replacements(self):
        import json
        identity = {"role_id": 3, "role_name": "su_admin"}
        matrix = {"roles": [], "modules": [], "permission_types": [], "grants": []}
        conn, dal = Mock(), Mock()
        dal.identity.return_value = identity
        dal.permissions.return_value = {"permissions": ["read", "update"]}
        dal.matrix.return_value = matrix
        with patch.object(manager, "get_db_connection", return_value=conn), \
             patch.object(manager, "PermissionsDAL", return_value=dal), \
             patch.object(authorization, "PermissionsDAL", return_value=dal):
            me = event()
            me.update(path="/dev/role-permissions/me", httpMethod="GET")
            response = manager.handler(me, None)
            self.assertEqual(response["statusCode"], 200)
            self.assertEqual(json.loads(response["body"]), {**identity, "permissions": dal.permissions.return_value})
            me["path"] = "/dev/role-permissions"
            self.assertEqual(json.loads(manager.handler(me, None)["body"]), matrix)
            for grants, expected in (([], []), ([{"module_id": 1, "permission_type_id": 1}] * 2, [(1, 1)])):
                with self.subTest(grants=grants):
                    change = event()
                    change.update(path="/role-permissions/1", httpMethod="PUT", body=json.dumps({"grants": grants}))
                    change["pathParameters"] = {"role_id": "1"}
                    dal.replace.reset_mock()
                    self.assertEqual(manager.handler(change, None)["statusCode"], 200)
                    dal.replace.assert_called_once_with(1, expected)

    def test_management_denies_non_super_admin_even_with_spoofed_grants(self):
        conn, dal = Mock(), Mock()
        dal.identity.return_value = {"role_id": 1, "role_name": "guidance_counselor"}
        dal.permissions.return_value = {"permissions": ["read", "update"]}
        request = event()
        request.update(path="/role-permissions/2", httpMethod="PUT", body='{"grants":[]}')
        request["pathParameters"] = {"role_id": "2"}
        with patch.object(manager, "get_db_connection", return_value=conn), \
             patch.object(manager, "PermissionsDAL", return_value=dal), \
             patch.object(authorization, "PermissionsDAL", return_value=dal):
            self.assertEqual(manager.handler(request, None)["statusCode"], 403)
        dal.replace.assert_not_called()


if __name__ == "__main__":
    unittest.main()
