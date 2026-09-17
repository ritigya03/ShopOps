#!/usr/bin/env python3
"""One-off check that Cognito is set up correctly: fetches a real ID
token for each of the three test users and prints its claims. Run this
once after Task 1's console setup, and again any time token retrieval
breaks, to isolate whether the problem is Cognito config or app code.
"""
import os

import boto3
import jwt
from dotenv import load_dotenv

load_dotenv()

ROLE_USERS = [
    ("Viewer", "COGNITO_TEST_VIEWER_EMAIL", "COGNITO_TEST_VIEWER_PASSWORD"),
    ("SupportAgent", "COGNITO_TEST_SUPPORT_EMAIL", "COGNITO_TEST_SUPPORT_PASSWORD"),
    ("OperationsManager", "COGNITO_TEST_MANAGER_EMAIL", "COGNITO_TEST_MANAGER_PASSWORD"),
]


def fetch_id_token(client, app_client_id, email, password):
    resp = client.initiate_auth(
        ClientId=app_client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": password},
    )
    return resp["AuthenticationResult"]["IdToken"]


def main():
    region = os.environ["COGNITO_REGION"]
    app_client_id = os.environ["COGNITO_APP_CLIENT_ID"]
    client = boto3.client("cognito-idp", region_name=region)

    for role_label, email_var, password_var in ROLE_USERS:
        email = os.environ[email_var]
        password = os.environ[password_var]
        token = fetch_id_token(client, app_client_id, email, password)
        claims = jwt.decode(token, options={"verify_signature": False})
        print(f"{role_label}: groups={claims.get('cognito:groups')} "
              f"email={claims.get('email')} aud={claims.get('aud')}")


if __name__ == "__main__":
    main()
