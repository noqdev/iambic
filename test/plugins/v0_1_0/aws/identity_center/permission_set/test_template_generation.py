from __future__ import annotations

import json
import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from test.plugins.v0_1_0.aws.iam.policy.test_utils import (
    EXAMPLE_TAG_KEY,
    EXAMPLE_TAG_VALUE,
)
from test.plugins.v0_1_0.aws.identity_center.permission_set.test_utils import (
    EXAMPLE_IDENTITY_CENTER_INSTANCE_ARN,
    EXAMPLE_PERMISSION_SET_NAME,
)
from unittest.mock import AsyncMock, MagicMock, patch

import boto3
import pytest
from moto import mock_ssoadmin

import iambic
from iambic.core.context import ctx
from iambic.core.iambic_enum import Command
from iambic.core.models import ExecutionMessage
from iambic.plugins.v0_1_0.aws.event_bridge.models import PermissionSetMessageDetails
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation import (
    collect_aws_permission_sets,
    create_templated_permission_set,
    generate_aws_permission_set_templates,
    get_template_dir,
    get_templated_permission_set_file_path,
)
from iambic.plugins.v0_1_0.aws.models import AWSAccount, IdentityCenterDetails

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
        async def get_sub_exe_files(
            self,
            *path_dirs,
            file_name_and_extension: str = None,
            flatten_results: bool = False,
        ) -> list[dict]:
            return MagicMock()

    return TestExecutionMessage(
        execution_id="test_exec_id", command=Command.IMPORT
    )  # Replace with your custom TestExecutionMessage object


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
            },
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


class MockAioFilesOpen:
    def __init__(self, content):
        self.content = content

    async def read(self):
        return json.dumps(self.content)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.mark.asyncio
