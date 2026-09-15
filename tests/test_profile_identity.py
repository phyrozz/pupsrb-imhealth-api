"""Offline identity-linking tests; all DAL and AWS boundaries are mocked."""
import importlib
import json
import os
from datetime import datetime, timedelta, timezone
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

create_details = importlib.import_module("services.students.create_personal_details")
update_details = importlib.import_module("services.students.update_personal_details")
submit_assessment = importlib.import_module("services.assessments.submit_assessment")
assessment_availability = importlib.import_module("services.assessments.get_assessment_availability")
post_confirmation = importlib.import_module("services.auth.post_confirmation")


def authenticated_event(body=None, include_student_claim=True):
    claims = {
        "sub": "cognito-subject-that-is-not-a-profile-id",
        "email": "Student@Example.edu",
        "email_verified": "true",
    }
    if include_student_claim:
        claims["custom:is_student"] = "true"
    return {
        "body": json.dumps(body or {}),
        "requestContext": {"authorizer": {"claims": claims}},
    }


class ProfileIdentityTests(unittest.TestCase):
    def setUp(self):
        self.conn = Mock()
        self.profile = Mock()
        self.profile.ensure_email_profile.return_value = {
            "id": "internal-profile-id", "username": "student@example.edu"
        }
        self.profile.get_by_username.return_value = self.profile.ensure_email_profile.return_value
        self.details = Mock()
        self.assessments = Mock()
        self.assessments.get_cooldown_days.return_value = "7"
        self.assessments.get_next_submission_at.return_value = None
        self.assessments.get_latest_responses.return_value = None
        self.auth = Mock()
        self.patches = [
            patch.object(create_details, "get_db_connection", return_value=self.conn),
            patch.object(create_details, "ProfilesDAL", return_value=self.profile),
            patch.object(create_details, "PersonalDetailsDAL", return_value=self.details),
            patch.object(update_details, "get_db_connection", return_value=self.conn),
            patch.object(update_details, "ProfilesDAL", return_value=self.profile),
            patch.object(update_details, "PersonalDetailsDAL", return_value=self.details),
            patch.object(submit_assessment, "get_db_connection", return_value=self.conn),
            patch.object(submit_assessment, "ProfilesDAL", return_value=self.profile),
            patch.object(submit_assessment, "AssessmentsDAL", return_value=self.assessments),
            patch.object(submit_assessment, "send_submission_confirmation"),
            patch.object(assessment_availability, "get_db_connection", return_value=self.conn),
            patch.object(assessment_availability, "ProfilesDAL", return_value=self.profile),
            patch.object(assessment_availability, "AssessmentsDAL", return_value=self.assessments),
            patch.object(post_confirmation, "get_db_connection", return_value=self.conn),
            patch.object(post_confirmation, "AuthDAL", return_value=self.auth),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        psycopg2.connect.reset_mock()

    def tearDown(self):
        psycopg2.connect.assert_not_called()

    def test_personal_details_uses_internal_profile_id_and_claim_email(self):
        self.details.create.return_value = {"user_id": "internal-profile-id"}
        payload = {
            "email": "attacker@example.edu", "first_name": "Ada", "last_name": "Lovelace",
            "student_number": "2021-12345-AB-0", "birth_date": "2000-01-01", "year": 1,
        }

        response = create_details.handler(authenticated_event(payload), None)

        self.assertEqual(response["statusCode"], 201)
        self.profile.ensure_email_profile.assert_called_once_with("student@example.edu")
        saved = self.details.create.call_args.args[0]
        self.assertEqual(saved["user_id"], "internal-profile-id")
        self.assertEqual(saved["email"], "student@example.edu")
        self.assertNotEqual(saved["user_id"], "cognito-subject-that-is-not-a-profile-id")

    def test_student_routes_do_not_depend_on_custom_student_claim(self):
        self.details.create.return_value = {"user_id": "internal-profile-id"}
        self.details.update_by_user_id.return_value = {"user_id": "internal-profile-id"}
        self.assessments.create_assessment.return_value = {"assessment": {"id": 1}}
        personal_details = {
            "first_name": "Ada", "last_name": "Lovelace", "student_number": "2021-12345-AB-0",
            "birth_date": "2000-01-01", "year": 1,
        }

        create_response = create_details.handler(
            authenticated_event(personal_details, include_student_claim=False), None
        )
        update_response = update_details.handler(
            authenticated_event({"year": 2}, include_student_claim=False), None
        )
        assessment_response = submit_assessment.handler(
            authenticated_event({"responses": [0] * 23}, include_student_claim=False), None
        )

        self.assertEqual(create_response["statusCode"], 201)
        self.assertEqual(update_response["statusCode"], 200)
        self.assertEqual(assessment_response["statusCode"], 201)
        self.details.create.assert_called_once()
        self.details.update_by_user_id.assert_called_once_with("internal-profile-id", {"year": 2})
        self.assessments.create_assessment.assert_called_once()

    def test_personal_details_returns_retryable_error_when_profile_is_missing(self):
        self.profile.ensure_email_profile.return_value = None
        response = create_details.handler(authenticated_event({
            "first_name": "Ada", "last_name": "Lovelace", "student_number": "2021-12345-AB-0",
            "birth_date": "2000-01-01", "year": 1,
        }), None)
        self.assertEqual(response["statusCode"], 409)
        self.details.create.assert_not_called()

    def test_personal_detail_update_resolves_claim_email_and_protects_email(self):
        self.details.update_by_user_id.return_value = {"user_id": "internal-profile-id"}
        response = update_details.handler(authenticated_event({"email": "other@example.edu", "year": 2}), None)
        self.assertEqual(response["statusCode"], 200)
        self.details.update_by_user_id.assert_called_once_with("internal-profile-id", {"year": 2})

    def test_assessment_uses_internal_profile_id_for_history_and_insert(self):
        self.assessments.create_assessment.return_value = {"assessment": {"id": 1}}
        response = submit_assessment.handler(authenticated_event({"responses": ["Not at all"] * 23}), None)
        self.assertEqual(response["statusCode"], 201)
        self.assessments.get_latest_responses.assert_called_once_with("internal-profile-id")
        self.assertEqual(self.assessments.create_assessment.call_args.args[0], "internal-profile-id")

    def test_assessment_cooldown_returns_next_available_time_without_writing(self):
        self.assessments.get_next_submission_at.return_value = datetime.now(timezone.utc) + timedelta(days=1)

        response = submit_assessment.handler(authenticated_event({"responses": ["Not at all"] * 23}), None)
        body = json.loads(response["body"])

        self.assertEqual(response["statusCode"], 429)
        self.assertIn("next_available_at", body)
        self.assessments.create_assessment.assert_not_called()

    def test_assessment_requires_a_configured_positive_cooldown(self):
        self.assessments.get_cooldown_days.return_value = None

        response = submit_assessment.handler(authenticated_event({"responses": ["Not at all"] * 23}), None)

        self.assertEqual(response["statusCode"], 503)
        self.assessments.create_assessment.assert_not_called()

    def test_assessment_rejects_a_non_integer_cooldown_setting(self):
        self.assessments.get_cooldown_days.return_value = "one week"

        response = submit_assessment.handler(authenticated_event({"responses": ["Not at all"] * 23}), None)

        self.assertEqual(response["statusCode"], 503)
        self.assessments.create_assessment.assert_not_called()

    def test_assessment_availability_exposes_the_cooldown_to_the_student(self):
        response = assessment_availability.handler(authenticated_event(), None)
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"]), {
            "available": True,
            "next_available_at": None,
        })

        self.assessments.get_next_submission_at.return_value = datetime.now(timezone.utc) + timedelta(days=1)
        response = assessment_availability.handler(authenticated_event(), None)
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertFalse(body["available"])
        self.assertIn("next_available_at", body)

    def test_post_confirmation_upserts_profile_by_normalized_email(self):
        event = {"userName": "fallback@example.edu", "request": {"userAttributes": {
            "email": "Student@Example.edu",
            "sub": "cognito-subject-that-is-not-a-profile-id",
            "custom:is_student": "true",
        }}}
        self.assertIs(post_confirmation.handler(event, None), event)
        self.auth.create_profile_on_confirm.assert_called_once_with("student@example.edu", True)

    def test_unverified_email_denied_before_database_access(self):
        event = authenticated_event({"responses": [0] * 23})
        event["requestContext"]["authorizer"]["claims"]["email_verified"] = "false"
        response = submit_assessment.handler(event, None)
        self.assertEqual(response["statusCode"], 401)
        self.profile.ensure_email_profile.assert_not_called()

    def test_signup_marital_status_maps_to_schema_foreign_key(self):
        self.details.create.return_value = {"user_id": "internal-profile-id"}
        self.profile._fetch_one.return_value = {"id": 3}
        response = create_details.handler(authenticated_event({
            "first_name": "Ada", "last_name": "Lovelace", "student_number": "2021-12345-AB-0",
            "birth_date": "2000-01-01", "year": 1, "marital_status": " Single ",
        }), None)
        self.assertEqual(response["statusCode"], 201)
        self.assertEqual(self.details.create.call_args.args[0]["marital_status_id"], 3)
        self.assertEqual(self.profile._fetch_one.call_args.args[1], ("Single",))

    def test_failed_details_save_returns_error_and_rolls_back(self):
        self.details.create.side_effect = RuntimeError("synthetic insert failure")
        with self.assertLogs(create_details.logger, level="ERROR"):
            response = create_details.handler(authenticated_event({
                "first_name": "Ada", "last_name": "Lovelace", "student_number": "2021-12345-AB-0",
                "birth_date": "2000-01-01", "year": 1,
            }), None)
        self.assertEqual(response["statusCode"], 500)
        self.conn.rollback.assert_called_once()
        self.assertNotIn("synthetic insert failure", response["body"])


