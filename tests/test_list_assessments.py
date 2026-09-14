"""Offline checks for the admin assessment list endpoint and query contract."""
import importlib
import json
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

list_assessments = importlib.import_module("services.assessments.list_assessments")


def admin_event(query_params=None):
    return {
        "queryStringParameters": query_params,
        "requestContext": {"authorizer": {"claims": {
            "sub": "cognito-subject-not-profile-id",
            "email": "Admin@Example.edu",
            "email_verified": "true",
            "custom:is_student": "false",
        }}},
    }


class ListAssessmentsTests(unittest.TestCase):
    def setUp(self):
        guard = patch.object(list_assessments, "require_permission", return_value=None)
        self.guard = guard.start()
        self.addCleanup(guard.stop)
        self.conn = Mock()
        self.access_dal = Mock()
        self.access_dal.is_admin_by_email.return_value = True
        self.assessments_dal = Mock()
        self.assessments_dal.list_assessments.return_value = [{"id": 7}]
        self.connection = patch.object(list_assessments, "get_db_connection", return_value=self.conn)
        self.access_constructor = patch.object(
            list_assessments, "PersonalDetailsDAL", return_value=self.access_dal
        )
        self.assessment_constructor = patch.object(
            list_assessments, "AssessmentsDAL", return_value=self.assessments_dal
        )
        self.connection.start()
        self.access_constructor.start()
        self.assessment_constructor.start()
        self.addCleanup(self.connection.stop)
        self.addCleanup(self.access_constructor.stop)
        self.addCleanup(self.assessment_constructor.stop)
        psycopg2.connect.reset_mock()

    def response_body(self, event):
        response = list_assessments.handler(event, None)
        return response, json.loads(response["body"])

    def test_admin_request_scopes_history_to_the_requested_student(self):
        student_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        response, body = self.response_body(admin_event({
            "search": " Ada ", "page_size": "999", "page": "2", "user_id": student_id,
        }))

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body, [{"id": 7}])
        self.access_dal.is_admin_by_email.assert_called_once_with("admin@example.edu")
        self.assessments_dal.list_assessments.assert_called_once_with(
            "Ada", "", "", student_id, 100, 2
        )
        self.conn.close.assert_called_once_with()

    def test_invalid_pagination_and_user_id_do_not_open_a_connection(self):
        for params, message in (
            ({"page": "0"}, "Invalid page parameter."),
            ({"page_size": "nope"}, "Invalid page_size parameter."),
            ({"user_id": "not-a-uuid"}, "Invalid user_id parameter."),
        ):
            with self.subTest(params=params):
                response, body = self.response_body(admin_event(params))
                self.assertEqual(response["statusCode"], 400)
                self.assertEqual(body, {"message": message})
        list_assessments.get_db_connection.assert_not_called()

    def test_only_a_verified_database_admin_can_list_assessments(self):
        self.access_dal.is_admin_by_email.return_value = False
        response, body = self.response_body(admin_event())

        self.assertEqual(response["statusCode"], 403)
        self.assertEqual(body, {"message": "Forbidden"})
        self.assessments_dal.list_assessments.assert_not_called()

    def test_database_errors_do_not_expose_connection_details(self):
        self.assessments_dal.list_assessments.side_effect = RuntimeError("private database hostname")
        response, body = self.response_body(admin_event())

        self.assertEqual(response["statusCode"], 500)
        self.assertEqual(body, {"message": "Unable to load assessments. Please try again later."})
        self.assertNotIn("private", response["body"])


class AssessmentsDALTests(unittest.TestCase):
    def test_list_query_uses_assessments_as_the_source_of_truth(self):
        from generic_dals.assessments_dal import AssessmentsDAL

        dal = AssessmentsDAL.__new__(AssessmentsDAL)
        dal._fetch_all = Mock(return_value=[])
        student_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        dal.list_assessments("", "", "", student_id, 20, 3)

        query, params = dal._fetch_all.call_args.args
        self.assertIn("FROM public.assessments a", query)
        self.assertIn("LEFT JOIN public.apriori_results", query)
        self.assertIn("LEFT JOIN public.personal_details", query)
        self.assertNotIn("get_assessments_table", query)
        self.assertEqual(params[-2:], (40, 20))
        self.assertEqual(params[6:8], (student_id, student_id))


if __name__ == "__main__":
    unittest.main()
