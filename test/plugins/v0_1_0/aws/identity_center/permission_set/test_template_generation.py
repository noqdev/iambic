from __future__ import annotations
import json
import os
import shutil

import tempfile
from mock import AsyncMock, MagicMock, patch

import boto3
from moto import mock_ssoadmin
import pytest
import iambic

from iambic.core.context import ctx
from iambic.core.iambic_enum import Command
from iambic.core.models import (
    ExecutionMessage,
)
from iambic.plugins.v0_1_0.aws.event_bridge.models import PermissionSetMessageDetails
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation import (
    collect_aws_permission_sets,
    get_template_dir,
    get_templated_permission_set_file_path,
    create_templated_permission_set,
)
from iambic.plugins.v0_1_0.aws.models import (
    AWSAccount,
    IdentityCenterDetails,
)
from test.plugins.v0_1_0.aws.identity_center.permission_set.test_utils import (
    EXAMPLE_IDENTITY_CENTER_INSTANCE_ARN,
    EXAMPLE_PERMISSION_SET_NAME,
)

from test.plugins.v0_1_0.aws.iam.policy.test_utils import (
    EXAMPLE_TAG_KEY,
    EXAMPLE_TAG_VALUE,
)

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
def setup_ctx():
    # Mock the ctx.execute attribute
    original_execute = ctx.eval_only
    ctx.eval_only = False
    yield
    ctx.eval_only = original_execute


@pytest.fixture
def mock_ssoadmin_client_bundle():
    with mock_ssoadmin():
        ssoadmin_client = boto3.client("sso-admin")
        response = ssoadmin_client.create_permission_set(
            Name=EXAMPLE_PERMISSION_SET_NAME,
            InstanceArn=EXAMPLE_IDENTITY_CENTER_INSTANCE_ARN,
            Tags=[
                {
                    "Key": EXAMPLE_TAG_KEY,
                    "Value": EXAMPLE_TAG_VALUE,
                }
            ],
        )
        permission_set_arn = response["PermissionSet"]["PermissionSetArn"]
        ssoadmin_client.list_accounts_for_provisioned_permission_set = MagicMock()
        ssoadmin_client.put_inline_policy_to_permission_set = MagicMock()
        ssoadmin_client.put_permissions_boundary_to_permission_set = MagicMock()
        ssoadmin_client.detach_managed_policy_from_permission_set = MagicMock()
        ssoadmin_client.untag_resource = MagicMock()
        yield ssoadmin_client, permission_set_arn


@pytest.fixture
def permission_set_refs():
    return [
        {
            "account_id": "111111111111",
            "file_path": "permission_set_111111111111.json",
        },
        {
            "account_id": "222222222222",
            "file_path": "permission_set_222222222222.json",
        },
    ]

@pytest.fixture
def permission_set_content():
    return {
        "name": "TestPermissionSet",
        "description": "A test permission set",
        "session_duration": "PT1H",
        "permissions_boundary": {"arn": "arn:aws:iam::aws:policy/ReadOnlyAccess"},
        "tags": [{"Key": "Environment", "Value": "Test"}],
    }

@pytest.fixture
def aws_account_map(permission_set_refs):
    class TestAWSAccount(AWSAccount):
        async def get_boto3_client(self, *args, **kwargs):
            identity_center_client = AsyncMock()
            return identity_center_client

    accounts = {}
    for ref in permission_set_refs:
        accounts[ref["account_id"]] = TestAWSAccount(
            account_id=ref["account_id"],
            org_id="o-1234567890",
            account_name=f"test_account_{ref['account_id']}",
            identity_center_details=IdentityCenterDetails(
                user_map={
                    "u-1234567890abcdef0": {"UserName": "user1"},
                },
                group_map={
                    "g-1234567890abcdef0": {"DisplayName": "group1"},
                },
                org_account_map={
                    "111111111111": "test_account_111111111111",
                    "222222222222": "test_account_222222222222",
                },
            ),
        )
    return accounts


@pytest.fixture
def exe_message():
    class TestExecutionMessage(ExecutionMessage):
        pass

    return TestExecutionMessage(execution_id="test_exec_id", command=Command.IMPORT)  # Replace with your custom TestExecutionMessage object

