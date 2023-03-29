from __future__ import annotations

import asyncio
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
import time
import traceback
import uuid
from enum import Enum
from typing import Any, Callable
from urllib.parse import urlparse

import github
from github.PullRequest import PullRequest

import iambic.output.markdown
from iambic.config.dynamic_config import load_config
from iambic.config.utils import resolve_config_template_path
from iambic.core.context import ctx
from iambic.core.git import Repo, clone_git_repo, get_remote_default_branch
from iambic.core.iambic_enum import Command
from iambic.core.logger import log
from iambic.core.models import ExecutionMessage, TemplateChangeDetails
from iambic.core.utils import yaml
from iambic.main import run_apply, run_detect, run_expire, run_git_apply, run_git_plan

iambic_app = __import__("iambic.lambda.app", globals(), locals(), [], 0)
lambda_run_handler = getattr(iambic_app, "lambda").app.run_handler


MERGEABLE_STATE_CLEAN = "clean"
MERGEABLE_STATE_BLOCKED = "blocked"


COMMIT_MESSAGE_USER_NAME = "Iambic Automation"
COMMIT_MESSAGE_USER_EMAIL = "iambic-automation@iambic.org"
COMMIT_MESSAGE_FOR_DETECT = "Import changes from detect operation"
COMMIT_MESSAGE_FOR_IMPORT = "Import changes from import operation"
COMMIT_MESSAGE_FOR_EXPIRE = "Periodic Expiration"
COMMIT_MESSAGE_FOR_GIT_APPLY_ABSOLUTE_TIME = "Replace relative time with absolute time"
SHARED_CONTAINER_GITHUB_DIRECTORY = "/root/data"


def init_shared_data_directory():
    # Have to be careful when setting REPO_BASE_PATH because lambda execution
    # environment can be very straight on only /tmp is writable
    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME", False):
        temp_templates_directory = tempfile.mkdtemp(prefix="github")
        SHARED_CONTAINER_GITHUB_DIRECTORY = f"{temp_templates_directory}/data/"
    else:
        SHARED_CONTAINER_GITHUB_DIRECTORY = "/root/data"
    this_module = sys.modules[__name__]
    setattr(
        this_module,
        "SHARED_CONTAINER_GITHUB_DIRECTORY",
        SHARED_CONTAINER_GITHUB_DIRECTORY,
    )


def get_lambda_repo_path() -> str:
    return getattr(iambic_app, "lambda").app.REPO_BASE_PATH


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
    github_client = github.Github(github_token)

    getattr(iambic_app, "lambda").app.init_plan_output_path()
    getattr(iambic_app, "lambda").app.init_repo_base_path()

    # TODO Support Github Enterprise with custom hostname
    # g = Github(base_url="https://{hostname}/api/v3", login_or_token="access_token")

    f: Callable[[github.Github, dict[str, Any]], None] = EVENT_DISPATCH_MAP.get(
        event_name
    )
    if f:
        f(github_client, context)
    else:
        log.error("no supported handler")
        raise Exception("no supported handler")


def handle_iambic_command(
    github_client: github.Github, context: dict[str, Any]
) -> None:
    github_token: str = context["iambic"]["GH_OVERRIDE_TOKEN"]
    command: str = context["iambic"]["IAMBIC_CLOUD_IMPORT_CMD"]
    github_client = github.Github(github_token)
    f: Callable[
        [github.Github, dict[str, Any]], None
    ] = IAMBIC_CLOUD_IMPORT_DISPATCH_MAP.get(command)
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

    repo_config_writer = cloned_repo.config_writer()
    repo_config_writer.set_value("user", "name", COMMIT_MESSAGE_USER_NAME)
    repo_config_writer.set_value("user", "email", COMMIT_MESSAGE_USER_EMAIL)
    repo_config_writer.release()

    default_branch = get_remote_default_branch(cloned_repo)
    cloned_repo.git.checkout("-b", f"attempt/{purpose}", default_branch)

    return cloned_repo


