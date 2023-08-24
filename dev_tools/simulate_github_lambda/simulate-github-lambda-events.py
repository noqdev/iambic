from __future__ import annotations

import os
from functools import cache
from unittest.mock import patch

import boto3
import yaml

from iambic.plugins.v0_1_0.github.github_app import run_handler

DEV_REGION = os.environ.get("DEV_REGION", "us-west-2")
DEV_EMAIL_DOMAIN_SUFFIX = os.environ.get("DEV_EMAIL_DOMAIN_SUFFIX", "@example.com")
DEV_ACCOUNT_ID = os.environ.get("DEV_ACCOUNT_ID", "")

# You cannot proceed without these values. Check your environment setup.
assert DEV_ACCOUNT_ID


@cache
def _get_app_secrets_as_lambda_context_current() -> dict:
    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=DEV_REGION)

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId="iambic/github-app-secrets"
        )
    except Exception as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    # Decrypts secret using the associated KMS key.
    return yaml.safe_load(get_secret_value_response["SecretString"])


if __name__ == "__main__":

    # to simulate lambda, we are pretending to be a lambda function
    os.environ["AWS_LAMBDA_FUNCTION_NAME"] = "simulate-github-lambda.py"

    req = {"source": "EventBridgeCron", "command": "import"}

    with patch(
        "iambic.plugins.v0_1_0.github.github_app._get_app_secrets_as_lambda_context_current",
        new=_get_app_secrets_as_lambda_context_current,
    ):
        run_handler(req, None)
