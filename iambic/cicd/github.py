from __future__ import annotations

import json
import os
import re
import shutil
from enum import Enum
from typing import Any, Callable
from urllib.parse import urlparse

import yaml
from github import Github
from github.PullRequest import PullRequest

from iambic.core.git import Repo, clone_git_repo
from iambic.core.logger import log
from iambic.main import run_detect, run_import

iambic_app = __import__("iambic.lambda.app", globals(), locals(), [], 0)
lambda_run_handler = getattr(iambic_app, "lambda").app.run_handler
lambda_repo_path = getattr(iambic_app, "lambda").app.REPO_BASE_PATH


MERGEABLE_STATE_CLEAN = "clean"
MERGEABLE_STATE_BLOCKED = "blocked"


SHARED_CONTAINER_GITHUB_DIRECTORY = "/root/data"


class HandleIssueCommentReturnCode(Enum):
    UNDEFINED = 1
    NO_MATCHING_BODY = 2
    MERGEABLE_STATE_NOT_CLEAN = 3
    MERGED = 4
    PLANNED = 5


# context is a dictionary structure published by Github Action
# https://docs.github.com/en/actions/learn-github-actions/contexts#github-context
def run_handler(context: dict[str, Any]):
    github_token: str = context["token"]
    event_name: str = context["event_name"]
    log_params = {"event_name": event_name}
    log.info("run_handler", **log_params)
    github_client = Github(github_token)
    # TODO Support Github Enterprise with custom hostname
    # g = Github(base_url="https://{hostname}/api/v3", login_or_token="access_token")

    f: Callable[[Github, dict[str, Any]]] = EVENT_DISPATCH_MAP.get(event_name)
    if f:
        f(github_client, context)
    else:
        log.error("no supported handler")
        raise Exception("no supported handler")


def handle_iambic_command(github_client: Github, context: dict[str, Any]) -> None:
    github_token: str = context["iambic"]["GH_OVERRIDE_TOKEN"]
    command: str = context["iambic"]["IAMBIC_CLOUD_IMPORT_CMD"]
    github_client = Github(github_token)
    f: Callable[[Github, dict[str, Any]]] = IAMBIC_CLOUD_IMPORT_DISPATCH_MAP.get(
        command
    )
    if f:
        f(github_client, context)
    else:
        log.error("no supported handler")
        raise Exception("no supported handler")


def format_github_url(repository_url: str, github_token: str) -> str:
    parse_result = urlparse(repository_url)
    return parse_result._replace(
        netloc="oauth2:{0}@{1}".format(github_token, parse_result.netloc)
    ).geturl()


def prepare_local_repo_for_new_commits(
    repo_url: str, repo_path: str, purpose: str
) -> Repo:
    if len(os.listdir(repo_path)) > 0:
        raise Exception(f"{repo_path} already exists. This is unexpected.")
    cloned_repo = clone_git_repo(repo_url, repo_path, None)
    cloned_repo.git.checkout("-b", f"attempt/{purpose}")

    return cloned_repo


def prepare_local_repo(
    repo_url: str, repo_path: str, pull_request_branch_name: str
) -> Repo:
    if len(os.listdir(repo_path)) > 0:
        raise Exception(f"{repo_path} already exists. This is unexpected.")
    cloned_repo = clone_git_repo(repo_url, repo_path, None)
    for remote in cloned_repo.remotes:
        remote.fetch()
    cloned_repo.git.checkout("-b", "attempt/git-apply")

    # Note, this is for local usage, we don't actually
    # forward this commit upstream
    repo_config_writer = cloned_repo.config_writer()
    repo_config_writer.set_value("user", "name", "Iambic Merger")
    repo_config_writer.set_value("user", "email", "iambic-merger@iambic.org")
    repo_config_writer.release()

    cloned_repo.git.merge(f"origin/{pull_request_branch_name}")
    log_params = {"last_commit_message": cloned_repo.head.commit.message}
    log.info(cloned_repo.head.commit.message, **log_params)
    return cloned_repo


def prepare_local_repo_from_remote_branch(
    repo_url: str, repo_path: str, pull_request_branch_name: str
) -> Repo:
    if len(os.listdir(repo_path)) > 0:
        raise Exception(f"{repo_path} already exists. This is unexpected.")
    cloned_repo = clone_git_repo(repo_url, repo_path, pull_request_branch_name)
    log_params = {"last_commit_message": cloned_repo.head.commit.message}
    log.info(cloned_repo.head.commit.message, **log_params)
    return cloned_repo


