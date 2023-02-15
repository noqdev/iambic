#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Callable
import boto3
from botocore.exceptions import ClientError

import github
import jwt
import requests
from iambic.cicd.github import format_github_url, handle_iambic_git_plan

from iambic.core.logger import log

GITHUB_APP_ID = "293178"  # FIXME
GITHUB_APP_PEM_PATH = "/Users/stevenmoy/Downloads/steven-test-github-app.2023-02-13.private-key.pem"  # FIXME
INSTANCE_OF_APP_INSTALLATION = "34179484"  # FIXME


# FIXME Lambda execution time is at most 15 minutes, and the Github installation token is at most
# 10 min validation period. 

# FIXME struct logs is not showing up on lambda cloudwatch logs


def get_app_bearer_token() -> str:
    # FIXME PEM PATH
    pem = GITHUB_APP_PEM_PATH
    # FIXME app_id
    app_id = GITHUB_APP_ID

    payload = {
        # Issued at time
        "iat": int(time.time()),
        # JWT expiration time (10 minutes maximum)
        "exp": int(time.time()) + 600,
        # GitHub App's identifier
        "iss": app_id,
    }

    # Create JWT
    return jwt.encode(payload, get_app_private_key(), algorithm="RS256")

def get_app_bearer_token(private_key, app_id) -> str:

    payload = {
        # Issued at time
        "iat": int(time.time()),
        # JWT expiration time (10 minutes maximum)
        "exp": int(time.time()) + 600,
        # GitHub App's identifier
        "iss": app_id,
    }

    # Create JWT
    return jwt.encode(payload, private_key, algorithm="RS256")


def get_app_private_key() -> str:
    # Open PEM
    with open(GITHUB_APP_PEM_PATH, "rb") as pem_file:
        signing_key = pem_file.read()
    return signing_key


def list_installations() -> list:
    encoded_jwt = get_app_bearer_token()
    response = requests.get(
        "https://api.github.com/app/installations",
        headers={
            "Accept": "application/vnd.github.v3.text-match+json",
            "Authorization": f"Bearer {encoded_jwt}",
        },
    )
    installations = json.loads(response.text)
    return installations


def get_installation_token() -> None:
    encoded_jwt = get_app_bearer_token()
    access_tokens_url = "https://api.github.com/app/installations/34179484/access_tokens"  # FIXME constant
    response = requests.post(
        access_tokens_url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {encoded_jwt}",
        },
    )
    payload = json.loads(response.text)
    installation_token = payload["token"]
    return installation_token

    response = requests.get(
        "https://api.github.com/installation/repositories",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {installation_token}",
        },
    )
    repos = json.loads(response.text)
    assert repos

    integration = github.GithubIntegration(
        GITHUB_APP_ID, get_app_private_key(), base_url="https://github.com/api/v3"
    )

    install = integration.get_installation("noqdev", "iambic-templates-itest")  # FIXME
    access = integration.get_access_token(install.id)
    return access.token


def post_pr_comment() -> None:
    # github_client = github.Github(
    #     app_auth=github.AppAuthentication(          # not supported until version 2.0 https://github.com/PyGithub/PyGithub/commits/5e27c10a3140c3b9bbf71a0b71c96e71e1e3496c/github/AppAuthentication.py
    #         app_id=GITHUB_APP_ID,
    #         private_key=get_app_private_key(),
    #         installation_id=INSTANCE_OF_APP_INSTALLATION,
    #         ),
    # )
    # repo_name is already in the format {repo_owner}/{repo_short_name}
    github_client = github.Github(login_or_token=get_installation_token())
    repo_name = "noqdev/iambic-templates-itest"  # FIXME constants
    pull_number = 248  # FIXME constants
    # repository_url_token
    templates_repo = github_client.get_repo(repo_name)
    pull_request = templates_repo.get_pull(pull_number)
    pull_request_branch_name = pull_request.head.ref
    log_params = {"pull_request_branch_name": pull_request_branch_name}
    log.info("PR remote branch name", **log_params)
    body = "posting as github app"
    pull_request.create_issue_comment(body)


