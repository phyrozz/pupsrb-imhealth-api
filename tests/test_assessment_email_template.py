"""Offline tests for branded assessment email rendering."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


API_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = API_ROOT / "utils" / "assessment_email_template.py"
SPEC = importlib.util.spec_from_file_location("assessment_email_template", TEMPLATE_PATH)
assessment_email_template = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assessment_email_template)


class AssessmentEmailTemplateTests(unittest.TestCase):
    def test_logo_url_uses_public_bucket(self):
        with patch.dict(
            os.environ,
            {
                "S3_BUCKET_NAME": "private-avatar-bucket",
                "S3_PUBLIC_BUCKET_NAME": "imhealth-logo-dev",
                "AWS_REGION": "ap-southeast-1",
            },
            clear=True,
        ):
            url = assessment_email_template.assessment_logo_url()

        self.assertEqual(
            url, "https://imhealth-logo-dev.s3.ap-southeast-1.amazonaws.com/logo.webp"
        )

    def test_private_bucket_is_not_used_as_logo_fallback(self):
        with patch.dict(
            os.environ, {"S3_BUCKET_NAME": "private-avatar-bucket"}, clear=True
        ):
            self.assertIsNone(assessment_email_template.assessment_logo_url())

    def test_html_template_escapes_logo_url(self):
        logo_url = "https://example.com/logo.webp?size=small&format=webp"
        with patch.object(
            assessment_email_template, "assessment_logo_url", return_value=logo_url
        ):
            html = assessment_email_template.render_assessment_email_html(
                "Student", ["Assessment ready."], "Open assessment", "https://example.com/login"
            )

        self.assertIn(
            'src="https://example.com/logo.webp?size=small&amp;format=webp"', html
        )


if __name__ == "__main__":
    unittest.main()