def is_last_commit_relative_to_absolute_change(
    repo_url: str, pull_request_branch_name: str
) -> Repo:
    repo_path = tempfile.mkdtemp(prefix="github")

    if len(os.listdir(repo_path)) > 0:
        raise Exception(f"{repo_path} already exists. This is unexpected.")
    cloned_repo = clone_git_repo(repo_url, repo_path, pull_request_branch_name)
    return cloned_repo.head.commit.message == COMMIT_MESSAGE_FOR_GIT_APPLY_ABSOLUTE_TIME


def prepare_local_repo(
    repo_url: str, repo_path: str, pull_request_branch_name: str
) -> Repo:
    if len(os.listdir(repo_path)) > 0:
        raise Exception(f"{repo_path} already exists. This is unexpected.")
    cloned_repo = clone_git_repo(repo_url, repo_path, None)
    for remote in cloned_repo.remotes:
        remote.fetch()
    default_branch = get_remote_default_branch(cloned_repo)
    cloned_repo.git.checkout("-b", "attempt/git-apply", default_branch)

    # Note, this is for local usage, we don't actually
    # forward this commit upstream
    repo_config_writer = cloned_repo.config_writer()
    repo_config_writer.set_value("user", "name", COMMIT_MESSAGE_USER_NAME)
    repo_config_writer.set_value("user", "email", COMMIT_MESSAGE_USER_EMAIL)
    repo_config_writer.release()

    cloned_repo.git.merge(f"origin/{pull_request_branch_name}")
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


def ensure_body_length_fits_github_spec(body: str, blob_html_url: str = None) -> str:
    if len(body) > BODY_MAX_LENGTH:
        body = TRUNCATED_WARNING + f"""<a href="{blob_html_url}">Run</a>"""
    return body


def post_result_as_pr_comment(
    pull_request: PullRequest,
    context: dict[str, Any],
    iambic_op: str,
    proposed_changes_path: str,
) -> None:
    if context:
        run_url = (
            context["server_url"]
            + "/"
            + context["repository"]
            + "/actions/runs/"
            + context["run_id"]
            + "/attempts/"
            + context["run_attempt"]
        )
    else:
        run_url = "lambda implementation not currently supported run_url"  # FIXME
    lines = []
    if not proposed_changes_path:
        cwd = os.getcwd()
        proposed_changes_path = f"{cwd}/proposed_changes.yaml"
    if os.path.exists(proposed_changes_path):
        with open(proposed_changes_path) as f:
            lines = f.readlines()
    plan = "".join(lines) if lines else "no changes"
    body = GIT_APPLY_COMMENT_TEMPLATE.format(
        plan=plan, run_url=run_url, iambic_op=iambic_op
    )
    _post_render_content_as_pr_comment(body)


def _post_render_content_as_pr_comment(
    pull_request: PullRequest,
    rendered_content: str,
    blob_html_url: str = None,
) -> None:
    body = ensure_body_length_fits_github_spec(
        rendered_content, blob_html_url=blob_html_url
    )
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
    github_client: github.Github, context: dict[str, Any]
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
        github_client,
        templates_repo,
        pull_request,
        repo_name,
        pull_number,
        pull_request_branch_name,
        repo_url,
    )


