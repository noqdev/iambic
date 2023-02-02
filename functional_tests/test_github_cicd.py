from __future__ import annotations

import asyncio
import datetime
import os
import shutil
import subprocess
import tempfile
import time

import boto3.session
import pytest
from github import Github

from functional_tests.conftest import all_config
from iambic.aws.iam.role.models import RoleTemplate
from iambic.config.models import Config, ExtendsConfig
from iambic.core.git import clone_git_repo

os.environ["TESTING"] = "true"


github_config = ExtendsConfig(
    key="AWS_SECRETS_MANAGER",
    value="arn:aws:secretsmanager:us-west-2:442632209887:secret:dev/github-token-iambic-templates-itest",
    hub_role_arn="arn:aws:iam::442632209887:role/IambicSpokeRole",
)


GITHUB_CICID_TEMPLATE_TARGET_PATH = (
    "resources/aws/roles/iambic_test_spoke_account_1/iambic_itest_github_cicd.yaml"
)

iambic_role_yaml = """template_type: NOQ::AWS::IAM::Role
identifier: iambic_itest_for_github_cicd
included_accounts:
  - iambic_test_spoke_account_1
properties:
  assume_role_policy_document:
    statement:
      - action: sts:AssumeRole
        effect: Deny
        principal:
          service: ec2.amazonaws.com
    version: '2012-10-17'
  description: {new_description}
  role_name: iambic_itest_for_github_cicd
"""


@pytest.fixture
def filesystem():
    fd, temp_config_filename = tempfile.mkstemp(
        prefix="iambic_test_temp_config_filename"
    )
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )

    with open(fd, "w") as temp_file:
        temp_file.write(all_config)

    try:
        config: Config = Config.load(temp_config_filename)
        config.combine_extended_configs()
        asyncio.run(config.setup_aws_accounts())
        yield (temp_config_filename, temp_templates_directory, config)
    finally:
        try:
            os.close(fd)
            os.unlink(temp_config_filename)
            shutil.rmtree(temp_templates_directory)
        except Exception as e:
            print(e)


@pytest.fixture
def generate_templates_fixture():
    # to override the conftest version to speed up testing
    pass


@pytest.fixture(scope="session")
def build_push_container():
    if not os.environ.get("GITHUB_ACTIONS", None):
        # If we are running locally on developer machine, we need to ensure
        # the payload is packed into a container image for the test templates repo
        # to run against, so this is why we are building the container images on-the-fly
        subprocess.run("make -f Makefile.itest auth_to_ecr", shell=True, check=True)
        subprocess.run(
            "make -f Makefile.itest build_docker_itest", shell=True, check=True
        )
        subprocess.run(
            "make -f Makefile.itest upload_docker_itest", shell=True, check=True
        )


def get_github_token(config: Config) -> str:
    github_secret = asyncio.run(config.get_aws_secret(github_config))
    return github_secret["secrets"]["github-token-iambic-templates-itest"]


def get_aws_key_dict(config: Config) -> str:
    github_secret = asyncio.run(config.get_aws_secret(github_config))
    return github_secret["secrets"]["aws-iambic-github-cicid-itest"]


