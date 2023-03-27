from __future__ import annotations

import json
import os
import shutil
import tempfile
from test.plugins.v0_1_0.aws.iam.role.test_utils import (  # noqa: F401 # intentional for mocks
    EXAMPLE_ROLE_NAME,
    EXAMPLE_TAG_KEY,
    EXAMPLE_TAG_VALUE,
    mock_iam_client,
)

import boto3
import pytest
from moto import mock_sts

import iambic
from iambic.core.iambic_enum import Command
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import merge_access_model_list
from iambic.plugins.v0_1_0.aws.iam.policy.models import AssumeRolePolicyDocument
from iambic.plugins.v0_1_0.aws.iam.role.models import AwsIamRoleTemplate, RoleProperties
from iambic.plugins.v0_1_0.aws.iam.role.template_generation import (
    calculate_import_preference,
    collect_aws_roles,
    generate_account_role_resource_files,
    generate_aws_role_templates,
    generate_role_resource_file_for_all_accounts,
    get_response_dir,
    set_role_resource_tags,
)
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.models import AWSAccount

TEST_TEMPLATE_DIR = "resources/aws/iam/role"
TEST_TEMPLATE_PATH = "resources/aws/iam/role/example_role.yaml"


def test_calculate_import_preference():
    template = AwsIamRoleTemplate(
        file_path="foo", identifier="foo", properties=RoleProperties(role_name="foo")
    )
    templatized_preferrence = calculate_import_preference(template)
    assert templatized_preferrence is False  # because we are not using variables

    template = AwsIamRoleTemplate(
        file_path="foo",
        identifier="{{account_name}} admin",
        properties=RoleProperties(role_name="{{account_name}} admin"),
    )
    templatized_preferrence = calculate_import_preference(template)
    assert templatized_preferrence is True  # because we are using variables

    template = AwsIamRoleTemplate(
        file_path="foo",
        identifier="{{account_name}} admin",
        properties=RoleProperties(role_name="{{account_name}} admin"),
    )
    # break template
    template.properties.description = lambda x: x  # lambda is not json-able
    templatized_preferrence = calculate_import_preference(template)
    assert templatized_preferrence is False  # because template preference crashed.


def test_merge_access_model_list_for_assume_role_policy_document(aws_accounts: list):
    existing_assume_role_policy = AssumeRolePolicyDocument()
    existing_assume_role_policy.included_accounts = [
        account.account_name for account in [aws_accounts[0], aws_accounts[1]]
    ]
    existing_list = [existing_assume_role_policy]
    for policy in existing_list:
        # the testing condition only matters if resourced_id is not unique
        assert policy.resource_id == ""

    new_assume_role_policy = AssumeRolePolicyDocument()
    new_assume_role_policy_include_accounts = [
        account.account_name for account in [aws_accounts[2]]
    ]
    new_assume_role_policy.included_accounts = new_assume_role_policy_include_accounts
    incoming_list = [
        new_assume_role_policy,
        existing_assume_role_policy.copy(deep=True),
    ]
    for policy in incoming_list:
        # the testing condition only matters if resourced_id is not unique
        assert policy.resource_id == ""

    assert (
        incoming_list[0] != existing_list[0]
    )  # this is to ensure we trigger the condition
    # in which incoming order has been mixed when we cannot relay on resource id

    considered_accounts = aws_accounts[0:3]
    merged_list = merge_access_model_list(
        incoming_list, existing_list, considered_accounts
    )
    incoming_assume_role_document: AssumeRolePolicyDocument = merged_list[0]
    assert (
        incoming_assume_role_document.included_accounts
        == new_assume_role_policy_include_accounts
    )
    existing_assume_role_document: AssumeRolePolicyDocument = merged_list[1]
    assert (
        existing_assume_role_document.included_accounts
        == existing_assume_role_policy.included_accounts
    )


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
        dir == f"{templates_base_dir}/.iambic/fake_execution_id/123456789012/iam/role"
    )


@pytest.mark.asyncio
async def test_generate_account_role_resource_files(
    mock_sts_client,
    mock_iam_client,  # noqa: F811 # intentional for mocks
    mock_fs,
    mock_execution_message,
    mock_aws_account,
):
    _, templates_base_dir = mock_fs
    files = await generate_account_role_resource_files(
        mock_execution_message, mock_aws_account
    )
    assert len(files["roles"]) == 1
    assert files["roles"][0]["name"] == EXAMPLE_ROLE_NAME


@pytest.mark.asyncio
async def test_generate_role_resource_file_for_all_accounts(
    mock_sts_client,
    mock_iam_client,  # noqa: F811 # intentional for mocks
    mock_fs,
    mock_execution_message,
    mock_aws_account,
):
    _, templates_base_dir = mock_fs
    files = await generate_role_resource_file_for_all_accounts(
        mock_execution_message, [mock_aws_account], EXAMPLE_ROLE_NAME
    )
    assert len(files) == 1
    assert files[0]["name"] == EXAMPLE_ROLE_NAME


@pytest.mark.asyncio
async def test_set_role_resource_tags(
    mock_sts_client,
    mock_iam_client,  # noqa: F811 # intentional for mocks
    mock_fs,
    mock_execution_message,
    mock_aws_account,
):
    _, templates_base_dir = mock_fs

    os.makedirs(f"{templates_base_dir}/.iambic/iam/role/")
    role_resource_path = (
        f"{templates_base_dir}/.iambic/iam/role/example_role_name_tags.json"
    )
    await set_role_resource_tags(
        EXAMPLE_ROLE_NAME, role_resource_path, mock_aws_account
    )

    with open(role_resource_path, "r") as f:
        contents = json.load(f)
        assert contents == {
            "Tags": [{"Key": EXAMPLE_TAG_KEY, "Value": EXAMPLE_TAG_VALUE}]
        }


@pytest.mark.asyncio
async def test_collect_aws_roles(
    mock_sts_client,
    mock_iam_client,  # noqa: F811 # intentional for mocks
    mock_fs,
    mock_execution_message,
    mock_aws_account,
):
    _, templates_base_dir = mock_fs
    config = AWSConfig(accounts=[mock_aws_account])
    await collect_aws_roles(mock_execution_message, config, templates_base_dir)
    output_path = f"{templates_base_dir}/.iambic/fake_execution_id/iam/role/output.json"
    with open(output_path, "r") as f:
        output_roles = json.load(f)
        assert len(output_roles) == 1


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
    # have to call collect_aws_roles to prep the cloud response
    await collect_aws_roles(mock_execution_message, config, templates_base_dir)
    # actually call the function being tested
    await generate_aws_role_templates(
        mock_execution_message, config, templates_base_dir
    )
    output_path = f"{templates_base_dir}/resources/aws/iam/role/example_account/example_role_name.yaml"
    assert os.path.exists(output_path)