def handle_iambic_git_apply(
    context: dict[str, Any],
    github_client: github.Github,
    templates_repo: github.Repo,
    pull_request: PullRequest,
    repo_name: str,
    pull_number: str,
    pull_request_branch_name: str,
    repo_url: str,
    proposed_changes_path: str = None,
):
    if pull_request.mergeable_state != MERGEABLE_STATE_CLEAN:
        # TODO log error and also make a comment to PR
        pull_request.create_issue_comment(
            "Mergable state is {0}. This probably means that the necessary approvals have not been granted for the request.".format(
                pull_request.mergeable_state
            )
        )
        return HandleIssueCommentReturnCode.MERGEABLE_STATE_NOT_CLEAN

    session_name = get_session_name(repo_name, pull_number)
    os.environ["IAMBIC_SESSION_NAME"] = session_name

    try:
        # merge_sha is used when we trigger a merge
        merge_sha = pull_request.head.sha

        repo_dir = get_lambda_repo_path()
        repo = prepare_local_repo(repo_url, repo_dir, pull_request_branch_name)
        # local_sha_before_git_apply may not match the initial merge
        # sha because we apply the PR to local checkout tracking branch
        local_sha_before_git_apply = repo.head.commit.hexsha

        if proposed_changes_path:
            # code smell to have to change a module variable
            # to control the destination of proposed_changes.yaml
            # It's questionable if we still need to depend on the lambda interface
            # because lambda interface was created to dynamic populate template config
            # but templates config is now already stored in the templates repo itself.
            getattr(iambic_app, "lambda").app.PLAN_OUTPUT_PATH = proposed_changes_path

        template_changes = run_git_apply(
            False, None, None, repo_dir, proposed_changes_path
        )

        # In the event git_apply changes relative time to absolute time
        repo.git.add(".")
        diff_list = repo.head.commit.diff()
        if len(diff_list) > 0:
            repo.git.commit("-m", COMMIT_MESSAGE_FOR_GIT_APPLY_ABSOLUTE_TIME)
        else:
            log.debug("git_apply did not introduce additional changes")

        local_sha_after_git_apply = repo.head.commit.hexsha
        if local_sha_before_git_apply != local_sha_after_git_apply:
            # signal changes due to git-apply
            repo.remotes.origin.push(
                refspec=f"HEAD:{pull_request_branch_name}"
            ).raise_if_error()
            log_params = {"sha": local_sha_after_git_apply}
            log.info("git-apply new sha is", **log_params)
            # update merge sha because we add new commits to pull request
            merge_sha = local_sha_after_git_apply

        _process_template_changes(
            github_client,
            templates_repo,
            pull_request,
            pull_number,
            proposed_changes_path,
            template_changes,
            "apply",
        )
        copy_data_to_data_directory()

        maybe_merge(templates_repo, pull_number, merge_sha)
        return HandleIssueCommentReturnCode.MERGED

    except Exception as e:
        captured_traceback = traceback.format_exc()
        log.error("fault", exception=captured_traceback)
        pull_request.create_issue_comment(
            "exception during apply is {0} \n ```{1}```".format(
                pull_request.mergeable_state, captured_traceback
            )
        )
        raise e


def maybe_merge(
    templates_repo: github.Repo,
    # pull_request: PullRequest,
    pull_number: int,
    merge_sha: str,
    max_attempts: int = 5,
    sleep_interval: float = 5,
):
    """Attempts to merge the PR at specific sha, this function will retry a few times because
    desired sha maybe not available yet"""
    attempts = 0
    merge_status = None
    last_known_traceback = None
    while attempts < max_attempts:
        pull_request = templates_repo.get_pull(pull_number)
        try:
            merge_status = pull_request.merge(sha=merge_sha)
            break
        except github.GithubException:
            last_known_traceback = traceback.format_exc()
            attempts += 1
            time.sleep(sleep_interval)
    if merge_status is None:
        raise RuntimeError(
            f"Fail to merge PR. Target sha is {merge_sha}. last_known_trace_back is {last_known_traceback}"
        )


