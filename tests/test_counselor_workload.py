"""Offline authorization checks for counselor workload handlers."""
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
os.environ["AWS_PROFILE"] = os.environ["AWS_DEFAULT_PROFILE"] = "imhealth-dev"

def forbidden(*args, **kwargs):
    raise AssertionError("External calls are forbidden")

pg = types.ModuleType("psycopg2"); pg.connect = Mock(side_effect=forbidden); pg.Error = Exception
extras = types.ModuleType("psycopg2.extras"); extras.RealDictCursor = object
sys.modules["psycopg2"] = pg; sys.modules["psycopg2.extras"] = extras
aws = types.ModuleType("boto3"); aws.client = aws.resource = aws.Session = forbidden; sys.modules["boto3"] = aws
workload = importlib.import_module("services.assessments.counselor_workload")

ASSESSMENT_ID = 1
COUNSELOR_ID = "00000000-0000-0000-0000-000000000002"

class WorkloadHandlerTests(unittest.TestCase):
    def event(self, method="GET", scope="mine", body=None):
        return {"queryStringParameters": {"scope": scope}, "pathParameters": {"assessment_id": str(ASSESSMENT_ID)},
                "body": json.dumps(body) if body is not None else None, "httpMethod": method,
                "requestContext": {"authorizer": {"claims": {"sub": "subject", "email": "counselor@example.edu", "email_verified": "true", "custom:is_student": "false"}}}}

    def test_counselor_can_read_only_mine_or_unassigned(self):
        conn, dal = Mock(), Mock(); dal.list_items.return_value = []
        identity = {"admin_id": COUNSELOR_ID, "role_id": 1, "role_name": "guidance_counselor"}
        with patch.object(workload, "get_db_connection", return_value=conn), patch.object(workload, "_workload_identity", return_value=(identity, None)), patch.object(workload, "CounselorWorkloadDAL", return_value=dal):
            response = workload.list_handler(self.event(scope="mine"), None)
        self.assertEqual(response["statusCode"], 200)
        dal.list_items.assert_called_once_with(COUNSELOR_ID, "mine", 1, 30)
        conn.close.assert_called_once()

    def test_page_returns_only_requested_items_and_has_more(self):
        conn, dal = Mock(), Mock()
        dal.list_items.return_value = [{"assessment_id": i} for i in range(3)]
        identity = {"admin_id": COUNSELOR_ID, "role_id": 1, "role_name": "guidance_counselor"}
        event = self.event()
        event["queryStringParameters"].update({"page": "2", "page_size": "2"})
        with patch.object(workload, "get_db_connection", return_value=conn), patch.object(workload, "_workload_identity", return_value=(identity, None)), patch.object(workload, "CounselorWorkloadDAL", return_value=dal):
            response = workload.list_handler(event, None)
        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(len(body["items"]), 2)
        self.assertTrue(body["has_more"])
        dal.list_items.assert_called_once_with(COUNSELOR_ID, "mine", 2, 2)

    def test_invalid_pagination_rejected_before_database_access(self):
        for page, page_size in [("0", "30"), ("1", "0"), ("1", "101"), ("bad", "30")]:
            event = self.event()
            event["queryStringParameters"].update({"page": page, "page_size": page_size})
            with self.subTest(page=page, page_size=page_size), patch.object(workload, "get_db_connection", side_effect=forbidden):
                response = workload.list_handler(event, None)
                self.assertEqual(response["statusCode"], 400)

    def test_counselor_cannot_read_everyone_workload(self):
        conn = Mock()
        identity = {"admin_id": COUNSELOR_ID, "role_id": 1, "role_name": "guidance_counselor"}
        with patch.object(workload, "get_db_connection", return_value=conn), patch.object(workload, "_workload_identity", return_value=(identity, None)):
            response = workload.list_handler(self.event(scope="all"), None)
        self.assertEqual(response["statusCode"], 400)
        conn.close.assert_called_once()

    def test_claim_is_limited_to_guidance_counselor(self):
        conn, dal = Mock(), Mock(); dal.claim.return_value = {"assessment_id": ASSESSMENT_ID}
        identity = {"admin_id": COUNSELOR_ID, "role_id": 3, "role_name": "su_admin"}
        with patch.object(workload, "get_db_connection", return_value=conn), patch.object(workload, "_workload_identity", return_value=(identity, None)), patch.object(workload, "CounselorWorkloadDAL", return_value=dal):
            response = workload.claim_handler(self.event(method="POST"), None)
        self.assertEqual(response["statusCode"], 403)
        dal.claim.assert_not_called()

    def test_counselor_updates_only_own_item(self):
        conn, dal = Mock(), Mock(); dal.update_mine.return_value = {"status": "in_review"}
        identity = {"admin_id": COUNSELOR_ID, "role_id": 1, "role_name": "guidance_counselor"}
        with patch.object(workload, "get_db_connection", return_value=conn), patch.object(workload, "_workload_identity", return_value=(identity, None)), patch.object(workload, "CounselorWorkloadDAL", return_value=dal):
            response = workload.update_handler(self.event(method="PUT", body={"status": "in_review"}), None)
        self.assertEqual(response["statusCode"], 200)
        dal.update_mine.assert_called_once_with(ASSESSMENT_ID, COUNSELOR_ID, "in_review")

    def test_super_admin_assignment_uses_only_guidance_counselors(self):
        from generic_dals.counselor_workload_dal import CounselorWorkloadDAL
        dal = CounselorWorkloadDAL.__new__(CounselorWorkloadDAL)
        dal._execute_write = Mock(return_value={})
        dal.manage(ASSESSMENT_ID, COUNSELOR_ID, "assigned")
        query = dal._execute_write.call_args.args[0]
        self.assertIn("role.role_name = 'guidance_counselor'", query)

    def test_workload_trend_is_computed_before_scope_and_prioritized(self):
        from generic_dals.counselor_workload_dal import CounselorWorkloadDAL
        dal = CounselorWorkloadDAL.__new__(CounselorWorkloadDAL)
        dal._fetch_all = Mock(return_value=[])
        dal.list_items(COUNSELOR_ID, "mine")
        query, params = dal._fetch_all.call_args.args
        self.assertEqual(params, (COUNSELOR_ID, 31, 0))
        self.assertIn("LAG(ar.apriori_result) OVER", query)
        self.assertIn("PARTITION BY a.user_id ORDER BY a.created_at, a.id", query)
        self.assertLess(query.index("FROM public.assessments a"), query.index("WHERE w.assigned_admin_id = %s"))
        self.assertIn("a.scenario_id > a.previous_scenario_id", query)
        self.assertIn("previous_s.name AS previous_scenario", query)
        self.assertIn("COALESCE(pd.email, p.username, '') AS email", query)
        self.assertIn("COALESCE(program.initial, '') AS program_initial", query)
        self.assertIn("COALESCE(marital_status.status, '') AS marital_status", query)
        self.assertIn("ORDER BY scenario_increased DESC, a.created_at ASC, a.id ASC", query)
        self.assertIn("LIMIT %s OFFSET %s", query)
        dal.list_items(COUNSELOR_ID, "unassigned", 3, 20)
        self.assertEqual(dal._fetch_all.call_args.args[1], (21, 40))

    def tearDown(self):
        pg.connect.assert_not_called()

if __name__ == "__main__":
    unittest.main()
