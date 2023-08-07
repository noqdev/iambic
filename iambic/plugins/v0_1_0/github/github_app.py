#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import tempfile
import time
from functools import cache
from typing import Any, Callable
from urllib.parse import urlparse

import aiohttp
import boto3
import github
import jwt
import yaml
from botocore.exceptions import ClientError

import iambic.core.utils
import iambic.plugins.v0_1_0.github.github

# from iambic.core.git import get_remote_default_branch
from iambic.core.logger import log
from iambic.plugins.v0_1_0.github.github import (
    HandleIssueCommentReturnCode,
    _handle_detect_changes_from_eventbridge,
    _handle_enforce,
    _handle_expire,
    _handle_import,
    github_app_workflow_wrapper,
    handle_iambic_approve,
    handle_iambic_git_apply,
    handle_iambic_git_plan,
    handle_iambic_version,
    iambic_app,
)

# FIXME Lambda execution time is at most 15 minutes, and the Github installation token is at most
# 10 min validation period.

# FIXME struct logs is not showing up on lambda cloudwatch logs

# FIXME exception during git-plan is unknown
# /tmp/.iambic/repos/ already exists. This is unexpected.
# This is due to lambda reusing the already running container


# We typically ignore bot interactions; however, there are scenarios
# in which we want other installed GitHub App to interact with the
# integrations, we allow list such situations explicitly.
ALLOWED_BOT_INTERACTIONS = ["iambic approve", "iambic apply"]


def format_github_url(repository_url: str, github_token: str) -> str:
    parse_result = urlparse(repository_url)
    return parse_result._replace(
        netloc="x-access-token:{0}@{1}".format(github_token, parse_result.netloc)
    ).geturl()


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


@cache
def _get_app_secrets_as_lambda_context_current() -> dict:
    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager")

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId="iambic/github-app-secrets"
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    # Decrypts secret using the associated KMS key.
    return yaml.safe_load(get_secret_value_response["SecretString"])


@cache
def _get_app_private_key_as_lambda_context_old():
    # assuming we are already in an lambda execution context
    secret_name = os.environ["GITHUB_APP_SECRET_KEY_SECRET_ID"]
    region_name = os.environ["AWS_REGION"]

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)

    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    # Decrypts secret using the associated KMS key.
    return get_secret_value_response["SecretString"]


def get_app_private_key_as_lambda_context():
    try:
        secrets = _get_app_secrets_as_lambda_context_current()
        return secrets["pem"]
    except ClientError:
        # try to fall back to use the old secrets
        pass
    return _get_app_private_key_as_lambda_context_old()


@cache
def _get_app_webhook_secret_as_lambda_context_old():
    # assuming we are already in an lambda execution context
    secret_name = os.environ["GITHUB_APP_WEBHOOK_SECRET_SECRET_ID"]
    region_name = os.environ["AWS_REGION"]

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)

    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    # Decrypts secret using the associated KMS key.
    return get_secret_value_response["SecretString"]


def get_app_webhook_secret_as_lambda_context():
    try:
        secrets = _get_app_secrets_as_lambda_context_current()
        return secrets["webhook_secret"]
    except ClientError:
        # try to fall back to use the old secrets
        pass
    return _get_app_webhook_secret_as_lambda_context_old()