def _post_artifact_to_companion_repository(
    github_client: github.Github,
    templates_repo: github.Repo,
    pull_number: str,
    op_name: str,
    proposed_changes_path: str,
    markdown_summary: str,
    default_base_name: str = "proposed_changes.yaml",
):
    url = None
    try:
        lines = []
        if os.path.exists(proposed_changes_path):
            with open(proposed_changes_path) as f:
                lines = f.readlines()
            gist_repo_name = f"{templates_repo.full_name}-gist"
            gist_repo = github_client.get_repo(gist_repo_name)
            now_timestamp = datetime.datetime.now()
            pr_prefix = f"pr-{pull_number}" if pull_number else "no-pr"
            yaml_repo_path = (
                f"{pr_prefix}/{op_name}/{now_timestamp}/{default_base_name}"
            )
            md_repo_path = f"{pr_prefix}/{op_name}/{now_timestamp}/summary.md"
            gist_repo.create_file(yaml_repo_path, op_name, "".join(lines))
            result = gist_repo.create_file(md_repo_path, op_name, markdown_summary)
            url = result["content"].html_url
    except Exception:
        # Decision to keep going is we do not want a failure of posting to companion
        # repository (for full machine and human readable contents) to stop the rest of
        # plan and apply operations. Companion repository is a separate failure domain.
        captured_traceback = traceback.format_exc()
        log.error("fault", exception=captured_traceback)
    return url


def handle_iambic_git_plan(
    context: dict[str, Any],
    github_client: github.Github,
    templates_repo: github.Repo,
    pull_request: PullRequest,
    repo_name: str,
    pull_number: str,
    pull_request_branch_name: str,
    repo_url: str,
    proposed_changes_path: str = None,
):
    session_name = get_session_name(repo_name, pull_number)
    os.environ["IAMBIC_SESSION_NAME"] = session_name

    try:
        repo_dir = get_lambda_repo_path()
        prepare_local_repo(repo_url, repo_dir, pull_request_branch_name)

        if proposed_changes_path:
            # code smell to have to change a module variable
            # to control the destination of proposed_changes.yaml
            # It's questionable if we still need to depend on the lambda interface
            # because lambda interface was created to dynamic populate template config
            # but templates config is now already stored in the templates repo itself.
            getattr(iambic_app, "lambda").app.PLAN_OUTPUT_PATH = proposed_changes_path

        template_changes = run_git_plan(proposed_changes_path, repo_dir)
        _process_template_changes(
            github_client,
            templates_repo,
            pull_request,
            pull_number,
            proposed_changes_path,
            template_changes,
            "plan",
        )
        copy_data_to_data_directory()
        return HandleIssueCommentReturnCode.PLANNED
    except Exception as e:
        captured_traceback = traceback.format_exc()
        log.error("fault", exception=captured_traceback)
        pull_request.create_issue_comment(
            "exception during plan is {0} \n ```{1}```".format(
                pull_request.mergeable_state, captured_traceback
            )
        )
        raise e


