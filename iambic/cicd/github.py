from __future__ import annotations

import json
import os
import sys

from github import Github

lambda_app = __import__("iambic.lambda.app", globals(), locals(), [], 0)

MERGEABLE_STATE_CLEAN = "clean"
MERGEABLE_STATE_BLOCKED = "blocked"


def run_handler(context=None):
    github_token = os.environ.get("GITHUB_TOKEN", None)
    print("event_name: {0}".format(context["event_name"]))
    github_client = Github(github_token)
    # TODO Support Github Enterprise with custom hostname
    # g = Github(base_url="https://{hostname}/api/v3", login_or_token="access_token")
    handle_issue_comment(github_client, context)


def handle_issue_comment(github_client, context):
    # Get PR
    repo_name = context.get("repository", None)
    pull_number = context.get("event", {}).get("issue", {}).get("number")
    # repo_name is already in the format {repo_owner}/{repo_short_name}
    templates_repo = github_client.get_repo(repo_name)
    pull_request = templates_repo.get_pull(pull_number)
    if pull_request.mergeable_state != MERGEABLE_STATE_CLEAN:
        # TODO log error and also make a comment to PR
        pull_request.create_issue_comment(
            "mergeable_state is {0}".format(pull_request.mergeable_state)
        )
        return
    try:
        lambda_app.run_handler(None, {"command": "git_apply"})
    except Exception as e:
        print(e)
        pull_request.create_issue_comment(
            "exception during git-apply is {0}".format(pull_request.mergable_state)
        )
        return
    pull_request.merge()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise Exception("You must pass a command")
    command = sys.argv[1]
    github_context_json_str = os.environ.get("GITHUB_CONTEXT")
    with open("/root/github_context/github_context.json", "r") as f:
        github_context = json.load(f)
    run_handler(context=github_context)
