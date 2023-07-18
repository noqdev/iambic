from __future__ import annotations

import json
import os
import shutil
import tempfile
from test.plugins.v0_1_0.aws.iam.policy.test_utils import (  # noqa: F401 # intentional for mocks
    EXAMPLE_MANAGED_POLICY_NAME,
    mock_iam_client,
)

import boto3
import pytest
from moto import mock_sts

import iambic
from iambic.core.iambic_enum import Command
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import get_existing_template_map
from iambic.plugins.v0_1_0.aws.event_bridge.models import ManagedPolicyMessageDetails
from iambic.plugins.v0_1_0.aws.iam.policy.template_generation import (
    collect_aws_managed_policies,
    generate_account_managed_policy_resource_files,
    generate_aws_managed_policy_templates,
    generate_managed_policy_resource_file_for_all_accounts,
    get_response_dir,
)
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.models import AWSAccount

TEST_TEMPLATE_DIR = "resources/aws/iam/policy"
TEST_TEMPLATE_PATH = "resources/aws/iam/policy/example_managed_policy_name.yaml"


@pytest.fixture
def mock_fs():
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )

    try:
        os.makedirs(f"{temp_templates_directory}/{TEST_TEMPLATE_DIR}")

        test_template_path = f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}"
        with open(test_template_path, "w") as f:
            f.write("")

        setattr(iambic.core.utils, "__WRITABLE_DIRECTORY__", temp_templates_directory)

        yield test_template_path, temp_templates_directory
    finally:
        try:
            shutil.rmtree(temp_templates_directory)
        except Exception as e:
            print(e)


@pytest.fixture
def mock_execution_message():
    message = ExecutionMessage(execution_id="fake_execution_id", command=Command.IMPORT)
    return message


@pytest.fixture
def mock_aws_account():
    account = AWSAccount(
        account_id="123456789012",
        account_name="example_account",
        hub_role_arn="arn:aws:iam::123456789012:role/example-hub-role",
        spoke_role_arn="arn:aws:iam::123456789012:role/example-spoke-role",
    )
    return account


@pytest.fixture
def mock_sts_client():
    with mock_sts():
        sts_client = boto3.client("sts")
        yield sts_client


def test_get_response_dir(mock_fs, mock_execution_message, mock_aws_account):
    _, templates_base_dir = mock_fs
    dir = get_response_dir(mock_execution_message, mock_aws_account)
    assert (
        dir
        == f"{templates_base_dir}/.iambic/fake_execution_id/123456789012/iam/managed_policy"
    )


@pytest.mark.asyncio
async def test_generate_account_managed_policy_resource_files(
    mock_sts_client,
    mock_iam_client,  # noqa: F811 # intentional for mocks
    mock_fs,
    mock_execution_message,
    mock_aws_account,
):
    _, templates_base_dir = mock_fs
    files = await generate_account_managed_policy_resource_files(
        mock_execution_message, mock_aws_account
    )
    assert len(files["managed_policies"]) == 1
    assert files["managed_policies"][0]["policy_name"] == EXAMPLE_MANAGED_POLICY_NAME


@pytest.mark.asyncio
async def test_generate_managed_policy_resource_file_for_all_accounts(
    mock_sts_client,
    mock_iam_client,  # noqa: F811 # intentional for mocks
    mock_fs,
    mock_execution_message,
    mock_aws_account,
):
    _, templates_base_dir = mock_fs
    policy_path = "/"
    files = await generate_managed_policy_resource_file_for_all_accounts(
        mock_execution_message,
        EXAMPLE_MANAGED_POLICY_NAME,
        {mock_aws_account.account_id: mock_aws_account},
        [
            ManagedPolicyMessageDetails(
                policy_path=policy_path,
                account_id=mock_aws_account.account_id,
                policy_name=EXAMPLE_MANAGED_POLICY_NAME,
                delete=False,
            )
        ],
        None,
    )
    assert len(files) == 1
    assert files[0]["policy_name"] == EXAMPLE_MANAGED_POLICY_NAME


@pytest.mark.asyncio
async def test_collect_aws_users(
    mock_sts_client,
    mock_iam_client,  # noqa: F811 # intentional for mocks
    mock_fs,
    mock_execution_message,
    mock_aws_account,
):
    _, templates_base_dir = mock_fs
    config = AWSConfig(accounts=[mock_aws_account])
    iam_template_map = await get_existing_template_map(
        repo_dir=templates_base_dir,
        template_type="AWS::IAM.*",
        template_map=config.template_map,
        nested=True,
    )

    await collect_aws_managed_policies(mock_execution_message, config, iam_template_map)
    output_path = (
        f"{templates_base_dir}/.iambic/fake_execution_id/iam/managed_policy/output.json"
    )
    with open(output_path, "r") as f:
        output_users = json.load(f)
        assert len(output_users) == 1


@pytest.mark.asyncio
async def test_generate_aws_role_templates(
    mock_sts_client,
    mock_iam_client,  # noqa: F811 # intentional for mocks
    mock_fs,
    mock_execution_message,
    mock_aws_account,
):
    _, templates_base_dir = mock_fs
    config = AWSConfig(accounts=[mock_aws_account])
    iam_template_map = await get_existing_template_map(
        repo_dir=templates_base_dir,
        template_type="AWS::IAM.*",
        template_map=config.template_map,
        nested=True,
    )

    # have to call collect_aws_managed_policies to prep the cloud response
    await collect_aws_managed_policies(mock_execution_message, config, iam_template_map)
    # actually call the function being tested
    await generate_aws_managed_policy_templates(
        mock_execution_message, config, templates_base_dir, iam_template_map
    )
    output_path = f"{templates_base_dir}/resources/aws/iam/managed_policy/example_account/example_managed_policy_name.yaml"
    assert os.path.exists(output_path)
