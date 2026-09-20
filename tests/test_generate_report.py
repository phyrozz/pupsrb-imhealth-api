"""Offline validation for the queued administrator report service."""
import csv
from datetime import datetime, timedelta, timezone
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
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


task_runner = importlib.import_module("services.generate_report.task_runner")
worker = importlib.import_module("services.generate_report.main")
validation = importlib.import_module("services.generate_report.report_validation")


def admin_event(body, *, student=False):
    return {
        "body": json.dumps(body),
        "requestContext": {"authorizer": {"claims": {
            "sub": "authenticated-admin-subject",
            "email": "Admin@Example.edu",
            "email_verified": "true",
            "custom:is_student": "true" if student else "false",
        }}},
    }


def program_request(**filters):
    return {"report_type": "program", "format": "csv", "filters": filters}


class ReportTaskRunnerTests(unittest.TestCase):
    def setUp(self):
        self.conn = Mock()
        self.ecs = Mock()
        self.connection_patch = patch.object(task_runner, "get_db_connection", return_value=self.conn)
        self.runner_patch = patch.object(task_runner, "ECSHelper", return_value=self.ecs)
        self.permission_patch = patch.object(task_runner, "require_permission", return_value=None)
        self.connection = self.connection_patch.start()
        self.runner = self.runner_patch.start()
        self.permission = self.permission_patch.start()
        self.addCleanup(self.connection_patch.stop)
        self.addCleanup(self.runner_patch.stop)
        self.addCleanup(self.permission_patch.stop)
        psycopg2.connect.reset_mock()

    def test_queues_program_report_with_only_verified_caller_email(self):
        response = task_runner.handler(admin_event(program_request(
            programs=["BSIT-SR"], years=[1], recommendations="Follow up"
        )), None)

        self.assertEqual(response["statusCode"], 202)
        self.assertEqual(json.loads(response["body"])["format"], "csv")
        self.permission.assert_has_calls([
            unittest.mock.call(unittest.mock.ANY, self.conn, "reports", "download"),
            unittest.mock.call(unittest.mock.ANY, self.conn, "assessments", "read"),
        ])
        self.runner.assert_called_once_with(task_definition="pupsrb-imhealth-generate-report")
        task_event = self.ecs.run_task.call_args.kwargs["event"]
        self.assertEqual(task_event["recipient_email"], "admin@example.edu")
        self.assertNotIn("recipient_email", task_event["filters"])
        self.assertEqual(self.ecs.run_task.call_args.kwargs["pass_environment"], False)
        self.conn.close.assert_called_once_with()

    def test_student_report_requires_the_student_read_grant(self):
        user_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        response = task_runner.handler(admin_event({
            "report_type": "student", "format": "xlsx", "filters": {"user_id": user_id}
        }), None)

        self.assertEqual(response["statusCode"], 202)
        self.assertEqual(self.permission.call_count, 3)
        self.assertEqual(self.permission.call_args_list[-1].args[2:], ("students", "read"))

    def test_invalid_request_never_opens_a_database_connection(self):
        cases = [
            {"report_type": "student", "format": "pdf", "filters": {}},
            {"report_type": "program", "format": "pdf", "filters": {"user_id": "a"}},
            {"report_type": "program", "format": "zip", "filters": {}},
            {"report_type": "program", "format": "pdf", "filters": {"start_date": "2026-09-31"}},
        ]
        for body in cases:
            with self.subTest(body=body):
                response = task_runner.handler(admin_event(body), None)
                self.assertEqual(response["statusCode"], 400)
        task_runner.get_db_connection.assert_not_called()
        self.ecs.run_task.assert_not_called()

    def test_students_cannot_queue_administrator_reports(self):
        response = task_runner.handler(admin_event(program_request(), student=True), None)

        self.assertEqual(response["statusCode"], 403)
        task_runner.get_db_connection.assert_not_called()

    def test_permission_denial_never_starts_the_ecs_task(self):
        self.permission.return_value = {"statusCode": 403, "body": "denied"}
        response = task_runner.handler(admin_event(program_request()), None)

        self.assertEqual(response["statusCode"], 403)
        self.ecs.run_task.assert_not_called()

    def test_ecs_launch_failure_does_not_return_a_queued_success(self):
        self.ecs.run_task.side_effect = RuntimeError("ECS task did not start")
        response = task_runner.handler(admin_event(program_request()), None)

        self.assertEqual(response["statusCode"], 500)
        self.assertEqual(json.loads(response["body"]), {
            "message": "Unable to start report generation. Please try again later."
        })