@pytest.fixture
def config():
    class TestAWSConfig(AWSConfig):
        pass
    class TestAWSAccount(AWSAccount):
        async def set_identity_center_details(self):
            # Call the original implementation if needed
            # await super().set_identity_center_details()

            # Call your custom implementation
            return await self.custom_set_identity_center_details()
        
        async def get_boto3_client(*args, **kwargs):
            return {
                "identity-center": "identity-center-client",
            }
        
        async def custom_set_identity_center_details(self):
            return AsyncMock()

    config = TestAWSConfig()
    test_aws_account = TestAWSAccount(
        account_id="111111111111",
        account_name="test_account_111111111111",
        org_id="o-1234567890",
        identity_center_details=IdentityCenterDetails(
            user_map={
                "u-1234567890abcdef0": {"UserName": "user1"},
            },
            group_map={
                "g-1234567890abcdef0": {"DisplayName": "group1"},
            },
            org_account_map={
                "111111111111": "test_account_111111111111",
                "222222222222": "test_account_222222222222",
            },
            permission_set_map={
                "111111111111": {
                    "TestPermissionSet1": {
                        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef0/ps-1234567890abcdef0",
                        "PermissionSetId": "ps-1234567890abcdef0",
                    },
                },
                "222222222222": {
                    "TestPermissionSet2": {
                        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef0/ps-1234567890abcdef0",
                        "PermissionSetId": "ps-1234567890abcdef0",
                    },
                },
            }
        ),
    )
    config.accounts = [test_aws_account]

    return config

@pytest.fixture
def identity_center_template_map():
    return {}  # Empty template map for this test

@pytest.fixture
def detect_messages():
    return [
        PermissionSetMessageDetails(
            permission_set_name="TestPermissionSet1",
            account_id="111111111111",
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef0",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef0/ps-1234567890abcdef0",
        ),
        PermissionSetMessageDetails(
            permission_set_name="TestPermissionSet2",
            account_id="222222222222",
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef0",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef0/ps-1234567890abcdef0",
        ),
    ]


def test_get_template_dir():
    base_dir = tempfile.mkdtemp()
    try:
        template_dir = get_template_dir(base_dir)
        assert template_dir.find("resources/aws/identity_center/permission_set") != -1
    finally:
        shutil.rmtree(base_dir)


def test_get_template_permission_set_file_path():
    permission_set_dir = "test"
    permission_set_name = "{{Example_permission_set_Name}}"

    assert (
        get_templated_permission_set_file_path(permission_set_dir, permission_set_name)
        == "test/example_permission_set_name_.yaml"
    )


@pytest.mark.asyncio
async def test_create_templated_permission_set(
    permission_set_refs, permission_set_content, aws_account_map
):
    # Mock aiofiles.open
    async def mock_aiofiles_open(file_path, mode):
        async def read():
            return json.dumps(permission_set_content)
        return MagicMock(read=AsyncMock(side_effect=read))

    permission_set_refs = []

    with patch("aiofiles.open", side_effect=mock_aiofiles_open):
        # Mock other methods used in the function
        calculate_import_preference = MagicMock(return_value=True)
        create_or_update_template = MagicMock()
        group_int_or_str_attribute = AsyncMock()
        group_dict_attribute = AsyncMock()
        get_templated_permission_set_file_path = MagicMock(return_value="test_file_path")

        with patch("iambic.plugins.v0_1_0.aws.utils.calculate_import_preference", calculate_import_preference), \
             patch("iambic.core.template_generation.create_or_update_template", create_or_update_template), \
             patch("iambic.core.template_generation.group_int_or_str_attribute", group_int_or_str_attribute), \
             patch("iambic.core.template_generation.group_dict_attribute", group_dict_attribute):

            # Call create_templated_permission_set
            result = await create_templated_permission_set(
                aws_account_map,
                "TestPermissionSet",
                permission_set_refs,
                "permission_set_dir",
                {}
            )

            assert result is not None
            assert result.file_path == "permission_set_dir/testpermissionset.yaml"
            assert result.resource_id == "TestPermissionSet"
            assert result.template_type == "NOQ::AWS::IdentityCenter::PermissionSet"
            assert result.expires_at is None


# Test function
@pytest.mark.asyncio
@mock_ssoadmin
async def test_collect_aws_permission_sets(
    exe_message, config, identity_center_template_map, detect_messages
):
    class MockGeneratePermissionSetResourceFileSemaphore:
        @staticmethod
        def process(*args, **kwargs):
            return {"test": "success"}

    # Mock methods and objects
    get_aws_account_map = AsyncMock(return_value={})
    set_identity_center_details = AsyncMock()
    gather_permission_set_names = AsyncMock(return_value=["TestPermissionSet1"])
    generate_permission_set_resource_file = AsyncMock()
    NoqSemaphore = MagicMock()

    with patch("iambic.plugins.v0_1_0.aws.utils.get_aws_account_map", get_aws_account_map), \
         patch("iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation.gather_permission_set_names", gather_permission_set_names), \
         patch("iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation.generate_permission_set_resource_file", generate_permission_set_resource_file), \
         patch("iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation.generate_permission_set_resource_file_sempaphore", MockGeneratePermissionSetResourceFileSemaphore), \
         patch("iambic.core.utils.NoqSemaphore", NoqSemaphore):

        # Call collect_aws_permission_sets
        await collect_aws_permission_sets(
            exe_message,
            config,
            identity_center_template_map,
            detect_messages,
        )

        RESOURCE_DIR = ["identity_center", "permission_set"]

        file_path = exe_message.get_file_path(*RESOURCE_DIR, file_name_and_extension="output.json")
        assert os.path.exists(file_path)
