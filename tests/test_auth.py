import jwt
import pytest
from fastapi import HTTPException

from app.auth import CurrentUser, decode_cognito_token, get_current_user


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


def test_get_current_user_sets_user_id_context(monkeypatch):
    from app.observability.context import user_id_var

    fake_user = CurrentUser(sub="user-123", email="u@example.com", role="Viewer")
    monkeypatch.setattr("app.auth.decode_cognito_token", lambda token: fake_user)

    try:
        result = get_current_user(authorization="Bearer sometoken")

        assert result is fake_user
        assert user_id_var.get() == "user-123"
    finally:
        # get_current_user has no request-scoped teardown of its own (that's
        # the HTTP middleware's job) — reset here so this contextvar mutation
        # doesn't leak into later tests sharing this thread's context.
        user_id_var.set(None)
