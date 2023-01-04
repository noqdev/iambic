from __future__ import annotations

import datetime
import os
import shutil
import tempfile
import time

from github import Github

from iambic.config.models import Config
from iambic.core.git import clone_git_repo

os.environ["AWS_PROFILE"] = "iambic_test_org_account/IambicHubRole"
os.environ["TESTING"] = "true"

github_config = """
extends:
  - key: AWS_SECRETS_MANAGER
    value: arn:aws:secretsmanager:us-west-2:442632209887:secret:dev/github-token-iambic-templates-itest
    assume_role_arn: arn:aws:iam::442632209887:role/IambicSpokeRole
"""


def test_github_cicd():

    fd, temp_config_filename = tempfile.mkstemp(
        prefix="iambic_test_temp_config_filename"
    )
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )

    with open(fd, "w") as temp_file:
        temp_file.write(github_config)

    config = Config.load(temp_config_filename)
    github_token = config.secrets["github-token-iambic-templates-itest"]
    github_repo_name = "noqdev/iambic-templates-itest"
    repo_url = f"https://oauth2:{github_token}@github.com/{github_repo_name}.git"
    repo = clone_git_repo(repo_url, temp_templates_directory, None)
    head_sha = repo.head.commit.hexsha
    print(repo)

    utc_obj = datetime.datetime.utcnow()
    date_isoformat = utc_obj.isoformat()
    date_string = date_isoformat.replace(":", "_")
    new_branch = f"itest/github_cicd_run_{date_string}"
    current = repo.create_head(new_branch)
    current.checkout()
    with open(f"{temp_templates_directory}/last_touched.md", "wb") as f:
        f.write(date_string.encode("utf-8"))
    if repo.index.diff(None) or repo.untracked_files:
        repo.git.add(A=True)
        repo.git.commit(m="msg")
        repo.git.push("--set-upstream", "origin", current)
        print("git push")

    github_client = Github(github_token)
    github_repo = github_client.get_repo(github_repo_name)
    pull_request_body = "itest"
    pr = github_repo.create_pull(
        title="itest", body=pull_request_body, head=new_branch, base="main"
    )
    pr.create_issue_comment("approve")
    pr.create_issue_comment("iambic git-apply")
    is_workflow_run_successful = False
    datetime_since_comment_issued = datetime.datetime.utcnow()
    while (datetime.datetime.utcnow() - datetime_since_comment_issued).seconds < 120:
        runs = github_repo.get_workflow_runs(event="issue_comment", branch="main")
        runs = [run for run in runs if run.created_at >= utc_obj]
        runs = [run for run in runs if run.head_sha == head_sha]
        if len(runs) != 2:
            time.sleep(10)
            print("sleeping")
            continue
        else:
            is_workflow_run_successful = True

        os.close(fd)
        os.unlink(temp_config_filename)
        shutil.rmtree(temp_templates_directory)
        break

    assert is_workflow_run_successful
