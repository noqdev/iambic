from __future__ import annotations

import os
import shutil
import tempfile
import traceback
from functools import cache
from typing import Callable

import boto3
import yaml
from botocore.exceptions import ClientError

import iambic.core.utils
import iambic.plugins.v0_1_0.github.github
from iambic.core.logger import log
from iambic.plugins.v0_1_0.generic_git_provider.generic_git_client import (
    create_git_client,
)
from iambic.plugins.v0_1_0.github.github import (
    _handle_import,
    get_session_name,
    iambic_app,
)

GENERIC_GIT_PROVIDER_SECRET_ARN = os.environ.get("GENERIC_GIT_PROVIDER_SECRET_ARN")


def run_handler(event=None, context=None):
    """
    Default handler for AWS Lambda. It is split out from the actual
    handler so we can also run via IDE run configurations
    """

    # debug
    print("Event: ", event)

    # Check if the event source is CloudWatch Events
    if isinstance(event, dict) and event.get("source") == "EventBridgeCron":
        return handle_events_cron(event, context)


@cache
def _get_app_secrets_as_lambda_context_current() -> dict:
    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager")

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=GENERIC_GIT_PROVIDER_SECRET_ARN,
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    # Decrypts secret using the associated KMS key.
    return yaml.safe_load(get_secret_value_response["SecretString"])


def handle_events_cron(event=None, context=None) -> None:
    secrets = _get_app_secrets_as_lambda_context_current()
    git_client = create_git_client(secrets)

    command = event["command"]

    if not (callable := AWS_EVENTS_WORKFLOW_DISPATCH_MAP.get(command)):
        log_params = {"command": command}
        log.error("handle_events_cron: Unable to find command", **log_params)
        return

    repo_url = git_client.repo_url

    # TODO, don't have a generic GitProviderRepo interface yet
    # templates_repo = git_client.get_repo(REPOSITORY_FULL_NAME)
    # TODO, don't have a generic GitProviderRepoFullName interface yet
    default_branch = git_client.default_branch_name
    repo_full_name = git_client.repo_full_name
    temp_templates_directory = tempfile.mkdtemp(prefix="lambda")
    os.chdir(temp_templates_directory)
    getattr(iambic_app, "lambda").app.init_plan_output_path()
    getattr(iambic_app, "lambda").app.init_repo_base_path()
    iambic.plugins.v0_1_0.github.github.init_shared_data_directory()
    iambic.core.utils.init_writable_directory()

    return callable(
        git_client,
        None,  # TODO, don't have a generic GitProviderRepo interface yet
        repo_full_name,
        repo_url,
        default_branch,
        proposed_changes_path=getattr(iambic_app, "lambda").app.PLAN_OUTPUT_PATH,
    )


def workflow_wrapper(workflow_func: Callable, ux_op_name: str) -> Callable:
    def wrapped_workflow_func(
        github_client,
        templates_repo,
        repo_name: str,
        repo_url: str,
        default_branch: str,
        proposed_changes_path: str = None,
    ):
        pull_number = (
            0  # 0 is not a valid pull number in github. workflow implementation
        )
        # does not have an associated PR. This is the path of least resistance adaption
        # for stable session name
        session_name = get_session_name(repo_name, pull_number)
        os.environ["IAMBIC_SESSION_NAME"] = session_name

        try:
            if proposed_changes_path:
                # code smell to have to change a module variable
                # to control the destination of proposed_changes.yaml
                # It's questionable if we still need to depend on the lambda interface
                # because lambda interface was created to dynamic populate template config
                # but templates config is now already stored in the templates repo itself.
                getattr(
                    iambic_app, "lambda"
                ).app.PLAN_OUTPUT_PATH = proposed_changes_path

            template_changes = workflow_func(
                repo_url,
                default_branch,
                github_client=github_client,
                templates_repo=templates_repo,
            )

            if template_changes:
                # TODO This is here just so pre-commit won't yell at me
                assert True

            # TODO disable _post_artifact_to_companion_repository because i don't have an interface defined yet
            # _process_template_changes(
            #     github_client,
            #     templates_repo,
            #     None,
            #     pull_number,
            #     proposed_changes_path,
            #     template_changes,
            #     f"{ux_op_name}",  # TODO this can probably be improved for user-experience
            # )
        except Exception as e:
            captured_traceback = traceback.format_exc()
            log.error("fault", exception=captured_traceback)
            try:
                temp_dir = tempfile.mkdtemp(suffix=None, prefix=None, dir=None)
                with open(f"{temp_dir}/crash.txt", "w") as f:
                    f.write(captured_traceback)
                # TODO disable _post_artifact_to_companion_repository because i don't have an interface defined yet
                # _post_artifact_to_companion_repository(
                #     github_client,
                #     templates_repo,
                #     pull_number,
                #     f"{ux_op_name}",
                #     f"{temp_dir}/crash.txt",
                #     captured_traceback,
                #     default_base_name="crash.txt",
                # )
            except Exception:
                captured_traceback = traceback.format_exc()
                log.error(
                    "fail to post exception to companion repo",
                    exception=captured_traceback,
                )
            finally:
                if temp_dir:
                    shutil.rmtree(temp_dir)
            raise e

    return wrapped_workflow_func


AWS_EVENTS_WORKFLOW_DISPATCH_MAP: dict[str, Callable] = {
    # "enforce": workflow_wrapper(_handle_enforce, "enforce"),
    # "expire": workflow_wrapper(_handle_expire, "expire"),
    "import": workflow_wrapper(_handle_import, "import"),
    # "detect": workflow_wrapper(
    #     _handle_detect_changes_from_eventbridge, "detect"
    # ),
}