class ProfileResolutionDALTests(unittest.TestCase):
    def setUp(self):
        from generic_dals.profiles_dal import ProfilesDAL
        self.dal = ProfilesDAL.__new__(ProfilesDAL)
        self.dal._fetch_all = Mock(return_value=[])
        self.dal._execute_write = Mock(return_value={"id": "internal-id"})

    def test_new_profile_uses_email_for_username_and_full_name_not_subject(self):
        self.assertEqual(self.dal.ensure_email_profile(" Student@Example.edu "), {"id": "internal-id"})
        query, params = self.dal._execute_write.call_args.args
        self.assertEqual(params, ("student@example.edu", "student@example.edu", True))
        self.assertIn("(username, full_name, is_student)", query)
        self.assertNotIn("(id,", query)

    def test_existing_profile_retains_id_name_and_role(self):
        self.dal._fetch_all.return_value = [{"id": "historical-id", "username": None, "is_student": True}]
        self.dal.ensure_email_profile("Student@Example.edu")
        query, params = self.dal._execute_write.call_args.args
        self.assertEqual(params, ("student@example.edu", "historical-id"))
        self.assertIn("SET username = %s", query)
        self.assertNotIn("SET full_name", query)
        self.assertNotIn("SET is_student", query)

    def test_wrong_role_is_rejected_without_profile_mutation(self):
        self.dal._fetch_all.return_value = [{"id": "admin-id", "username": "student@example.edu", "is_student": False}]
        with self.assertRaises(ValueError):
            self.dal.ensure_email_profile("student@example.edu")
        self.dal._execute_write.assert_not_called()

    def test_ambiguous_legacy_matches_are_rejected_without_mutation(self):
        self.dal._fetch_all.return_value = [{"id": "one"}, {"id": "two"}]
        with self.assertRaises(ValueError):
            self.dal.ensure_email_profile("student@example.edu")
        self.dal._execute_write.assert_not_called()

    def test_existing_username_is_authoritative_over_fallback_email(self):
        self.dal._fetch_all.return_value = [{"id": "other-id", "username": "owner@example.edu", "is_student": True}]
        with self.assertRaises(ValueError):
            self.dal.ensure_email_profile("student@example.edu")
        self.dal._execute_write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
