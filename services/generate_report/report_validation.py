"""Pure validation shared by the report Lambda and Fargate worker."""
from datetime import date
import re
from uuid import UUID


REPORT_TYPES = {"program", "student"}
REPORT_FORMATS = {"pdf", "csv", "xlsx"}
FILTER_KEYS = {
    "programs",
    "years",
    "counseling_status_ids",
    "scenario_ids",
    "start_date",
    "end_date",
    "user_id",
    "recommendations",
}
EMAIL_PATTERN = re.compile(r"^[^@\s]{1,254}@[^@\s]+\.[^@\s]+$")
MAX_VALUES_PER_FILTER = 100
MAX_RECOMMENDATIONS_LENGTH = 12000


def _invalid(message: str):
    raise ValueError(message)


def _string_list(value, name: str) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_VALUES_PER_FILTER:
        _invalid(f"{name} must be an array with at most {MAX_VALUES_PER_FILTER} values.")

    result = []
    for item in value:
        if not isinstance(item, str):
            _invalid(f"{name} must contain strings.")
        cleaned = item.strip()
        if not cleaned or len(cleaned) > 100:
            _invalid(f"{name} contains an invalid value.")
        if cleaned not in result:
            result.append(cleaned)
    return result


def _integer_list(value, name: str, *, minimum: int, maximum: int) -> list[int]:
    if not isinstance(value, list) or len(value) > MAX_VALUES_PER_FILTER:
        _invalid(f"{name} must be an array with at most {MAX_VALUES_PER_FILTER} values.")

    result = []
    for item in value:
        # The current select controls submit string IDs. Normalize those at the
        # boundary while still rejecting floats, booleans, and signed values.
        if type(item) is int:
            parsed = item
        elif isinstance(item, str) and item.strip().isdecimal():
            parsed = int(item.strip())
        else:
            _invalid(f"{name} contains an invalid value.")
        if not minimum <= parsed <= maximum:
            _invalid(f"{name} contains an invalid value.")
        if parsed not in result:
            result.append(parsed)
    return result


def _date_value(value, name: str) -> str:
    if not isinstance(value, str) or len(value) != 10:
        _invalid(f"{name} must use YYYY-MM-DD.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _invalid(f"{name} must use YYYY-MM-DD.")
    if parsed.isoformat() != value:
        _invalid(f"{name} must use YYYY-MM-DD.")
    return value


def validate_filters(value, report_type: str) -> dict:
    if not isinstance(value, dict):
        _invalid("filters must be an object.")
    unknown = set(value) - FILTER_KEYS
    if unknown:
        _invalid("filters contains unsupported fields.")

    filters = {}
    if "programs" in value:
        filters["programs"] = _string_list(value["programs"], "programs")
    if "years" in value:
        filters["years"] = _integer_list(value["years"], "years", minimum=1, maximum=5)
    if "counseling_status_ids" in value:
        filters["counseling_status_ids"] = _integer_list(
            value["counseling_status_ids"], "counseling_status_ids", minimum=0, maximum=1_000_000
        )
    if "scenario_ids" in value:
        filters["scenario_ids"] = _integer_list(
            value["scenario_ids"], "scenario_ids", minimum=0, maximum=1_000_000
        )
    if "start_date" in value:
        filters["start_date"] = _date_value(value["start_date"], "start_date")
    if "end_date" in value:
        filters["end_date"] = _date_value(value["end_date"], "end_date")
    if filters.get("start_date") and filters.get("end_date"):
        if filters["start_date"] > filters["end_date"]:
            _invalid("start_date must be on or before end_date.")

    if "recommendations" in value:
        recommendations = value["recommendations"]
        if not isinstance(recommendations, str) or len(recommendations) > MAX_RECOMMENDATIONS_LENGTH:
            _invalid(f"recommendations must be text with at most {MAX_RECOMMENDATIONS_LENGTH} characters.")
        filters["recommendations"] = recommendations.strip()

    user_id = value.get("user_id")
    if report_type == "student":
        if not isinstance(user_id, str):
            _invalid("user_id is required for student reports.")
        try:
            filters["user_id"] = str(UUID(user_id.strip()))
        except (ValueError, AttributeError):
            _invalid("user_id must be a UUID.")
    elif "user_id" in value:
        _invalid("user_id is only allowed for student reports.")

    return filters


def validate_report_request(body) -> dict:
    if not isinstance(body, dict):
        _invalid("Request body must be an object.")
    allowed = {"report_type", "format", "filters"}
    if set(body) - allowed:
        _invalid("Request body contains unsupported fields.")

    report_type = body.get("report_type")
    output_format = body.get("format")
    if report_type not in REPORT_TYPES:
        _invalid("report_type must be program or student.")
    if output_format not in REPORT_FORMATS:
        _invalid("format must be pdf, csv, or xlsx.")
    if "filters" not in body:
        _invalid("filters is required.")

    return {
        "report_type": report_type,
        "format": output_format,
        "filters": validate_filters(body["filters"], report_type),
    }


def validate_task_event(task_event) -> dict:
    """Validate the only data the Lambda is allowed to pass to the ECS task."""
    if not isinstance(task_event, dict):
        _invalid("TASK_EVENT must be an object.")
    if set(task_event) != {"report_type", "format", "filters", "recipient_email"}:
        _invalid("TASK_EVENT has an invalid shape.")
    request = validate_report_request({
        "report_type": task_event["report_type"],
        "format": task_event["format"],
        "filters": task_event["filters"],
    })
    recipient = task_event["recipient_email"]
    if not isinstance(recipient, str) or not EMAIL_PATTERN.fullmatch(recipient):
        _invalid("TASK_EVENT recipient_email is invalid.")
    request["recipient_email"] = recipient.lower()
    return request