def load_proposed_changes(filepath: str) -> dict:
    if not os.path.exists(filepath):
        return {}
    with open(filepath, "r") as f:
        return yaml.load(f)


# TODO do more formatting to emphasize resources deletion
def format_proposed_changes(changes: dict) -> str:
    pass


TRUNCATED_WARNING = (
    "Plan is too large and truncated. View Run link to check the entire plan."
)
BODY_MAX_LENGTH = 65000
TRUNCATED_BODY_MAX_LENGTH = BODY_MAX_LENGTH - len(TRUNCATED_WARNING)
GIT_APPLY_COMMENT_TEMPLATE = """iambic {iambic_op} ran with:

```yaml
{plan}
```

<a href="{run_url}">Run</a>
"""


def ensure_body_length_fits_github_spec(body: str) -> str:
    if len(body) > BODY_MAX_LENGTH:
        body = TRUNCATED_WARNING + body[-TRUNCATED_BODY_MAX_LENGTH:-1]
    return body


def post_result_as_pr_comment(
    pull_request: PullRequest, context: dict[str, Any], iambic_op: str
) -> None:
    run_url = (
        context["server_url"]
        + "/"
        + context["repository"]
        + "/actions/runs/"
        + context["run_id"]
        + "/attempts/"
        + context["run_attempt"]
    )
    lines = []
    cwd = os.getcwd()
    filepath = f"{cwd}/proposed_changes.yaml"
    if os.path.exists(filepath):
        with open(filepath) as f:
            lines = f.readlines()
    plan = "".join(lines) if lines else "no changes"
    body = GIT_APPLY_COMMENT_TEMPLATE.format(
        plan=plan, run_url=run_url, iambic_op=iambic_op
    )
    body = ensure_body_length_fits_github_spec(body)
    pull_request.create_issue_comment(body)


def copy_data_to_data_directory() -> None:
    cwd = os.getcwd()
    filepath = f"{cwd}/proposed_changes.yaml"
    dest_dir = SHARED_CONTAINER_GITHUB_DIRECTORY
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
    if os.path.exists(filepath):
        shutil.copy(filepath, f"{dest_dir}/proposed_changes.yaml")


IAMBIC_SESSION_NAME_TEMPLATE = "org={org},repo={repo},pr={number}"
SESSION_NAME_REGEX = re.compile("[\\w=,.@-]+")


def get_session_name(repo_name: str, pull_request_number: str) -> str:
    org = ""
    repo = ""
    repo_parts = repo_name.split("/")
    if len(repo_parts) == 2:
        repo = repo_parts[1]
        org = repo_parts[0]
    else:
        repo = repo_name
    pending_session_name = IAMBIC_SESSION_NAME_TEMPLATE.format(
        org=org, repo=repo, number=pull_request_number
    )
    session_name = "".join(
        [c for c in pending_session_name if SESSION_NAME_REGEX.match(c)]
    )
    if session_name != pending_session_name:
        log_params = {
            "pending_session_name": pending_session_name,
            "session_name": session_name,
        }
        log.error("lossy-session-name", **log_params)
    return session_name


def handle_issue_comment(
    github_client: Github, context: dict[str, Any]
) -> HandleIssueCommentReturnCode:

    comment_body = context["event"]["comment"]["body"]
    log_params = {"COMMENT_DISPATCH_MAP_KEYS": COMMENT_DISPATCH_MAP.keys()}
    log.info("COMMENT_DISPATCH_MAP keys", **log_params)
    if comment_body not in COMMENT_DISPATCH_MAP:
        log_params = {"comment_body": comment_body}
        log.error("handle_issue_comment: no op", **log_params)
        return HandleIssueCommentReturnCode.NO_MATCHING_BODY

    github_token = context["token"]
    # repo_name is already in the format {repo_owner}/{repo_short_name}
    repo_name = context["repository"]
    pull_number = context["event"]["issue"]["number"]
    repository_url = context["event"]["repository"]["clone_url"]
    repo_url = format_github_url(repository_url, github_token)
    # repository_url_token
    templates_repo = github_client.get_repo(repo_name)
    pull_request = templates_repo.get_pull(pull_number)
    pull_request_branch_name = pull_request.head.ref
    log_params = {"pull_request_branch_name": pull_request_branch_name}
    log.info("PR remote branch name", **log_params)

    comment_func: Callable = COMMENT_DISPATCH_MAP[comment_body]
    return comment_func(
        context,
        pull_request,
        repo_name,
        pull_number,
        pull_request_branch_name,
        repo_url,
    )


