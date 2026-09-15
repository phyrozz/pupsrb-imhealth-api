import sys
import os
import logging
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.db import get_db_connection
from utils.response import success, error
from utils.request import get_authenticated_username, get_body, get_cognito_user_id
from generic_dals.assessments_dal import AssessmentsDAL
from generic_dals.profiles_dal import ProfilesDAL
from utils.assessment_email import send_submission_confirmation
from utils.assessment_settings import get_positive_integer

logger = logging.getLogger(__name__)

RESPONSE_VALUES = {
    "Not at all": 0,
    "Slight": 1,
    "Mild": 2,
    "Moderate": 3,
    "Severe": 4,
}

DOMAIN_QUESTIONS = {
    "I": (0, 1), "II": (2,), "III": (3, 4), "IV": (5, 6, 7),
    "V": (8, 9), "VI": (10,), "VII": (11, 12), "VIII": (13,),
    "IX": (14,), "X": (15, 16), "XI": (17,), "XII": (18, 19),
    "XIII": (20, 21, 22),
}


def _normalise_responses(responses: list) -> list[int]:
    normalised = []
    for response in responses:
        if isinstance(response, bool):
            raise ValueError
        if isinstance(response, int) and 0 <= response <= 4:
            normalised.append(response)
        elif isinstance(response, str) and response in RESPONSE_VALUES:
            normalised.append(RESPONSE_VALUES[response])
        else:
            raise ValueError
    return normalised


def _has_response_at_least(responses: list[int], domains: tuple[str, ...], threshold: int) -> bool:
    return any(
        responses[index] >= threshold
        for domain in domains
        for index in DOMAIN_QUESTIONS[domain]
    )


def _compute_apriori(responses: list[int], previous_responses: list[int] | None) -> int:
    improvement_domains = ("I", "II", "III", "IV", "V", "VIII", "X", "XIII")
    if previous_responses and len(previous_responses) == len(responses):
        previous_has_concern = _has_response_at_least(previous_responses, improvement_domains, 2)
        current_has_no_improvement = any(
            responses[index] < 2
            for domain in improvement_domains
            for index in DOMAIN_QUESTIONS[domain]
        )
        if previous_has_concern and current_has_no_improvement:
            return 1

    if _has_response_at_least(responses, tuple(DOMAIN_QUESTIONS), 3):
        return 3
    if _has_response_at_least(responses, ("VI", "VII", "IX", "XI", "XII"), 1):
        return 2
    return 0


def _format_next_available_at(next_available_at: datetime) -> str:
    return next_available_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def handler(event, context):
    user_id = get_cognito_user_id(event)
    username = get_authenticated_username(event)
    if not user_id or not username:
        return error("Unauthorized", 401)
    body = get_body(event)
    responses = body.get("responses", [])
    if len(responses) != 23:
        return error("responses must contain exactly 23 values", 400)
    try:
        responses = _normalise_responses(responses)
    except ValueError:
        return error("responses must use the supported assessment rating values", 400)

    conn = get_db_connection()
    try:
        profile = ProfilesDAL(conn).ensure_email_profile(username)
        if not profile:
            return error("Account profile is not ready. Please sign in again.", 409)
        profile_id = profile["id"]
        assessments = AssessmentsDAL(conn)
        assessments.acquire_submission_lock(profile_id)
        cooldown_days = get_positive_integer(assessments.get_cooldown_days())
        if cooldown_days is None:
            return error("Assessment scheduling is not configured. Please try again later.", 503)
        next_available_at = assessments.get_next_submission_at(profile_id, cooldown_days)
        now = datetime.now(timezone.utc)
        if next_available_at and next_available_at > now:
            formatted_next = _format_next_available_at(next_available_at)
            return error(
                f"You can submit another assessment on {formatted_next}.",
                429,
                next_available_at=formatted_next,
            )
        previous_responses = assessments.get_latest_responses(profile_id)
        if previous_responses is not None:
            try:
                previous_responses = _normalise_responses(previous_responses)
            except (TypeError, ValueError):
                logger.warning("Ignoring malformed responses on the previous assessment")
                previous_responses = None
        result = assessments.create_assessment(
            profile_id,
            responses,
            _compute_apriori(responses, previous_responses),
        )
        submitted_at = result["assessment"].get("created_at")
        if not isinstance(submitted_at, datetime):
            submitted_at = datetime.now(timezone.utc)
        next_available_at = submitted_at + timedelta(days=cooldown_days)
        result["next_available_at"] = _format_next_available_at(next_available_at)
        try:
            send_submission_confirmation(username, next_available_at)
            result["notification_sent"] = True
        except Exception:
            logger.exception("Assessment submission confirmation email failed")
            result["notification_sent"] = False
        return success(result, 201)
    except ValueError as e:
        conn.rollback()
        return error(str(e), 409)
    except Exception:
        logger.exception("Assessment submission failed")
        try:
            conn.rollback()
        except Exception:
            logger.exception("Assessment submission rollback failed")
        return error("Unable to submit assessment. Please try again later.")
    finally:
        conn.close()