async def _get_installation_token(app_id, installation_id):
    encoded_jwt = get_app_bearer_token(get_app_private_key_as_lambda_context(), app_id)
    access_tokens_url = (
        f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {encoded_jwt}",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(access_tokens_url, headers=headers) as resp:
            payload = json.loads(await resp.text())
            installation_token = payload["token"]
            return installation_token


def lower_case_all_header_keys(d):
    return {key.lower(): value for key, value in d.items()}


def run_handler(event=None, context=None):
    """
    Default handler for AWS Lambda. It is split out from the actual
    handler so we can also run via IDE run configurations
    """

    # debug
    print(event)

    # Http spec considers keys to be insensitive but different
    # proxy will pass along different case sensitive header key
    # for example: API Gateway lambda integration pass header case transparent from request
    # whereas lambda functional url proactive lower case the incoming header keys
    # this is the reason we proactively lower_case the header keys
    github_event_headers = lower_case_all_header_keys(event["headers"])

    github_event = github_event_headers["x-github-event"]
    app_id = github_event_headers["x-github-hook-installation-target-id"]
    request_signature = github_event_headers["x-hub-signature-256"].split("=")[
        1
    ]  # the format is in sha256=<sig>

    payload = {}
    # the payload is switch between lambda event's body vs rawBody
    # due to difference of how various proxy temper with the http post body
    # For API Gateway, it's lambda integration always decode the payload and pass to lambda
    # however, to verify message signature, we must use non-tempered body.
    if "rawBody" in event:
        payload = event["rawBody"]
    else:
        payload = event["body"]

    # verify webhooks security secrets
    verify_signature(request_signature, payload)

    webhook_payload = json.loads(payload)
    installation_id = webhook_payload["installation"]["id"]
    github_override_token = asyncio.run(
        _get_installation_token(app_id, installation_id)
    )

    github_client = github.Github(github_override_token)

    # Handle lambda environment can only write to /tmp and make sure we don't leave previous
    # state on a new function execution
    temp_templates_directory = tempfile.mkdtemp(prefix="lambda")
    os.chdir(
        temp_templates_directory
    )  # the rest of the system seems to use filesystem for stuff
    getattr(iambic_app, "lambda").app.init_plan_output_path()
    getattr(iambic_app, "lambda").app.init_repo_base_path()
    iambic.plugins.v0_1_0.github.github.init_shared_data_directory()
    iambic.core.utils.init_writable_directory()

    f: Callable[[str, github.Github, dict[str, Any]]] = EVENT_DISPATCH_MAP.get(
        github_event
    )
    if f:
        f(github_override_token, github_client, webhook_payload)
    else:
        # warning. what it means is we are getting events send to the lambda
        # that we don't know how to handle.
        log.warning(f"no supported handler for {github_client}")


def handle_pull_request(
    github_token: str, github_client: github.Github, webhook_payload: dict[str, Any]
) -> None:
    action = webhook_payload["action"]
    if action not in ["opened", "synchronize"]:
        return

    repo_name = webhook_payload["repository"]["full_name"]
    pull_number = webhook_payload["pull_request"]["number"]
    # repository_url_token
    templates_repo = github_client.get_repo(repo_name)
    pull_request = templates_repo.get_pull(pull_number)
    repository_url = webhook_payload["repository"]["clone_url"]
    repo_url = format_github_url(repository_url, github_token)
    pull_request_branch_name = pull_request.head.ref

    if action == "synchronize":
        commits: list[github.Commit.Commit] = list(pull_request.get_commits())
        last_commit_message = commits[-1].commit.message
        if (
            last_commit_message
            == iambic.plugins.v0_1_0.github.github.COMMIT_MESSAGE_FOR_GIT_APPLY_ABSOLUTE_TIME
        ):
            log.info(
                "github_app ignore synchronize event since its likely triggered by itself"
            )
            return
        else:
            log_params = {"last_commit_message": last_commit_message}
            log.info("last known commit message", **log_params)

    return handle_iambic_git_plan(
        None,
        github_client,
        templates_repo,
        pull_request,
        repo_name,
        pull_number,
        pull_request_branch_name,
        repo_url,
        proposed_changes_path=getattr(iambic_app, "lambda").app.PLAN_OUTPUT_PATH,
    )


def handle_issue_comment(
    github_token: str, github_client: github.Github, webhook_payload: dict[str, Any]
) -> HandleIssueCommentReturnCode:
    action = webhook_payload["action"]
    if action != "created":
        return

    comment_body = webhook_payload["comment"]["body"]
    comment_user_login = webhook_payload["comment"]["user"]["login"]
    log_params = {"COMMENT_DISPATCH_MAP_KEYS": COMMENT_DISPATCH_MAP.keys()}
    log.info("COMMENT_DISPATCH_MAP keys", **log_params)

    command_lookup = comment_body.split("\n")[0].strip()

    if command_lookup not in COMMENT_DISPATCH_MAP:
        log_params = {
            "command_lookup": command_lookup,
            "comment_body": comment_body,
        }
        log.error("handle_issue_comment: no op", **log_params)
        return HandleIssueCommentReturnCode.NO_MATCHING_BODY

    if comment_user_login.endswith("[bot]"):
        if command_lookup not in ALLOWED_BOT_INTERACTIONS:
            # return early unless it's the approve attempt
            # the approve handler require to walk the full config
            # to determine.
            return HandleIssueCommentReturnCode.UNDEFINED

    repo_name = webhook_payload["repository"]["full_name"]
    pull_number = webhook_payload["issue"]["number"]
    # repository_url_token
    templates_repo = github_client.get_repo(repo_name)
    pull_request = templates_repo.get_pull(pull_number)

    # repo_name is already in the format {repo_owner}/{repo_short_name}
    repository_url = webhook_payload["repository"]["clone_url"]
    repo_url = format_github_url(repository_url, github_token)
    # repository_url_token
    templates_repo = github_client.get_repo(repo_name)
    pull_request = templates_repo.get_pull(pull_number)
    pull_request_branch_name = pull_request.head.ref
    log_params = {"pull_request_branch_name": pull_request_branch_name}
    log.info("PR remote branch name", **log_params)

    comment_func: Callable = COMMENT_DISPATCH_MAP[command_lookup]
    return comment_func(
        None,
        github_client,
        templates_repo,
        pull_request,
        repo_name,
        pull_number,
        pull_request_branch_name,
        repo_url,
        proposed_changes_path=getattr(iambic_app, "lambda").app.PLAN_OUTPUT_PATH,
        comment_user_login=comment_user_login,
        comment=comment_body,
    )


def handle_workflow_run(
    github_token: str, github_client: github.Github, webhook_payload: dict[str, Any]
) -> None:
    action = webhook_payload["action"]
    if action != "requested":
        return

    workflow_path = webhook_payload["workflow_run"]["path"]

    if workflow_path not in WORKFLOW_DISPATCH_MAP:
        log_params = {"workflow_path": workflow_path}
        log.error("handle_workflow_run: no op", **log_params)
        return

    repository_url = webhook_payload["repository"]["clone_url"]
    repo_url = format_github_url(repository_url, github_token)

    repo_name = webhook_payload["repository"]["full_name"]
    templates_repo = github_client.get_repo(repo_name)
    default_branch = templates_repo.default_branch

    workflow_func: Callable = WORKFLOW_DISPATCH_MAP[workflow_path]
    return workflow_func(
        github_client,
        templates_repo,
        repo_name,
        repo_url,
        default_branch,
        proposed_changes_path=getattr(iambic_app, "lambda").app.PLAN_OUTPUT_PATH,
    )


EVENT_DISPATCH_MAP: dict[str, Callable] = {
    "issue_comment": handle_issue_comment,
    "pull_request": handle_pull_request,
    "workflow_run": handle_workflow_run,
}


# We are supporting both "iambic" and "/iambic"
# for now during transition.
COMMENT_DISPATCH_MAP: dict[str, Callable] = {
    "iambic git-apply": handle_iambic_git_apply,
    "/iambic git-apply": handle_iambic_git_apply,
    "iambic git-plan": handle_iambic_git_plan,
    "/iambic git-plan": handle_iambic_git_plan,
    "iambic apply": handle_iambic_git_apply,
    "/iambic apply": handle_iambic_git_apply,
    "iambic plan": handle_iambic_git_plan,
    "/iambic plan": handle_iambic_git_plan,
    "iambic approve": handle_iambic_approve,
    "/iambic approve": handle_iambic_approve,
    "iambic version": handle_iambic_version,
    "/iambic version": handle_iambic_version,
}

WORKFLOW_DISPATCH_MAP: dict[str, Callable] = {
    ".github/workflows/iambic-enforce.yml": github_app_workflow_wrapper(
        _handle_enforce, "enforce"
    ),
    ".github/workflows/iambic-expire.yml": github_app_workflow_wrapper(
        _handle_expire, "expire"
    ),
    ".github/workflows/iambic-import.yml": github_app_workflow_wrapper(
        _handle_import, "import"
    ),
    ".github/workflows/iambic-detect.yml": github_app_workflow_wrapper(
        _handle_detect_changes_from_eventbridge, "detect"
    ),
}


# Use to verify Github App Webhook Secret Using SHA256
def calculate_signature(webhook_secret: str, payload: str) -> str:
    secret_in_bytes = bytes(webhook_secret, "utf-8")
    digest = hmac.new(
        key=secret_in_bytes, msg=payload.encode("utf-8"), digestmod=hashlib.sha256
    )
    signature = digest.hexdigest()
    return signature


def verify_signature(sig: str, payload: str) -> None:
    good_sig = calculate_signature(get_app_webhook_secret_as_lambda_context(), payload)
    if not hmac.compare_digest(good_sig, sig):
        raise Exception("Bad signature")


if __name__ == "__main__":
    print("not supported")