def handle_iambic_git_apply(
    context: dict[str, Any],
    pull_request: PullRequest,
    repo_name: str,
    pull_number: str,
    pull_request_branch_name: str,
    repo_url: str,
):
    if pull_request.mergeable_state != MERGEABLE_STATE_CLEAN:
        # TODO log error and also make a comment to PR
        pull_request.create_issue_comment(
            "mergeable_state is {0}".format(pull_request.mergeable_state)
        )
        return HandleIssueCommentReturnCode.MERGEABLE_STATE_NOT_CLEAN

    session_name = get_session_name(repo_name, pull_number)
    os.environ["IAMBIC_SESSION_NAME"] = session_name

    try:
        prepare_local_repo(repo_url, lambda_repo_path, pull_request_branch_name)
        lambda_run_handler(None, {"command": "git_apply"})
        post_result_as_pr_comment(pull_request, context, "git-apply")
        copy_data_to_data_directory()
        pull_request.merge()
        return HandleIssueCommentReturnCode.MERGED
    except Exception as e:
        log.error("fault", exception=str(e))
        pull_request.create_issue_comment(
            "exception during git-apply is {0} \n {1}".format(
                pull_request.mergeable_state, e
            )
        )
        raise e


def handle_iambic_git_plan(
    context: dict[str, Any],
    pull_request: PullRequest,
    repo_name: str,
    pull_number: str,
    pull_request_branch_name: str,
    repo_url: str,
):
    session_name = get_session_name(repo_name, pull_number)
    os.environ["IAMBIC_SESSION_NAME"] = session_name

    try:
        prepare_local_repo(repo_url, lambda_repo_path, pull_request_branch_name)
        lambda_run_handler(None, {"command": "git_plan"})
        post_result_as_pr_comment(pull_request, context, "git-plan")
        copy_data_to_data_directory()
        return HandleIssueCommentReturnCode.PLANNED
    except Exception as e:
        log.error("fault", exception=str(e))
        pull_request.create_issue_comment(
            "exception during git-plan is {0} \n {1}".format(
                pull_request.mergeable_state, e
            )
        )
        raise e


def handle_pull_request(github_client: Github, context: dict[str, Any]) -> None:
    # replace with a different github client because we need a different
    # identity to leave the "iambic git-plan". Otherwise, it won't be able
    # to trigger the correct react-to-comment workflow.
    github_client = Github(context["iambic"]["GH_OVERRIDE_TOKEN"])
    # repo_name is already in the format {repo_owner}/{repo_short_name}
    repo_name = context["repository"]
    pull_number = context["event"]["pull_request"]["number"]
    # repository_url_token
    templates_repo = github_client.get_repo(repo_name)
    pull_request = templates_repo.get_pull(pull_number)

    try:
        pull_request.create_issue_comment("iambic git-plan")
    except Exception as e:
        log.error("fault", exception=str(e))
        pull_request.create_issue_comment(
            "exception during pull-request is {0} \n {1}".format(
                pull_request.mergeable_state, e
            )
        )
        raise e


def handle_detect_changes_from_eventbridge(
    github_client: Github, context: dict[str, Any]
) -> None:

    # we need a different github token because we will need to push to main without PR
    github_token = context["iambic"]["GH_OVERRIDE_TOKEN"]

    # repo_name is already in the format {repo_owner}/{repo_short_name}
    repository_url = context["event"]["repository"]["clone_url"]
    repo_url = format_github_url(repository_url, github_token)
    # repository_url_token
    # log_params = {"pull_request_branch_name": pull_request_branch_name}
    # log.info("PR remote branch name", **log_params)

    try:
        repo = prepare_local_repo_for_new_commits(repo_url, lambda_repo_path, "detect")

        repo_config_writer = repo.config_writer()
        repo_config_writer.set_value(
            "user", "name", context["iambic"]["IAMBIC_COMMIT_USERNAME"]
        )
        repo_config_writer.set_value(
            "user", "email", context["iambic"]["IAMBIC_COMMIT_EMAIL"]
        )
        repo_config_writer.release()

        # TODO customize config.yaml filename
        run_detect(lambda_repo_path)
        repo.git.add(".")
        diff_list = repo.head.commit.diff()
        if len(diff_list) > 0:
            repo.git.commit("-m", github_context["iambic"]["IAMBIC_COMMIT_MESSAGE"])
            repo.remotes.origin.push(refspec="HEAD:main")
        else:
            log.info("handle_import no changes")
    except Exception as e:
        log.error("fault", exception=str(e))
        raise e