async def test_create_templated_permission_set(
    permission_set_refs, permission_set_content, aws_account_map
):
    @asynccontextmanager
    async def mock_aiofiles_open(file_path, mode):
        content = permission_set_content  # Replace with your test data
        yield MockAioFilesOpen(content)

    with patch(
        "iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation.aiofiles.open",
        new=mock_aiofiles_open,
    ):
        # Mock other methods used in the function
        calculate_import_preference = MagicMock(return_value=True)
        create_or_update_template = MagicMock()
        group_int_or_str_attribute = AsyncMock()
        group_dict_attribute = AsyncMock()
        MagicMock(return_value="test_file_path")
        config = MagicMock()

        with patch(
            "iambic.plugins.v0_1_0.aws.utils.calculate_import_preference",
            calculate_import_preference,
        ), patch(
            "iambic.core.template_generation.create_or_update_template",
            create_or_update_template,
        ), patch(
            "iambic.core.template_generation.group_int_or_str_attribute",
            group_int_or_str_attribute,
        ), patch(
            "iambic.core.template_generation.group_dict_attribute", group_dict_attribute
        ):
            # Call create_templated_permission_set
            result = await create_templated_permission_set(
                aws_account_map,
                "TestPermissionSet",
                permission_set_refs,
                "permission_set_dir",
                {},
                config,
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
    gather_permission_set_names = AsyncMock(return_value=["TestPermissionSet1"])
    generate_permission_set_resource_file = AsyncMock(return_value={"test": "success"})

    with patch(
        "iambic.plugins.v0_1_0.aws.utils.get_aws_account_map", get_aws_account_map
    ), patch(
        "iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation.gather_permission_set_names",
        gather_permission_set_names,
    ), patch(
        "iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation.generate_permission_set_resource_file",
        generate_permission_set_resource_file,
    ):
        # Call collect_aws_permission_sets
        await collect_aws_permission_sets(
            exe_message,
            config,
            identity_center_template_map,
            detect_messages,
        )

        RESOURCE_DIR = ["identity_center", "permission_set"]

        file_path = exe_message.get_file_path(
            *RESOURCE_DIR, file_name_and_extension="output.json"
        )
        assert os.path.exists(file_path)


@pytest.fixture
def base_output_dir():
    return "/test/output/dir"


@pytest.mark.asyncio
async def test_generate_aws_permission_set_templates(
    exe_message, config, base_output_dir, identity_center_template_map, detect_messages
):
    # Mock methods and objects
    get_template_dir = MagicMock(return_value="/test/template/dir")
    get_aws_account_map = AsyncMock(return_value={})
    base_group_str_attribute = AsyncMock(return_value={})
    create_templated_permission_set = AsyncMock()
    delete_orphaned_templates = MagicMock()

    with patch(
        "iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation.get_template_dir",
        get_template_dir,
    ), patch(
        "iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation.get_aws_account_map",
        get_aws_account_map,
    ), patch(
        "iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation.base_group_str_attribute",
        base_group_str_attribute,
    ), patch(
        "iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation.create_templated_permission_set",
        create_templated_permission_set,
    ), patch(
        "iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation.delete_orphaned_templates",
        delete_orphaned_templates,
    ):
        # Call generate_aws_permission_set_templates
        await generate_aws_permission_set_templates(
            exe_message,
            config,
            base_output_dir,
            identity_center_template_map,
            detect_messages,
        )

        # Assertions
        get_template_dir.assert_called_once_with(base_output_dir)
        get_aws_account_map.assert_called_once_with(config)
        base_group_str_attribute.assert_called_once()


@pytest.mark.asyncio
async def test_create_templated_permission_set_import_rules(
    permission_set_refs, permission_set_content, aws_account_map
):
    """
    The test_rules in this test validate that the `iambic_managed` setting
    is set correctly based on the rules. In the event that the rules tell us
    to ignore a resource (for example, because the resource is managed by other IaC),
    the result of calling `create_templated_permission_set` is None.
    """
    from iambic.plugins.v0_1_0.aws.iambic_plugin import (
        ImportAction,
        ImportRule,
        ImportRuleTag,
    )

    test_rules = [
        {
            "rules": [
                ImportRule(
                    match_tags=[ImportRuleTag(key="Environment")],
                    action=ImportAction.set_import_only,
                ),
            ],
            "result": "import_only",
        },
        {
            "rules": [
                ImportRule(
                    match_tags=[ImportRuleTag(key="Environment", value="Test")],
                    action=ImportAction.ignore,
                ),
            ],
            "result": None,
        },
        {
            "rules": [
                ImportRule(
                    match_tags=[ImportRuleTag(key="tagkey", value="tagvalue")],
                    action=ImportAction.set_import_only,
                )
            ],
            "result": "undefined",
        },
        {
            "rules": [ImportRule(match_names=["Test*"], action=ImportAction.ignore)],
            "result": None,
        },
        {
            "rules": [
                ImportRule(match_names=["AWSServiceRole*"], action=ImportAction.ignore)
            ],
            "result": "undefined",
        },
        {
            "rules": [
                ImportRule(
                    match_paths=["/service-role/*", "/aws-service-role/*"],
                    action=ImportAction.ignore,
                )
            ],
            "result": "undefined",
        },
        {
            "rules": [
                ImportRule(
                    match_tags=[{"key": "ManagedBy", "value": "CDK"}],
                    action=ImportAction.ignore,
                )
            ],
            "result": "undefined",
        },
        {
            "rules": [
                ImportRule(
                    match_template_types=["NOQ::AWS::IdentityCenter::PermissionSet"],
                    match_tags=[ImportRuleTag(key="Environment")],
                    action=ImportAction.set_import_only,
                )
            ],
            "result": "import_only",
        },
    ]
    for test_rule in test_rules:

        @asynccontextmanager
        async def mock_aiofiles_open(file_path, mode):
            content = permission_set_content  # Replace with your test data
            yield MockAioFilesOpen(content)

        with patch(
            "iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation.aiofiles.open",
            new=mock_aiofiles_open,
        ):
            # Mock other methods used in the function
            calculate_import_preference = MagicMock(return_value=True)
            create_or_update_template = MagicMock()
            group_int_or_str_attribute = AsyncMock()
            group_dict_attribute = AsyncMock()
            MagicMock(return_value="test_file_path")
            config = MagicMock()
            config.import_rules = test_rule["rules"]

            with patch(
                "iambic.plugins.v0_1_0.aws.utils.calculate_import_preference",
                calculate_import_preference,
            ), patch(
                "iambic.core.template_generation.create_or_update_template",
                create_or_update_template,
            ), patch(
                "iambic.core.template_generation.group_int_or_str_attribute",
                group_int_or_str_attribute,
            ), patch(
                "iambic.core.template_generation.group_dict_attribute",
                group_dict_attribute,
            ):
                # Call create_templated_permission_set
                result = await create_templated_permission_set(
                    aws_account_map,
                    "TestPermissionSet",
                    permission_set_refs,
                    "permission_set_dir",
                    {},
                    config,
                )
                if not test_rule["result"]:
                    assert result is None
                else:
                    assert result.iambic_managed.value == test_rule["result"]
