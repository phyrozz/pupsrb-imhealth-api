"""HTML helpers for branded student assessment emails."""
import os
from collections.abc import Iterable
from html import escape


CAMPUS_NAME = "Polytechnic University of the Philippines - Santa Rosa Campus"
APP_NAME = "PUP-iMHealth"
LOGO_KEY = "logo.webp"


def assessment_logo_url() -> str | None:
    """Build the public S3 URL for the campus logo."""
    bucket = os.environ.get("S3_PUBLIC_BUCKET_NAME", "").strip()
    if not bucket:
        return None

    region = (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "ap-southeast-1"
    )
    return f"https://{bucket}.s3.{region}.amazonaws.com/{LOGO_KEY}"


def assessment_login_url(app_url: str) -> str:
    """Return the assessment login path below the configured application URL."""
    return f"{app_url.rstrip('/')}/assessment/login"


def brand_assessment_email_text(body_text: str) -> str:
    """Add campus and application identity to the plain-text email alternative."""
    return f"{CAMPUS_NAME}\n{APP_NAME}\n\n{body_text}"


def render_assessment_email_html(
    first_name: str,
    paragraphs: Iterable[str],
    action_label: str,
    action_url: str,
) -> str:
    """Render a branded, email-client-friendly PUP-iMHealth message."""
    greeting_name = escape(first_name or "there")
    paragraph_markup = "".join(
        '<p style="margin:0 0 16px;color:#3f3a3b;font-size:15px;line-height:1.65;">'
        f"{escape(paragraph)}</p>"
        for paragraph in paragraphs
    )
    action_markup = (
        f'<a href="{escape(action_url, quote=True)}" '
        'style="display:inline-block;padding:13px 22px;border-radius:6px;'
        'background-color:#7a1025;color:#ffffff;font-size:15px;font-weight:700;'
        'text-decoration:none;">'
        f"{escape(action_label)}</a>"
    )
    logo_url = assessment_logo_url()
    logo_markup = ""
    if logo_url:
        logo_markup = (
            '<td width="64" valign="middle" style="padding-right:16px;">'
            f'<img src="{escape(logo_url, quote=True)}" alt="PUP logo" '
            'width="56" height="56" '
            'style="display:block;width:56px;height:56px;object-fit:contain;'
            'border:0;border-radius:50%;background-color:#ffffff;">'
            "</td>"
        )

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"<title>{APP_NAME}</title></head>"
        '<body style="margin:0;padding:0;background-color:#f3f1f2;'
        'font-family:Arial,Helvetica,sans-serif;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'border="0" style="background-color:#f3f1f2;">'
        '<tr><td align="center" style="padding:32px 14px;">'
        '<table role="presentation" width="600" cellspacing="0" cellpadding="0" '
        'border="0" style="width:100%;max-width:600px;background-color:#ffffff;'
        'border:1px solid #e5dfe1;border-radius:10px;overflow:hidden;">'
        '<tr><td style="padding:22px 28px;background-color:#7a1025;">'
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0">'
        f"<tr>{logo_markup}<td valign=\"middle\">"
        f'<div style="color:#ffffff;font-size:13px;line-height:1.45;">{CAMPUS_NAME}</div>'
        f'<div style="margin-top:4px;color:#ffffff;font-size:20px;font-weight:700;">{APP_NAME}</div>'
        "</td></tr></table></td></tr>"
        '<tr><td style="padding:30px 32px 28px;">'
        f'<p style="margin:0 0 20px;color:#282425;font-size:16px;line-height:1.5;">'
        f"<strong>Hi, {greeting_name}!</strong></p>"
        f"{paragraph_markup}"
        f'<div style="padding-top:6px;">{action_markup}</div>'
        "</td></tr>"
        '<tr><td style="padding:16px 32px;border-top:1px solid #eee9eb;'
        'color:#746d70;font-size:12px;line-height:1.5;">'
        f"{CAMPUS_NAME} &middot; {APP_NAME}"
        "</td></tr></table></td></tr></table></body></html>"
    )
