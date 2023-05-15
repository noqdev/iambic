from __future__ import annotations

import json
import os
import shutil
import tempfile
from test.plugins.v0_1_0.aws.iam.group.test_utils import (  # noqa: F401 # intentional for mocks
    EXAMPLE_GROUPNAME,
    mock_iam_client,
)

import boto3
import pytest
from moto import mock_sts

import iambic
from iambic.core.iambic_enum import Command
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import get_existing_template_map
from iambic.plugins.v0_1_0.aws.iam.group.template_generation import (
    collect_aws_groups,
    generate_account_group_resource_files,
    generate_aws_group_templates,
    generate_group_resource_file_for_all_accounts,
    get_response_dir,
)
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.models import AWSAccount

TEST_TEMPLATE_DIR = "resources/aws/iam/group"
TEST_TEMPLATE_PATH = "resources/aws/iam/group/example_groupname.yaml"


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
        dir == f"{templates_base_dir}/.iambic/fake_execution_id/123456789012/iam/group"
    )


@pytest.mark.asyncio
async def test_generate_account_group_resource_files(
    mock_sts_client,
    mock_iam_client,  # noqa: F811 # intentional for mocks
    mock_fs,
    mock_execution_message,
    mock_aws_account,
):
    _, templates_base_dir = mock_fs
    files = await generate_account_group_resource_files(
        mock_execution_message, mock_aws_account
    )
    assert len(files["groups"]) == 1
    assert files["groups"][0]["name"] == EXAMPLE_GROUPNAME


@pytest.mark.asyncio
async def test_generate_group_resource_file_for_all_accounts(
    mock_sts_client,
    mock_iam_client,  # noqa: F811 # intentional for mocks
    mock_fs,
    mock_execution_message,
    mock_aws_account,
):
    _, templates_base_dir = mock_fs
    files = await generate_group_resource_file_for_all_accounts(
        mock_execution_message, [mock_aws_account], EXAMPLE_GROUPNAME
    )
    assert len(files) == 1
    assert files[0]["name"] == EXAMPLE_GROUPNAME


@pytest.mark.asyncio
async def test_collect_aws_groups(
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
        nested=True,
    )

    await collect_aws_groups(mock_execution_message, config, iam_template_map)
    output_path = (
        f"{templates_base_dir}/.iambic/fake_execution_id/iam/group/output.json"
    )
    with open(output_path, "r") as f:
        output_users = json.load(f)
        assert len(output_users) == 1


@pytest.mark.asyncio
async def test_generate_aws_group_templates(
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
        nested=True,
    )

    # have to call collect_aws_groups to prep the cloud response
    await collect_aws_groups(mock_execution_message, config, iam_template_map)
    # actually call the function being tested
    await generate_aws_group_templates(
        mock_execution_message, config, templates_base_dir, iam_template_map
    )
    output_path = f"{templates_base_dir}/resources/aws/iam/group/example_account/example_groupname.yaml"
    assert os.path.exists(output_path)
