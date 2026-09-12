"""Offline program lookup checks; no database, AWS, or real environment files."""
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

db = importlib.import_module("utils.db")
db.get_db_connection = Mock(side_effect=forbidden_external_call)
programs = importlib.import_module("services.students.list_programs")


class ProgramsTests(unittest.TestCase):
    def setUp(self):
        self.conn = Mock()
        self.conn.closed = False
        self.cursor = self.conn.cursor.return_value
        self.cursor.fetchone.return_value = {"total": 0}
        self.cursor.fetchall.return_value = []
        self.lookup = patch.object(programs, "get_db_connection", return_value=self.conn)
        self.lookup.start()
        self.addCleanup(self.lookup.stop)
        psycopg2.connect.reset_mock()

    def tearDown(self):
        psycopg2.connect.assert_not_called()

    def response_body(self, event=None):
        response = programs.handler(event or {}, None)
        return response, json.loads(response["body"])

    def test_defaults_return_first_page_and_metadata(self):
        rows = [{"id": 44, "initial": "BSIT", "name": "Information Technology"}]
        self.cursor.fetchone.return_value = {"total": 26}
        self.cursor.fetchall.return_value = rows

        response, body = self.response_body()

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body, {
            "items": rows, "page": 1, "page_size": 25, "total": 26, "has_more": True,
        })
        self.assertEqual(self.cursor.execute.call_args_list[0].args, (
            "SELECT COUNT(*) AS total FROM public.programs", ()
        ))
        self.assertEqual(self.cursor.execute.call_args_list[1].args, (
            "SELECT id, initial, name FROM public.programs ORDER BY initial, name, id LIMIT %s OFFSET %s",
            (25, 0),
        ))
        self.conn.close.assert_called_once_with()
        self.conn.commit.assert_not_called()

    def test_search_uses_parameterized_case_insensitive_filter(self):
        event = {"queryStringParameters": {"q": "  bS%_it  ", "page": "2", "page_size": "10"}}
        self.cursor.fetchone.return_value = {"total": 11}

        response, body = self.response_body(event)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["page"], 2)
        self.assertEqual(body["has_more"], False)
        pattern = "%bS\\%\\_it%"
        self.assertEqual(self.cursor.execute.call_args_list[0].args, (
            "SELECT COUNT(*) AS total FROM public.programs WHERE initial ILIKE %s ESCAPE E'\\\\' OR name ILIKE %s ESCAPE E'\\\\'",
            (pattern, pattern),
        ))
        self.assertEqual(self.cursor.execute.call_args_list[1].args, (
            "SELECT id, initial, name FROM public.programs WHERE initial ILIKE %s ESCAPE E'\\\\' OR name ILIKE %s ESCAPE E'\\\\' "
            "ORDER BY initial, name, id LIMIT %s OFFSET %s",
            (pattern, pattern, 10, 10),
        ))

    def test_blank_search_has_no_filter_and_page_size_is_capped(self):
        event = {"queryStringParameters": {"q": "   ", "page_size": "200"}}
        self.cursor.fetchone.return_value = {"total": 50}

        response, body = self.response_body(event)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["page_size"], 50)
        self.assertEqual(body["has_more"], False)
        self.assertNotIn("WHERE", self.cursor.execute.call_args_list[0].args[0])

    def test_invalid_pagination_returns_safe_400_without_connecting(self):
        for query_params, message in (
            ({"page": "0"}, "Invalid page parameter."),
            ({"page": "one"}, "Invalid page parameter."),
            ({"page_size": "0"}, "Invalid page_size parameter."),
            ({"page_size": "1.5"}, "Invalid page_size parameter."),
        ):
            with self.subTest(query_params=query_params):
                response, body = self.response_body({"queryStringParameters": query_params})
                self.assertEqual(response["statusCode"], 400)
                self.assertEqual(body, {"message": message})
        programs.get_db_connection.assert_not_called()

    def test_query_failure_is_safe_and_connection_is_closed(self):
        self.cursor.execute.side_effect = psycopg2.Error("private database details")
        response, body = self.response_body()
        self.assertEqual(response["statusCode"], 500)
        self.assertEqual(body, {"message": "Unable to load programs. Please try again later."})
        self.assertNotIn("private", response["body"])
        self.conn.close.assert_called_once_with()

    def test_connection_failure_also_returns_safe_error(self):
        programs.get_db_connection.side_effect = RuntimeError("private host details")
        response, body = self.response_body()
        self.assertEqual(response["statusCode"], 500)
        self.assertNotIn("private", response["body"])
        self.conn.close.assert_not_called()

    def test_close_failure_preserves_success_and_safe_query_error(self):
        self.conn.close.side_effect = RuntimeError("private cleanup details")
        with self.assertLogs(programs.logger, level="WARNING") as logs:
            success_response, success_body = self.response_body()
            self.cursor.execute.side_effect = psycopg2.Error("private query details")
            error_response, error_body = self.response_body()

        self.assertEqual(success_response["statusCode"], 200)
        self.assertEqual(success_body["items"], [])
        self.assertEqual(error_response["statusCode"], 500)
        self.assertEqual(error_body, {
            "message": "Unable to load programs. Please try again later."
        })
        self.assertNotIn("private", error_response["body"])
        self.assertNotIn("private", " ".join(logs.output))
        self.assertEqual(self.conn.close.call_count, 2)

    def test_route_is_public_and_other_student_routes_keep_authorizers(self):
        config = (API_ROOT / "services/students/serverless.yml").read_text()
        public_route = config.split("  listPrograms:\n", 1)[1].split("  listStudents:\n", 1)[0]
        self.assertIn("path: /programs", public_route)
        self.assertIn("method: get", public_route)
        self.assertIn("cors:", public_route)
        self.assertNotIn("authorizer:", public_route)
        self.assertEqual(config.count("authorizer:"), 5)


if __name__ == "__main__":
    unittest.main()