# Opens a PR on noqdev/iambic-templates-test. The workflow on the repo will
# pull container with "test label". It will then approve the PR and trigger
# the "iambic git-apply" command on the PR. If the flow is successful, the PR
# will be merged and we will check the workflow to be completed state.
def test_github_cicd(filesystem, generate_templates_fixture, build_push_container):

    temp_config_filename, temp_templates_directory, config = filesystem

    github_token = get_github_token(config)

    github_repo_name = "noqdev/iambic-templates-itest"
    repo_url = f"https://oauth2:{github_token}@github.com/{github_repo_name}.git"
    repo = clone_git_repo(repo_url, temp_templates_directory, None)
    head_sha = repo.head.commit.hexsha
    print(repo)

    repo_config_writer = repo.config_writer()
    repo_config_writer.set_value(
        "user", "name", "Iambic Github Functional Test for Github"
    )
    repo_config_writer.set_value(
        "user", "email", "github-cicd-functional-test@iambic.org"
    )
    repo_config_writer.release()

    utc_obj = datetime.datetime.utcnow()
    date_isoformat = utc_obj.isoformat()
    date_string = date_isoformat.replace(":", "_")
    new_branch = f"itest/github_cicd_run_{date_string}"
    current = repo.create_head(new_branch)
    current.checkout()
    with open(f"{temp_templates_directory}/last_touched.md", "wb") as f:
        f.write(date_string.encode("utf-8"))
    test_role_path = os.path.join(
        temp_templates_directory,
        GITHUB_CICID_TEMPLATE_TARGET_PATH,
    )

    with open(test_role_path, "w") as temp_role_file:
        utc_obj = datetime.datetime.utcnow()
        date_isoformat = utc_obj.isoformat()
        date_string = date_isoformat.replace(":", "_")
        temp_role_file.write(iambic_role_yaml.format(new_description=date_string))

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
    pr_number = pr.number

    # test react to pull_request
    is_workflow_run_successful = False
    datetime_since_comment_issued = datetime.datetime.utcnow()
    while (datetime.datetime.utcnow() - datetime_since_comment_issued).seconds < 120:
        runs = github_repo.get_workflow_runs(event="pull_request", branch=new_branch)
        runs = [run for run in runs if run.created_at >= utc_obj]
        runs = [run for run in runs if run.conclusion == "success"]
        if len(runs) != 1:
            time.sleep(10)
            print("sleeping")
            continue
        else:
            is_workflow_run_successful = True
            break

    assert is_workflow_run_successful

    # test git-plan
    is_workflow_run_successful = False
    datetime_since_comment_issued = datetime.datetime.utcnow()
    while (datetime.datetime.utcnow() - datetime_since_comment_issued).seconds < 120:
        runs = github_repo.get_workflow_runs(event="issue_comment", branch="main")
        runs = [run for run in runs if run.created_at >= utc_obj]
        runs = [run for run in runs if run.conclusion == "success"]
        if len(runs) != 1:
            time.sleep(10)
            print("sleeping")
            continue
        else:
            is_workflow_run_successful = True
            break

    assert is_workflow_run_successful

    # let github action to handle the approval flow
    pr.create_issue_comment("approve")
    is_workflow_run_successful = False
    datetime_since_comment_issued = datetime.datetime.utcnow()
    while (datetime.datetime.utcnow() - datetime_since_comment_issued).seconds < 120:
        review_list = github_repo.get_pull(pr_number).get_reviews()
        approved_review_list = [
            review for review in review_list if review.state == "APPROVED"
        ]
        if len(approved_review_list) != 1:
            time.sleep(10)
            print("sleeping")
            continue
        else:
            is_workflow_run_successful = True
            break

    # test iambic git-apply
    pr.create_issue_comment("iambic git-apply")
    is_workflow_run_successful = False
    datetime_since_comment_issued = datetime.datetime.utcnow()
    while (datetime.datetime.utcnow() - datetime_since_comment_issued).seconds < 120:
        runs = github_repo.get_workflow_runs(event="issue_comment", branch="main")
        runs = [run for run in runs if run.created_at >= utc_obj]
        runs = [run for run in runs if run.head_sha == head_sha]
        runs = [run for run in runs if run.conclusion == "success"]
        if len(runs) != 2:
            time.sleep(10)
            print("sleeping")
            continue
        else:
            is_workflow_run_successful = True
            break

    assert is_workflow_run_successful

    # ensure it is merged
    is_workflow_run_successful = False
    datetime_since_comment_issued = datetime.datetime.utcnow()
    while (datetime.datetime.utcnow() - datetime_since_comment_issued).seconds < 120:
        check_pull_request = github_repo.get_pull(pr_number)
        if not check_pull_request.merged:
            time.sleep(10)
            print("sleeping")
            continue
        else:
            is_workflow_run_successful = True
            break
    check_pull_request = github_repo.get_pull(pr_number)
    assert check_pull_request.merged


