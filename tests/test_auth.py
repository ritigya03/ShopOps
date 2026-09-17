import jwt
import pytest
from fastapi import HTTPException

from app.auth import decode_cognito_token, get_current_user


@pytest.mark.integration
def test_decode_valid_viewer_token(cognito_tokens):
    user = decode_cognito_token(cognito_tokens["Viewer"])
    assert user.role == "Viewer"
    assert user.email


def test_decode_rejects_garbage_token():
    with pytest.raises(jwt.InvalidTokenError):
        decode_cognito_token("not-a-real-token")


@pytest.mark.integration
def test_get_current_user_rejects_token_with_unknown_kid():
    # A well-formed JWT (unlike the garbage-string case above) whose kid
    # isn't in this pool's JWKS — this is the case that raises
    # jwt.PyJWKClientError, not jwt.InvalidTokenError, and must still
    # come back as a clean 401 rather than an unhandled 500.
    bogus_token = jwt.encode(
        {"sub": "someone"}, "irrelevant-secret-that-is-long-enough-32b", algorithm="HS256",
        headers={"kid": "nonexistent-kid"},
    )
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {bogus_token}")
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_missing_header():
    # authorization: str | None = Header(default=None) is what makes this
    # 401 instead of FastAPI's own 422 request-validation rejection for a
    # required Header(...) parameter.
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=None)
    assert exc_info.value.status_code == 401