def github_app_workflow_wrapper(workflow_func: Callable, ux_op_name: str) -> Callable:
    def wrapped_workflow_func(
        github_client: github.Github,
        templates_repo: github.Repo,
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

            template_changes = workflow_func(repo_url, default_branch)
            _process_template_changes(
                github_client,
                templates_repo,
                None,
                pull_number,
                proposed_changes_path,
                template_changes,
                f"{ux_op_name}",  # TODO this can probably be improved for user-experience
            )
        except Exception as e:
            captured_traceback = traceback.format_exc()
            log.error("fault", exception=captured_traceback)
            try:
                temp_dir = tempfile.mkdtemp(suffix=None, prefix=None, dir=None)
                with open(f"{temp_dir}/crash.txt", "w") as f:
                    f.write(captured_traceback)
                _post_artifact_to_companion_repository(
                    github_client,
                    templates_repo,
                    pull_number,
                    f"{ux_op_name}",
                    f"{temp_dir}/crash.txt",
                    captured_traceback,
                    default_base_name="crash.txt",
                )
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


def _process_template_changes(
    github_client: github.Github,
    templates_repo: github.Repo,
    pull_request: PullRequest,
    pull_number: str,
    proposed_changes_path: str,  # Path where we are sourcing the machine output
    template_changes: list[TemplateChangeDetails],
    op_name: str,  # Examples are "plan", "apply"
):
    html_url = ""
    if template_changes and len(template_changes) > 0:
        rendered_content = iambic.output.markdown.gh_render_resource_changes(
            template_changes
        )
        html_url = _post_artifact_to_companion_repository(
            github_client,
            templates_repo,
            pull_number,
            op_name,
            proposed_changes_path,
            rendered_content,
        )
    else:
        rendered_content = "no changes detected"

    rendered_content = f"""Reacting to `{op_name}`\n\n{rendered_content}\n\n <a href="{html_url}">Run</a>"""
    if pull_request:
        _post_render_content_as_pr_comment(
            pull_request, rendered_content, blob_html_url=html_url
        )


def handle_pull_request(github_client: github.Github, context: dict[str, Any]) -> None:
    # replace with a different github client because we need a different
    # identity to leave the "iambic git-plan". Otherwise, it won't be able
    # to trigger the correct react-to-comment workflow.
    github_client = github.Github(context["iambic"]["GH_OVERRIDE_TOKEN"])
    # repo_name is already in the format {repo_owner}/{repo_short_name}
    repo_name = context["repository"]
    pull_number = context["event"]["pull_request"]["number"]
    # repository_url_token
    templates_repo = github_client.get_repo(repo_name)
    pull_request = templates_repo.get_pull(pull_number)

    try:
        pull_request.create_issue_comment("iambic git-plan")
    except Exception as e:
        captured_traceback = traceback.format_exc()
        log.error("fault", exception=captured_traceback)
        pull_request.create_issue_comment(
            "exception during pull-request is {0} \n ```{1}```".format(
                pull_request.mergeable_state, captured_traceback
            )
        )
        raise e


def handle_detect_changes_from_eventbridge(
    github_client: github.Github, context: dict[str, Any]
) -> None:
    # we need a different github token because we will need to push to main without PR
    github_token = context["iambic"]["GH_OVERRIDE_TOKEN"]
    repository_url = context["event"]["repository"]["clone_url"]
    repo_url = format_github_url(repository_url, github_token)

    repo_name = context["repository"]
    templates_repo = github_client.get_repo(repo_name)
    default_branch = get_remote_default_branch(templates_repo)
    _handle_detect_changes_from_eventbridge(repo_url, default_branch)


def _handle_detect_changes_from_eventbridge(
    repo_url: str, default_branch: str
) -> list[TemplateChangeDetails]:
    try:
        repo = prepare_local_repo_for_new_commits(
            repo_url, get_lambda_repo_path(), "detect"
        )

        run_detect(get_lambda_repo_path())
        repo.git.add(".")
        diff_list = repo.head.commit.diff()
        if len(diff_list) > 0:
            repo.git.commit("-m", COMMIT_MESSAGE_FOR_DETECT)
            repo.remotes.origin.push(refspec=f"HEAD:{default_branch}").raise_if_error()
        else:
            log.info("handle_detect no changes")
    except Exception as e:
        log.error("fault", exception=str(e))
        raise e
    return []


def handle_import(github_client: github.Github, context: dict[str, Any]) -> None:
    # we need a different github token because we will need to push to main without PR
    github_token = context["iambic"]["GH_OVERRIDE_TOKEN"]

    # repo_name is already in the format {repo_owner}/{repo_short_name}
    repository_url = context["event"]["repository"]["clone_url"]
    repo_url = format_github_url(repository_url, github_token)
    repo_name = context["repository"]
    templates_repo = github_client.get_repo(repo_name)
    default_branch = get_remote_default_branch(templates_repo)
    _handle_import(repo_url, default_branch)


def _handle_import(repo_url: str, default_branch: str) -> list[TemplateChangeDetails]:
    try:
        exe_message = ExecutionMessage(
            execution_id=str(uuid.uuid4()), command=Command.IMPORT
        )
        repo_dir = get_lambda_repo_path()
        repo = prepare_local_repo_for_new_commits(repo_url, repo_dir, "import")
        config_path = asyncio.run(resolve_config_template_path(repo_dir))
        config = asyncio.run(load_config(config_path))
        asyncio.run(config.run_import(exe_message, repo_dir))
        repo.git.add(".")
        diff_list = repo.head.commit.diff()
        if len(diff_list) > 0:
            repo.git.commit("-m", COMMIT_MESSAGE_FOR_IMPORT)
            repo.remotes.origin.push(refspec=f"HEAD:{default_branch}").raise_if_error()
        else:
            log.info("_handle_import no changes")
    except Exception as e:
        log.error("fault", exception=str(e))
        raise e
    return []


def _handle_enforce(repo_url: str, default_branch: str) -> list[TemplateChangeDetails]:
    try:
        local_repo_path = get_lambda_repo_path()
        _ = prepare_local_repo_for_new_commits(repo_url, local_repo_path, "enforce")
        config_path = asyncio.run(resolve_config_template_path(local_repo_path))
        config = asyncio.run(load_config(config_path))
        # we are not restoring teh original ctx because we expect
        # this is called in a completely separate process
        ctx.eval_only = False
        # running in enforce option mean we are only writing to the cloud.
        # there will be no templates being changed in the git context
        template_changes = run_apply(
            config,
            [],
            repo_dir=local_repo_path,
            enforced_only=True,
            output_path=getattr(iambic_app, "lambda").app.PLAN_OUTPUT_PATH,
        )
        return template_changes
    except Exception as e:
        log.error("fault", exception=str(e))
        raise e


def handle_expire(github_client: github.Github, context: dict[str, Any]) -> None:
    # we need a different github token because we will need to push to main without PR
    github_token = context["iambic"]["GH_OVERRIDE_TOKEN"]

    # repo_name is already in the format {repo_owner}/{repo_short_name}
    repository_url = context["event"]["repository"]["clone_url"]
    repo_url = format_github_url(repository_url, github_token)
    repo_name = context["repository"]
    templates_repo = github_client.get_repo(repo_name)
    default_branch = get_remote_default_branch(templates_repo)
    _handle_expire(repo_url, default_branch)


def _handle_expire(repo_url: str, default_branch: str) -> list[TemplateChangeDetails]:
    try:
        repo = prepare_local_repo_for_new_commits(
            repo_url, get_lambda_repo_path(), "expire"
        )

        run_expire(None, get_lambda_repo_path())
        repo.git.add(".")
        diff_list = repo.head.commit.diff()
        if len(diff_list) > 0:
            repo.git.commit("-m", "expire")  # FIXME

            lambda_run_handler(None, {"command": "git_apply"})

            # if it's in a PR, it's more natural to upload the proposed_changes.yaml to somewhere
            # current implementation, it's just logging to standard out
            lines = []
            filepath = getattr(iambic_app, "lambda").app.PLAN_OUTPUT_PATH
            if os.path.exists(filepath):
                with open(filepath) as f:
                    lines = f.readlines()
            log_params = {"proposed_changes": lines}
            log.info("handle_expire ran", **log_params)

            default_branch = get_remote_default_branch(repo)
            repo.remotes.origin.push(
                refspec=f"HEAD:{default_branch}"
            ).raise_if_error()  # FIXME
        else:
            log.info("handle_expire no changes")
    except Exception as e:
        log.error("fault", exception=str(e))
        raise e
    return []


EVENT_DISPATCH_MAP: dict[str, Callable] = {
    "issue_comment": handle_issue_comment,
    "pull_request": handle_pull_request,
    "iambic_command": handle_iambic_command,
}


IAMBIC_CLOUD_IMPORT_DISPATCH_MAP: dict[str, Callable] = {
    "detect": handle_detect_changes_from_eventbridge,
    "import": handle_import,
    "expire": handle_expire,
}


COMMENT_DISPATCH_MAP: dict[str, Callable] = {
    "iambic git-apply": handle_iambic_git_apply,
    "iambic git-plan": handle_iambic_git_plan,
    "iambic apply": handle_iambic_git_apply,
    "iambic plan": handle_iambic_git_plan,
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
