import json


def get_body(event):
    body = event.get("body") or "{}"
    if isinstance(body, str):
        return json.loads(body)
    return body


def get_path_param(event, key):
    return (event.get("pathParameters") or {}).get(key)


def get_query_param(event, key, default=None):
    return (event.get("queryStringParameters") or {}).get(key, default)


def get_cognito_user_id(event):
    return (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("claims", {})
        .get("sub")
    )


def get_authenticated_username(event):
    """Link database identities only through a verified Cognito email claim."""
    claims = get_claims(event)
    if str(claims.get("email_verified", "false")).lower() != "true":
        return None
    value = claims.get("email")
    return value.strip().lower() if isinstance(value, str) and value.strip() else None


def get_claims(event) -> dict:
    return (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("claims", {})
    )


def is_student(event) -> bool:
    return get_claims(event).get("custom:is_student", "false").lower() == "true"


def is_admin(event) -> bool:
    return get_claims(event).get("custom:is_student", "false").lower() != "true"
