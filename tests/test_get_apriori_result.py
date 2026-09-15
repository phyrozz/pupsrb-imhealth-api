"""Offline contract tests for assessment response retrieval."""
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
os.environ["AWS_PROFILE"] = os.environ["AWS_DEFAULT_PROFILE"] = "imhealth-dev"


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


endpoint = importlib.import_module("services.assessments.get_apriori_result")


def student_event():
    return {
        "pathParameters": {"assessment_id": "synthetic-assessment"},
        "requestContext": {"authorizer": {"claims": {
            "sub": "cognito-subject",
            "email": "student@example.edu",
            "email_verified": "true",
            "custom:is_student": "true",
        }}},
    }


class AprioriResultTests(unittest.TestCase):
    def tearDown(self):
        psycopg2.connect.assert_not_called()

    def test_result_payload_includes_stored_answers_for_authorized_student(self):
        conn, profiles, assessments = Mock(), Mock(), Mock()
        profiles.get_by_username.return_value = {"id": "internal-profile", "is_student": True}
        assessments.get_apriori_result.return_value = {
            "assessment_id": "synthetic-assessment", "responses": list(range(23)),
        }
        with patch.object(endpoint, "get_db_connection", return_value=conn), \
             patch.object(endpoint, "ProfilesDAL", return_value=profiles), \
             patch.object(endpoint, "AssessmentsDAL", return_value=assessments):
            response = endpoint.handler(student_event(), None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"])["responses"], list(range(23)))
        assessments.get_apriori_result.assert_called_once_with("synthetic-assessment", "internal-profile")
        conn.close.assert_called_once_with()

    def test_dal_joins_owned_assessment_and_selects_responses(self):
        from generic_dals.assessments_dal import AssessmentsDAL

        dal = AssessmentsDAL.__new__(AssessmentsDAL)
        dal._fetch_one = Mock(return_value=None)
        dal.get_apriori_result("synthetic-assessment", "internal-profile")

        query, params = dal._fetch_one.call_args.args
        self.assertIn("a.responses", query)
        self.assertIn("JOIN public.assessments a ON a.id = ar.assessment_id", query)
        self.assertEqual(params, ("synthetic-assessment", False, "internal-profile"))


if __name__ == "__main__":
    unittest.main()