def test_github_import(filesystem, generate_templates_fixture, build_push_container):

    temp_config_filename, temp_templates_directory, config = filesystem

    github_token = get_github_token(config)
    github_repo_name = "noqdev/iambic-templates-itest"
    github_client = Github(github_token)
    github_repo = github_client.get_repo(github_repo_name)
    workflow = github_repo.get_workflow("iambic-import.yml")
    workflow.create_dispatch(github_repo.default_branch)

    # test full import
    utc_obj = datetime.datetime.utcnow()
    is_workflow_run_successful = False
    datetime_since_comment_issued = datetime.datetime.utcnow()
    while (datetime.datetime.utcnow() - datetime_since_comment_issued).seconds < 120:
        runs = github_repo.get_workflow_runs(event="workflow_dispatch", branch="main")
        runs = [run for run in runs if run.created_at >= utc_obj]
        runs = [run for run in runs if run.conclusion == "success"]
        if len(runs) != 1:
            time.sleep(10)
            print("sleeping")
            continue
        else:
            is_workflow_run_successful = True
            break

    assert is_workflow_run_successful


def test_github_detect(filesystem, generate_templates_fixture, build_push_container):

    temp_config_filename, temp_templates_directory, config = filesystem

    github_token = get_github_token(config)

    # emulate iam changes
    # the arn target is from https://github.com/noqdev/iambic-templates-itest/blob/main/resources/aws/roles/dev/iambic_itest_github_cicd.yaml
    region_name = "us-east-1"

    # this is the preferred way to make out-of-band changes using iam role but
    # iambic detect intentionally filters out iambic related actor. so i have
    # to resort to use a static access key that is scope to aws user only able
    # UpdateRoleDescription to a particular arn
    # session = asyncio.run(config.get_boto_session_from_arn("arn:aws:iam::442632209887:role/iambic_itest_for_github_cicd", region_name))
    # identity = session.client("sts").get_caller_identity()
    # identity_arn_with_session_name = (
    #     identity["Arn"].replace(":sts:", ":iam:").replace("assumed-role", "role")
    # )
    # iam_client = session.client("iam", region_name=region_name)

    aws_key_dict = get_aws_key_dict(config)
    session = boto3.session.Session(
        aws_access_key_id=aws_key_dict["access_key"],
        aws_secret_access_key=aws_key_dict["secret_key"],
        region_name=region_name,
    )
    iam_client = session.client("iam", region_name=region_name)

    utc_obj = datetime.datetime.utcnow()
    date_isoformat = utc_obj.isoformat()
    new_description = date_isoformat.replace(":", "_")
    response = iam_client.update_role_description(
        RoleName="iambic_itest_for_github_cicd", Description=new_description
    )
    assert response["Role"]["Description"] == new_description

    # hack sleep 10 seconds to hope eventbridge has picked up the event...
    # this test can still break if eventbridge is not setup correctly
    # or detect is not doing what we expect.
    time.sleep(10)

    github_repo_name = "noqdev/iambic-templates-itest"
    github_client = Github(github_token)
    github_repo = github_client.get_repo(github_repo_name)
    workflow = github_repo.get_workflow("iambic-detect.yml")
    workflow.create_dispatch(github_repo.default_branch)

    # test iambic detect
    utc_obj = datetime.datetime.utcnow()
    is_workflow_run_successful = False
    datetime_since_comment_issued = datetime.datetime.utcnow()
    while (datetime.datetime.utcnow() - datetime_since_comment_issued).seconds < 120:
        runs = github_repo.get_workflow_runs(event="workflow_dispatch", branch="main")
        runs = [run for run in runs if run.created_at >= utc_obj]
        runs = [run for run in runs if run.conclusion == "success"]
        if len(runs) != 1:
            time.sleep(10)
            print("sleeping")
            continue
        else:
            is_workflow_run_successful = True
            break

    assert is_workflow_run_successful

    github_repo_name = "noqdev/iambic-templates-itest"
    repo_url = f"https://oauth2:{github_token}@github.com/{github_repo_name}.git"
    repo = clone_git_repo(repo_url, temp_templates_directory, None)

    new_branch = f"itest/github_cicd_run_{new_description}"
    current = repo.create_head(new_branch)
    current.checkout()

    test_role_path = os.path.join(
        temp_templates_directory,
        GITHUB_CICID_TEMPLATE_TARGET_PATH,
    )

    role_template = RoleTemplate.load(file_path=test_role_path)

    # this is prone to race condition since we are using the same resource for test
    assert role_template.properties.description == new_description