class ReportValidationTests(unittest.TestCase):
    def test_task_event_rejects_body_supplied_recipient_and_normalizes_uuid(self):
        event = validation.validate_task_event({
            "report_type": "student",
            "format": "pdf",
            "filters": {"user_id": "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"},
            "recipient_email": "Admin@Example.edu",
        })

        self.assertEqual(event["recipient_email"], "admin@example.edu")
        self.assertEqual(event["filters"]["user_id"], "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        with self.assertRaises(ValueError):
            validation.validate_report_request({
                **program_request(), "recipient_email": "attacker@example.edu"
            })

    def test_select_control_string_ids_are_normalized_to_integers(self):
        report = validation.validate_report_request(program_request(
            years=["1", "2"], counseling_status_ids=["3"], scenario_ids=["0", "1"]
        ))

        self.assertEqual(report["filters"], {
            "years": [1, 2], "counseling_status_ids": [3], "scenario_ids": [0, 1],
        })


class ReportWorkerTests(unittest.TestCase):
    def test_worker_streams_keyset_batches_and_writes_csv_with_formula_protection(self):
        dal = Mock()
        dal.get_report_batch.side_effect = [
            [
                {"assessment_id": 3, "submitted_at": "2026-09-03", "student_name": "=formula", "student_number": "1", "student_email": "one@example.edu", "program_initial": "BSIT-SR", "year_level": 1, "scenario_name": "Scenario 1", "counseling_status": "For Counseling"},
                {"assessment_id": 2, "submitted_at": "2026-09-02", "student_name": "Student", "student_number": "2", "student_email": "two@example.edu", "program_initial": "BSIT-SR", "year_level": 2, "scenario_name": "Scenario 3", "counseling_status": ""},
            ],
            [
                {"assessment_id": 1, "submitted_at": "2026-09-01", "student_name": "Last", "student_number": "3", "student_email": "last@example.edu", "program_initial": "BSIT-SR", "year_level": 3, "scenario_name": "None", "counseling_status": ""},
            ],
        ]
        dal.get_setting.return_value = "Asia/Manila"
        task_event = {
            "report_type": "program", "format": "csv", "recipient_email": "admin@example.edu",
            "filters": {"recommendations": "=Review"},
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(worker, "REPORT_BATCH_SIZE", 2),
            patch.object(worker, "ZoneInfo", return_value=timezone.utc),
        ):
            report_path, count = worker.write_report(dal, task_event, directory=directory)
            with report_path.open(newline="", encoding="utf-8") as report_file:
                contents = list(csv.reader(report_file))
            report_path.unlink()

        self.assertEqual(count, 3)
        self.assertEqual(dal.get_report_batch.call_args_list[0].args, ({"recommendations": "=Review"}, 2, None))
        self.assertEqual(dal.get_report_batch.call_args_list[1].args[2], ("2026-09-02", 2))
        self.assertIn("'=Review", contents[3])
        self.assertIn("'=formula", contents[6])

    def test_worker_uses_configured_iana_timezone_for_one_report_timestamp_and_rows(self):
        dal = Mock()
        dal.get_setting.return_value = "Asia/Manila"
        submitted_at = datetime(2026, 9, 20, 0, 30, tzinfo=timezone.utc)
        dal.get_report_batch.side_effect = [[{
            "assessment_id": 1, "submitted_at": submitted_at, "student_name": "Student",
            "student_number": "1", "student_email": "student@example.edu",
            "program_initial": "BSIT-SR", "year_level": 1, "scenario_name": "Scenario 1",
            "counseling_status": "For Counseling",
        }]]
        task_event = {
            "report_type": "program", "format": "csv", "recipient_email": "admin@example.edu",
            "filters": {},
        }
        manila = timezone(timedelta(hours=8), "PST")
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(worker, "ZoneInfo", return_value=manila),
        ):
            report_path, _ = worker.write_report(dal, task_event, directory=directory)
            with report_path.open(newline="", encoding="utf-8") as report_file:
                contents = list(csv.reader(report_file))
            report_path.unlink()

        self.assertEqual(dal.get_setting.call_args.args, ("report_timestamp_timezone",))
        self.assertIn("Asia/Manila", contents[1][1])
        self.assertEqual(contents[6][0], "2026-09-20 08:30 PST")

    def test_report_filename_uses_the_configured_generation_timestamp(self):
        generated_at = datetime(2026, 9, 20, 8, 30, 45, tzinfo=timezone(timedelta(hours=8)))

        self.assertEqual(
            worker.report_filename(generated_at, "xlsx"),
            "imhealth-report-20260920T083045+0800.xlsx",
        )

    def test_worker_rejects_missing_or_invalid_timezone_settings_before_querying_rows(self):
        for setting in (None, "Not/A_Timezone", ""):
            with self.subTest(setting=setting):
                dal = Mock()
                dal.get_setting.return_value = setting
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaisesRegex(RuntimeError, "timezone setting"):
                        worker.write_report(dal, {
                            "report_type": "program", "format": "csv",
                            "recipient_email": "admin@example.edu", "filters": {},
                        }, directory=directory)
                dal.get_report_batch.assert_not_called()

    def test_worker_passes_the_configured_iana_name_to_zoneinfo_once(self):
        dal = Mock()
        dal.get_setting.return_value = "Asia/Manila"
        manila = timezone(timedelta(hours=8), "PST")
        with patch.object(worker, "ZoneInfo", return_value=manila) as zone_info:
            result, timezone_name = worker.get_report_timezone(dal)

        self.assertIs(result, manila)
        self.assertEqual(timezone_name, "Asia/Manila")
        zone_info.assert_called_once_with("Asia/Manila")

    def test_xlsx_assessment_header_cells_are_bold(self):
        class FakeFont:
            def __init__(self, *, bold=False):
                self.bold = bold

        class FakeCell:
            def __init__(self, sheet, value):
                self.sheet = sheet
                self.value = value
                self.font = None

        class FakeSheet:
            def __init__(self):
                self.rows = []

            def append(self, row):
                self.rows.append(row)

        class FakeWorkbook:
            instance = None

            def __init__(self, *, write_only=False):
                self.write_only = write_only
                self.sheets = []
                self.__class__.instance = self

            def create_sheet(self, name):
                sheet = FakeSheet()
                self.sheets.append((name, sheet))
                return sheet

            def save(self, path):
                Path(path).write_bytes(b"xlsx")

        openpyxl = types.ModuleType("openpyxl")
        openpyxl.Workbook = FakeWorkbook
        cell_module = types.ModuleType("openpyxl.cell")
        cell_module.WriteOnlyCell = FakeCell
        styles_module = types.ModuleType("openpyxl.styles")
        styles_module.Font = FakeFont
        event = {
            "report_type": "program", "format": "xlsx", "recipient_email": "admin@example.edu",
            "filters": {},
        }
        manila = timezone(timedelta(hours=8), "PST")
        generated_at = datetime(2026, 9, 20, 8, 45, 6, tzinfo=manila)
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, {
            "openpyxl": openpyxl, "openpyxl.cell": cell_module, "openpyxl.styles": styles_module,
        }):
            worker._write_xlsx(
                Path(directory) / "report.xlsx", iter(()), event, generated_at, "Asia/Manila",
                manila,
            )

        self.assertIn("2026-09-20 08:45:06 PST (Asia/Manila)", FakeWorkbook.instance.sheets[0][1].rows[1])
        header = FakeWorkbook.instance.sheets[1][1].rows[0]
        self.assertEqual([cell.value for cell in header], [column for column, _ in worker.REPORT_COLUMNS])
        self.assertTrue(all(cell.font.bold for cell in header))

    def test_worker_requires_a_valid_task_event_before_database_access(self):
        with self.assertRaisesRegex(ValueError, "TASK_EVENT"):
            worker.load_task_event("{bad json")
        with self.assertRaisesRegex(ValueError, "TASK_EVENT"):
            worker.load_task_event(json.dumps({"report_type": "program"}))

    def test_email_attachment_uses_the_task_sender_and_recipient(self):
        ses = Mock()
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.csv"
            report_path.write_text("header\n", encoding="utf-8")
            worker.send_report_email(ses, "sender@example.edu", "admin@example.edu", report_path, 4)

        sent = ses.send_raw_email.call_args.kwargs
        self.assertEqual(sent["Source"], "sender@example.edu")
        self.assertEqual(sent["Destinations"], ["admin@example.edu"])
        self.assertIn("report.csv", sent["RawMessage"]["Data"])

    def test_main_cleans_the_generated_file_after_ses_delivery(self):
        conn, ses = Mock(), Mock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "generated.pdf"
            path.write_bytes(b"report")
            event = {
                "report_type": "program", "format": "pdf", "recipient_email": "admin@example.edu",
                "filters": {},
            }
            with patch.object(worker, "load_task_event", return_value=event), \
                 patch.object(worker, "get_db_connection", return_value=conn), \
                 patch.object(worker, "ReportDAL", return_value=Mock()), \
                 patch.object(worker, "write_report", return_value=(path, 1)), \
                 patch.object(worker.boto3, "client", return_value=ses), \
                 patch.object(worker, "send_report_email") as send_email, \
                 patch.dict(os.environ, {"SES_FROM_EMAIL": "sender@example.edu"}, clear=False):
                worker.main()
            self.assertFalse(path.exists())

        send_email.assert_called_once_with(ses, "sender@example.edu", "admin@example.edu", path, 1)
        conn.close.assert_called_once_with()

    def test_pdf_paginates_a_valid_long_recommendation(self):
        class FakeCanvas:
            instances = []

            def __init__(self, *args, **kwargs):
                self.show_page_calls = 0
                self.saved = False
                self.__class__.instances.append(self)

            def setFont(self, *args, **kwargs):
                pass

            def drawString(self, *args, **kwargs):
                pass

            def showPage(self):
                self.show_page_calls += 1

            def save(self):
                self.saved = True

        reportlab = types.ModuleType("reportlab")
        reportlab.__path__ = []
        lib = types.ModuleType("reportlab.lib")
        lib.__path__ = []
        pagesizes = types.ModuleType("reportlab.lib.pagesizes")
        pagesizes.letter = (612, 792)
        pagesizes.landscape = lambda size: (792, 612)
        pdfgen = types.ModuleType("reportlab.pdfgen")
        pdfgen.__path__ = []
        canvas_module = types.ModuleType("reportlab.pdfgen.canvas")
        canvas_module.Canvas = FakeCanvas
        reportlab.lib = lib
        lib.pagesizes = pagesizes
        reportlab.pdfgen = pdfgen
        pdfgen.canvas = canvas_module
        modules = {
            "reportlab": reportlab,
            "reportlab.lib": lib,
            "reportlab.lib.pagesizes": pagesizes,
            "reportlab.pdfgen": pdfgen,
            "reportlab.pdfgen.canvas": canvas_module,
        }
        event = {
            "report_type": "program", "format": "pdf", "recipient_email": "admin@example.edu",
            "filters": {"recommendations": "safe " * 2300},
        }
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, modules):
            count = worker._write_pdf(Path(directory) / "report.pdf", iter(()), event)

        self.assertEqual(count, 0)
        self.assertGreater(FakeCanvas.instances[0].show_page_calls, 0)
        self.assertTrue(FakeCanvas.instances[0].saved)


