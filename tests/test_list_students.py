"""Offline students-list authorization and validation checks."""
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

list_students = importlib.import_module("services.students.list_students")
import_students = importlib.import_module("services.students.import_students_csv")


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


class ListStudentsTests(unittest.TestCase):
    def setUp(self):
        self.conn = Mock()
        self.dal = Mock()
        self.dal.is_admin_by_email.return_value = True
        self.dal.list_students.return_value = [{"user_id": "student-1"}]
        self.connection = patch.object(list_students, "get_db_connection", return_value=self.conn)
        self.dal_constructor = patch.object(list_students, "PersonalDetailsDAL", return_value=self.dal)
        self.connection.start()
        self.dal_constructor.start()
        self.addCleanup(self.connection.stop)
        self.addCleanup(self.dal_constructor.stop)
        psycopg2.connect.reset_mock()

    def tearDown(self):
        psycopg2.connect.assert_not_called()

    def response_body(self, event):
        response = list_students.handler(event, None)
        return response, json.loads(response["body"])

    def test_valid_request_authorizes_by_verified_email_and_caps_page_size(self):
        response, body = self.response_body(admin_event({
            "result_count": "2", "program": " BSIT ", "search": " Ada ",
            "page_size": "999", "page": "3",
        }))

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body, [{"user_id": "student-1"}])
        self.dal.is_admin_by_email.assert_called_once_with("admin@example.edu")
        self.dal.list_students.assert_called_once_with("2", "BSIT", "Ada", "100", "3")
        self.conn.close.assert_called_once_with()

    def test_blank_result_count_means_no_assessment_count_filter(self):
        response, body = self.response_body(admin_event({"result_count": ""}))

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body, [{"user_id": "student-1"}])
        self.dal.list_students.assert_called_once_with("", "", "", "20", "1")

    def test_invalid_query_parameters_are_rejected_before_database_access(self):
        for params, message in (
            ({"result_count": "-1"}, "Invalid result_count parameter."),
            ({"result_count": "2.5"}, "Invalid result_count parameter."),
            ({"page_size": "0"}, "Invalid page_size parameter."),
            ({"page": "zero"}, "Invalid page parameter."),
        ):
            with self.subTest(params=params):
                response, body = self.response_body(admin_event(params))
                self.assertEqual(response["statusCode"], 400)
                self.assertEqual(body, {"message": message})
        list_students.get_db_connection.assert_not_called()

    def test_student_claim_and_non_admin_email_are_forbidden(self):
        student = admin_event()
        student["requestContext"]["authorizer"]["claims"]["custom:is_student"] = "true"
        response, _ = self.response_body(student)
        self.assertEqual(response["statusCode"], 403)
        list_students.get_db_connection.assert_not_called()

        self.dal.is_admin_by_email.return_value = False
        response, _ = self.response_body(admin_event())
        self.assertEqual(response["statusCode"], 403)
        self.dal.list_students.assert_not_called()

    def test_missing_subject_or_unverified_email_is_denied_before_database_access(self):
        missing_subject = admin_event()
        del missing_subject["requestContext"]["authorizer"]["claims"]["sub"]
        response, _ = self.response_body(missing_subject)
        self.assertEqual(response["statusCode"], 401)

        unverified = admin_event()
        unverified["requestContext"]["authorizer"]["claims"]["email_verified"] = "false"
        response, _ = self.response_body(unverified)
        self.assertEqual(response["statusCode"], 401)
        list_students.get_db_connection.assert_not_called()

    def test_failure_response_does_not_expose_database_details(self):
        self.dal.list_students.side_effect = RuntimeError("private database hostname")
        response, body = self.response_body(admin_event())
        self.assertEqual(response["statusCode"], 500)
        self.assertEqual(body, {"message": "Unable to load students. Please try again later."})
        self.assertNotIn("private", response["body"])
        self.conn.close.assert_called_once_with()


class PersonalDetailsDALTests(unittest.TestCase):
    def test_admin_email_check_uses_the_baseline_admins_email_column(self):
        from generic_dals.personal_details_dal import PersonalDetailsDAL
        dal = PersonalDetailsDAL.__new__(PersonalDetailsDAL)
        dal._fetch_one = Mock(return_value={"?column?": 1})

        self.assertTrue(dal.is_admin_by_email("admin@example.edu"))
        query, params = dal._fetch_one.call_args.args
        self.assertEqual(params, ("admin@example.edu",))
        self.assertIn("public.admins", query)
        self.assertIn("lower(email) = lower(%s)", query)


class ImportStudentsTests(unittest.TestCase):
    def setUp(self):
        self.conn = Mock()
        self.dal = Mock()
        self.dal.is_admin_by_email.return_value = True
        self.dal.import_csv.return_value = {"inserted": 1, "skipped": 0}
        self.connection = patch.object(import_students, "get_db_connection", return_value=self.conn)
        self.dal_constructor = patch.object(import_students, "PersonalDetailsDAL", return_value=self.dal)
        self.connection.start()
        self.dal_constructor.start()
        self.addCleanup(self.connection.stop)
        self.addCleanup(self.dal_constructor.stop)

    def test_import_uses_verified_admin_email_and_json_csv_field(self):
        event = admin_event()
        event["body"] = json.dumps({"csv": "student_number,first_name\n1,Ada"})

        response = import_students.handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        self.dal.is_admin_by_email.assert_called_once_with("admin@example.edu")
        self.dal.import_csv.assert_called_once_with("student_number,first_name\n1,Ada")

    def test_import_denies_a_non_admin_without_processing_csv(self):
        self.dal.is_admin_by_email.return_value = False
        event = admin_event()
        event["body"] = json.dumps({"csv": "student_number,first_name\n1,Ada"})

        response = import_students.handler(event, None)

        self.assertEqual(response["statusCode"], 403)
        self.dal.import_csv.assert_not_called()


if __name__ == "__main__":
    unittest.main()