def handle_import(github_client: Github, context: dict[str, Any]) -> None:

    # we need a different github token because we will need to push to main without PR
    github_token = context["iambic"]["GH_OVERRIDE_TOKEN"]

    # repo_name is already in the format {repo_owner}/{repo_short_name}
    repository_url = context["event"]["repository"]["clone_url"]
    repo_url = format_github_url(repository_url, github_token)
    # repository_url_token
    # log_params = {"pull_request_branch_name": pull_request_branch_name}
    # log.info("PR remote branch name", **log_params)

    try:
        repo = prepare_local_repo_for_new_commits(repo_url, lambda_repo_path, "import")

        repo_config_writer = repo.config_writer()
        repo_config_writer.set_value(
            "user", "name", context["iambic"]["IAMBIC_COMMIT_USERNAME"]
        )
        repo_config_writer.set_value(
            "user", "email", context["iambic"]["IAMBIC_COMMIT_EMAIL"]
        )
        repo_config_writer.release()

        # TODO customize config.yaml filename
        config_file = context["iambic"]["IAMBIC_CONFIG_FILE"]
        config_path = f"{lambda_repo_path}/config/{config_file}"
        run_import([config_path], lambda_repo_path)
        repo.git.add(".")
        diff_list = repo.head.commit.diff()
        if len(diff_list) > 0:
            repo.git.commit("-m", github_context["iambic"]["IAMBIC_COMMIT_MESSAGE"])
            repo.remotes.origin.push(refspec="HEAD:main")
        else:
            log.info("handle_import no changes")
    except Exception as e:
        log.error("fault", exception=str(e))
        raise e


EVENT_DISPATCH_MAP: dict[str, Callable] = {
    "issue_comment": handle_issue_comment,
    "pull_request": handle_pull_request,
    "iambic_command": handle_iambic_command,
}


IAMBIC_CLOUD_IMPORT_DISPATCH_MAP: dict[str, Callable] = {
    "detect": handle_detect_changes_from_eventbridge,
    "import": handle_import,
}


COMMENT_DISPATCH_MAP: dict[str, Callable] = {
    "iambic git-apply": handle_iambic_git_apply,
    "iambic git-plan": handle_iambic_git_plan,
}

if __name__ == "__main__":
    github_context_json_str = os.environ.get("GITHUB_CONTEXT")
    github_override_token = os.environ.get("GH_OVERRIDE_TOKEN")
    iambic_integration_str = os.environ.get("IAMBIC_CLOUD_IMPORT_CMD")
    iambic_commit_email = os.environ.get("IAMBIC_COMMIT_EMAIL")
    iambic_commit_username = os.environ.get("IAMBIC_COMMIT_USERNAME")
    iambic_commit_message = os.environ.get("IAMBIC_COMMIT_MESSAGE")
    iambic_config_file = os.environ.get("IAMBIC_CONFIG_FILE")

    with open("/root/github_context/github_context.json", "r") as f:
        github_context = json.load(f)
        github_context["iambic"] = {}
        github_context["iambic"]["GH_OVERRIDE_TOKEN"] = github_override_token
        github_context["iambic"]["IAMBIC_CLOUD_IMPORT_CMD"] = iambic_integration_str
        github_context["iambic"]["IAMBIC_COMMIT_EMAIL"] = iambic_commit_email
        github_context["iambic"]["IAMBIC_COMMIT_USERNAME"] = iambic_commit_username
        github_context["iambic"]["IAMBIC_COMMIT_MESSAGE"] = iambic_commit_message
        github_context["iambic"]["IAMBIC_CONFIG_FILE"] = iambic_config_file

    if iambic_integration_str:
        github_context["event_name"] = "iambic_command"

    run_handler(github_context)