def generate_jwt_for_server_to_server_communication() -> str:
    # FIXME PEM PATH
    pem = "/Users/stevenmoy/Downloads/steven-test-github-app.2023-02-13.private-key.pem"
    # FIXME app_id
    app_id = "293178"

    # Open PEM
    with open(pem, "rb") as pem_file:
        signing_key = pem_file.read()

    payload = {
        # Issued at time
        "iat": int(time.time()),
        # JWT expiration time (10 minutes maximum)
        "exp": int(time.time()) + 600,
        # GitHub App's identifier
        "iss": app_id,
    }

    # Create JWT
    encoded_jwt = jwt.encode(payload, signing_key, algorithm="RS256")

    print(f"JWT:  ", encoded_jwt)

    github_app = github_client.get_app()
    response = requests.get(
        "https://api.github.com/app/installations",
        headers={
            "Accept": "application/vnd.github.v3.text-match+json",
            "Authorization": f"Bearer {encoded_jwt}",
        },
    )
    installations = json.loads(response.text)
    response


def get_app_private_key_as_lambda_context():
    # assuming we are already in an lambda execution context
    secret_name = "dev/test-github-app-private-key" # FIXME
    region_name = "us-west-2" # FIXME

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    # Decrypts secret using the associated KMS key.
    return get_secret_value_response['SecretString']


def get_installation_token(app_id, installation_id):
    encoded_jwt = get_app_bearer_token(get_app_private_key_as_lambda_context(), app_id)
    access_tokens_url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"  # FIXME constant
    response = requests.post(
        access_tokens_url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {encoded_jwt}",
        },
    )
    payload = json.loads(response.text)
    installation_token = payload["token"]
    return installation_token

def run_handler(event=None, context=None):
    """
    Default handler for AWS Lambda. It is split out from the actual
    handler so we can also run via IDE run configurations
    """

    # debug
    print(event)

    github_event = event["headers"]["x-github-event"]
    app_id = event["headers"]["x-github-hook-installation-target-id"]
    # FIXME implement webhooks security secrets
    webhook_payload = json.loads(event["body"])
    installation_id = webhook_payload["installation"]["id"]
    github_override_token = get_installation_token(app_id, installation_id)


    github_client = github.Github(github_override_token)


    if github_event == "pull_request":
        handle_pull_request(github_override_token, github_client, webhook_payload)
        return

    # repo_name is already in the format {repo_owner}/{repo_short_name}
    repo_name = webhook_payload["repository"]["full_name"]
    comment_body = webhook_payload["comment"]["body"]
    comment_user_login = webhook_payload["comment"]["user"]["login"]
    pull_number = webhook_payload["issue"]["number"]
    # repository_url_token
    templates_repo = github_client.get_repo(repo_name)
    pull_request = templates_repo.get_pull(pull_number)

    # FIXME: Need to find a mechanism to avoid infinite loop
    # the following is a very crude one
    if comment_user_login.endswith("[bot]"):
        # return early
        return

    if comment_body.startswith("iambic "):
        pull_request.create_issue_comment("lambda iambic git-plan")

    print(f"{github_event}|{comment_body}|{comment_user_login}")


EVENT_DISPATCH_MAP: dict[str, Callable] = {
    # "issue_comment": handle_issue_comment,
    # "pull_request": handle_pull_request,
    # "iambic_command": handle_iambic_command,
}


def handle_pull_request(github_token: str, github_client: github.Github, webhook_payload: dict[str, Any]) -> None:
    # replace with a different github client because we need a different
    # identity to leave the "iambic git-plan". Otherwise, it won't be able
    # to trigger the correct react-to-comment workflow.
    # repo_name is already in the format {repo_owner}/{repo_short_name}
    repo_name = webhook_payload["repository"]["full_name"]
    pull_number = webhook_payload["pull_request"]["number"]
    # repository_url_token
    templates_repo = github_client.get_repo(repo_name)
    pull_request = templates_repo.get_pull(pull_number)
    repository_url = webhook_payload["repository"]["clone_url"]
    repo_url = format_github_url(repository_url, github_token)
    pull_request_branch_name = pull_request.head.ref

    return handle_iambic_git_plan(
        None,
        pull_request,
        repo_name,
        pull_number,
        pull_request_branch_name,
        repo_url,
        proposed_changes_path="/tmp/proposed_changes.yaml",
    )



if __name__ == "__main__":
    post_pr_comment()