class ReportDALTests(unittest.TestCase):
    def test_query_uses_public_baseline_tables_and_descending_keyset(self):
        from generic_dals.report_dal import ReportDAL

        dal = ReportDAL.__new__(ReportDAL)
        dal._fetch_all = Mock(return_value=[])
        filters = {"programs": ["BSIT-SR"], "years": [1], "user_id": "student-id"}
        dal.get_report_batch(filters, 500, ("2026-09-02", 2))

        query, params = dal._fetch_all.call_args.args
        self.assertIn("FROM public.assessments a", query)
        self.assertIn("LEFT JOIN public.apriori_results ar", query)
        self.assertIn("LEFT JOIN public.personal_details pd", query)
        self.assertIn("(a.created_at, a.id) < (%s, %s)", query)
        self.assertIn("ORDER BY a.created_at DESC, a.id DESC", query)
        self.assertEqual(params, (["BSIT-SR"], [1], "student-id", "2026-09-02", 2, 500))


class ReportDeploymentDefinitionTests(unittest.TestCase):
    def test_service_uses_the_dedicated_lambda_and_fargate_entry_points(self):
        service_dir = API_ROOT / "services" / "generate_report"
        serverless = (service_dir / "serverless.yml").read_text(encoding="utf-8")
        dockerfile = (service_dir / "Dockerfile").read_text(encoding="utf-8")
        task_definition = (service_dir / "ecs-task-definition.json").read_text(encoding="utf-8")

        self.assertIn("path: /generate-report", serverless)
        self.assertIn("handler: task_runner.handler", serverless)
        self.assertIn('CMD ["python", "services/generate_report/main.py"]', dockerfile)
        self.assertIn('"family": "pupsrb-imhealth-generate-report"', task_definition)
        self.assertIn('"name": "SES_FROM_EMAIL"', task_definition)
        self.assertIn('"name": "DB_PASSWORD"', task_definition)
        self.assertNotIn('"name": "TASK_EVENT"', task_definition)


if __name__ == "__main__":
    unittest.main()
