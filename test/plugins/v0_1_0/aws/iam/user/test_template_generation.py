import json
import os
import shutil
import tempfile
from test.plugins.v0_1_0.aws.iam.user.test_utils import (  # noqa: F401 # intentional for mocks
    EXAMPLE_TAG_KEY,
    EXAMPLE_TAG_VALUE,
    EXAMPLE_USERNAME,
    mock_iam_client,
)

import boto3
import pytest
from moto import mock_sts

import iambic
from iambic.core.iambic_enum import Command
from iambic.core.models import ExecutionMessage
from iambic.plugins.v0_1_0.aws.iam.user.template_generation import (
    collect_aws_users,
    generate_account_user_resource_files,
    generate_aws_user_templates,
    generate_user_resource_file_for_all_accounts,
    get_response_dir,
    set_user_resource_tags,
)
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.models import AWSAccount

TEST_TEMPLATE_DIR = "resources/aws/iam/user"
TEST_TEMPLATE_PATH = "resources/aws/iam/user/example_user.yaml"


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
        dir == f"{templates_base_dir}/.iambic/fake_execution_id/123456789012/iam/user"
    )


@pytest.mark.asyncio
async def test_generate_account_user_resource_files(
    mock_sts_client,
    mock_iam_client,  # noqa: F811 # intentional for mocks
    mock_fs,
    mock_execution_message,
    mock_aws_account,
):
    _, templates_base_dir = mock_fs
    files = await generate_account_user_resource_files(
        mock_execution_message, mock_aws_account
    )
    assert len(files["users"]) == 1
    assert files["users"][0]["name"] == EXAMPLE_USERNAME


@pytest.mark.asyncio
async def test_generate_user_resource_file_for_all_accounts(
    mock_sts_client,
    mock_iam_client,  # noqa: F811 # intentional for mocks
    mock_fs,
    mock_execution_message,
    mock_aws_account,
):
    _, templates_base_dir = mock_fs
    files = await generate_user_resource_file_for_all_accounts(
        mock_execution_message, [mock_aws_account], EXAMPLE_USERNAME
    )
    assert len(files) == 1
    assert files[0]["name"] == EXAMPLE_USERNAME


@pytest.mark.asyncio
async def test_set_user_resource_tags(
    mock_sts_client,
    mock_iam_client,  # noqa: F811 # intentional for mocks
    mock_fs,
    mock_execution_message,
    mock_aws_account,
):
    _, templates_base_dir = mock_fs

    os.makedirs(f"{templates_base_dir}/.iambic/iam/user/")
    user_resource_path = (
        f"{templates_base_dir}/.iambic/iam/user/example_username_tags.json"
    )
    await set_user_resource_tags(EXAMPLE_USERNAME, user_resource_path, mock_aws_account)

    with open(user_resource_path, "r") as f:
        contents = json.load(f)
        assert contents == {
            "Tags": [{"Key": EXAMPLE_TAG_KEY, "Value": EXAMPLE_TAG_VALUE}]
        }


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
    await collect_aws_users(mock_execution_message, config, templates_base_dir)
    output_path = f"{templates_base_dir}/.iambic/fake_execution_id/iam/user/output.json"
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
    # have to call collect_aws_users to prep the cloud response
    await collect_aws_users(mock_execution_message, config, templates_base_dir)
    # actually call the function being tested
    await generate_aws_user_templates(
        mock_execution_message, config, templates_base_dir
    )
    output_path = f"{templates_base_dir}/resources/aws/iam/user/example_account/example_username.yaml"
    assert os.path.exists(output_path)
