import pytest
from sqlalchemy import Engine

from app.config import settings
from app.db import get_engine


@pytest.fixture(scope="session")
def engine() -> Engine:
    return get_engine()


@pytest.mark.integration
def test_local_database_is_reachable(engine):
    with engine.connect() as conn:
        assert conn.execute(__import__("sqlalchemy").text("SELECT 1")).scalar() == 1


import boto3


@pytest.fixture(scope="session")
def cognito_tokens():
    import os
    client = boto3.client("cognito-idp", region_name=os.environ["COGNITO_REGION"])
    app_client_id = os.environ["COGNITO_APP_CLIENT_ID"]

    def _fetch(email_var, password_var):
        resp = client.initiate_auth(
            ClientId=app_client_id, AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": os.environ[email_var], "PASSWORD": os.environ[password_var]},
        )
        return resp["AuthenticationResult"]["IdToken"]

    return {
        "Viewer": _fetch("COGNITO_TEST_VIEWER_EMAIL", "COGNITO_TEST_VIEWER_PASSWORD"),
        "SupportAgent": _fetch("COGNITO_TEST_SUPPORT_EMAIL", "COGNITO_TEST_SUPPORT_PASSWORD"),
        "OperationsManager": _fetch("COGNITO_TEST_MANAGER_EMAIL", "COGNITO_TEST_MANAGER_PASSWORD"),
    }
