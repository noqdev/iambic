from __future__ import annotations

import json
import os
import sys
from enum import Enum
from urllib.parse import urlparse

import yaml
from github import Github

from iambic.core.git import clone_git_repo

iambic_app = __import__("iambic.lambda.app", globals(), locals(), [], 0)
lambda_run_handler = getattr(iambic_app, "lambda").app.run_handler
lambda_repo_path = getattr(iambic_app, "lambda").app.REPO_BASE_PATH


MERGEABLE_STATE_CLEAN = "clean"
MERGEABLE_STATE_BLOCKED = "blocked"


class HandleIssueCommentReturnCode(Enum):
    UNDEFINED = 1
    NO_MATCHING_BODY = 2
    MERGEABLE_STATE_NOT_CLEAN = 3
    MERGED = 4


def run_handler(context=None):
    github_token = context["token"]
    print("event_name: {0}".format(context["event_name"]))
    github_client = Github(github_token)
    # TODO Support Github Enterprise with custom hostname
    # g = Github(base_url="https://{hostname}/api/v3", login_or_token="access_token")
    handle_issue_comment(github_client, context)


def format_github_url(repository_url, github_token):
    parse_result = urlparse(repository_url)
    return parse_result._replace(
        netloc="oauth2:{0}@{1}".format(github_token, parse_result.netloc)
    ).geturl()


def prepare_local_repo(repo_url, repo_path, pull_request_branch_name):
    cloned_repo = clone_git_repo(repo_url, repo_path, None)
    for remote in cloned_repo.remotes:
        remote.fetch()
    cloned_repo.git.checkout("-b", "attempt/git-apply")
    cloned_repo.git.merge(f"origin/{pull_request_branch_name}")
    print("last commit message: {0}".format(cloned_repo.head.commit.message))
    return cloned_repo


def load_proposed_changes(filepath):
    if not os.path.exists(filepath):
        return {}
    with open(filepath, "r") as f:
        return yaml.load(f)


def format_proposed_changes(changes):
    pass


GIT_APPLY_COMMENT_TEMPLATE = """iambic git-applied ran with:

```yaml
{plan}
```
"""


def post_result_as_pr_comment(pull_request, repo_file_path):
    lines = []
    cwd = os.getcwd()
    filepath = f"{cwd}/proposed_changes.yaml"
    if os.path.exists(filepath):
        with open(filepath) as f:
            lines = f.readlines()
    plan = "".join(lines) if lines else "no changes"
    body = GIT_APPLY_COMMENT_TEMPLATE.format(plan=plan)
    if len(body) > 65000:
        body = body[0:65000]
    pull_request.create_issue_comment(body)


def handle_issue_comment(github_client, context) -> HandleIssueCommentReturnCode:

    comment_body = context.get("event", {}).get("comment", {}).get("body")
    if comment_body != "iambic git-apply":
        print("no op")
        return HandleIssueCommentReturnCode.NO_MATCHING_BODY

    github_token = context.get("token", None)
    # repo_name is already in the format {repo_owner}/{repo_short_name}
    repo_name = context.get("repository", None)
    pull_number = context.get("event", {}).get("issue", {}).get("number")
    repository_url = context.get("event", {}).get("repository", {}).get("clone_url")
    repo_url = format_github_url(repository_url, github_token)
    # repository_url_token
    templates_repo = github_client.get_repo(repo_name)
    pull_request = templates_repo.get_pull(pull_number)
    pull_request_branch_name = pull_request.head.ref
    print("pull_request branch name is {0}".format(pull_request_branch_name))

    if pull_request.mergeable_state != MERGEABLE_STATE_CLEAN:
        # TODO log error and also make a comment to PR
        pull_request.create_issue_comment(
            "mergeable_state is {0}".format(pull_request.mergeable_state)
        )
        return HandleIssueCommentReturnCode.MERGEABLE_STATE_NOT_CLEAN
    try:
        prepare_local_repo(repo_url, lambda_repo_path, pull_request_branch_name)
        lambda_run_handler(None, {"command": "git_apply"})
        post_result_as_pr_comment(pull_request, lambda_repo_path)
        pull_request.merge()
        return HandleIssueCommentReturnCode.MERGED
    except Exception as e:
        print(e)
        pull_request.create_issue_comment(
            "exception during git-apply is {0} \n {1}".format(
                pull_request.mergeable_state, e
            )
        )
        return HandleIssueCommentReturnCode.UNDEFINED


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise Exception("You must pass a command")
    command = sys.argv[1]
    github_context_json_str = os.environ.get("GITHUB_CONTEXT")
    with open("/root/github_context/github_context.json", "r") as f:
        github_context = json.load(f)
    run_handler(context=github_context)
