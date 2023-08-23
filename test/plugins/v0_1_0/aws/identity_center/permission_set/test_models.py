from __future__ import annotations

import sys
import traceback
from test.plugins.v0_1_0.aws.iam.policy.test_utils import (
    EXAMPLE_TAG_KEY,
    EXAMPLE_TAG_VALUE,
)
from test.plugins.v0_1_0.aws.identity_center.permission_set.test_utils import (
    EXAMPLE_IDENTITY_CENTER_INSTANCE_ARN,
    EXAMPLE_PERMISSION_SET_NAME,
)
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import boto3
import pytest
from moto import mock_ssoadmin
from pydantic import ValidationError

from iambic.core.context import ctx
from iambic.core.models import (
    AccountChangeDetails,
    ProposedChange,
    ProposedChangeType,
    ProviderChild,
    TemplateChangeDetails,
)
from iambic.core.template_generation import merge_access_model_list, merge_model
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import (
    AwsIdentityCenterPermissionSetTemplate,
    PermissionSetAccess,
    PermissionSetProperties,
)
from iambic.plugins.v0_1_0.aws.models import (
    AWSAccount,
    Description,
    IdentityCenterDetails,
)


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


def test_description_validation_with_default_being_none():
    properties = PermissionSetProperties(name="foo")
    assert properties.description is None


def test_description_validation_with_empty_string():
    with pytest.raises(ValidationError) as exc_info:
        PermissionSetProperties(name="foo", description="")
    if sys.version_info < (3, 10):
        exc = exc_info.value
        captured_traceback_lines = traceback.format_exception(
            type(exc), exc, exc.__traceback__
        )
    else:
        captured_traceback_lines = traceback.format_exception(
            exc_info.value
        )  # this is a pytest specific format
    captured_traceback = "\n".join(captured_traceback_lines)

    assert "description must be between 1 and 700 characters" in captured_traceback


def test_permission_boundary_with_customer_managed_policy_ref_with_default_path():
    properties = PermissionSetProperties(
        name="foo",
        description="A",
        permissions_boundary={"customer_managed_policy_reference": {"name": "foo"}},
    )
    assert properties.permissions_boundary.customer_managed_policy_reference.path == "/"


def test_permission_boundary_with_customer_managed_policy_ref_with_custom_path():
    properties = PermissionSetProperties(
        name="foo",
        description="A",
        permissions_boundary={
            "customer_managed_policy_reference": {
                "name": "foo",
                "path": "/engineering/",
            }
        },
    )
    assert (
        properties.permissions_boundary.customer_managed_policy_reference.path
        == "/engineering/"
    )


def test_statement_as_dict():
    properties = PermissionSetProperties(
        name="foo",
        description="A",
        statement={
            "Sid": "Statement1",
            "Effect": "Deny",
            "Action": ["s3:ListAllMyBuckets"],
            "Resource": "*",
        },
    )
    assert properties


def test_statement_as_list_of_dict():
    properties = PermissionSetProperties(
        name="foo",
        description="A",
        statement=[
            {
                "Sid": "Statement1",
                "Effect": "Deny",
                "Action": ["s3:ListAllMyBuckets"],
                "Resource": "*",
            }
        ],
    )
    assert properties


def test_description_validation_with_valid_string():
    properties = PermissionSetProperties(name="foo", description="A")
    assert properties.description == "A"


def test_description_validation_with_valid_list():
    properties = PermissionSetProperties(
        name="foo", description=[Description(description="A")]
    )
    assert properties.description[0].description == "A"


def test_description_validation_with_list_with_empty_string():
    with pytest.raises(ValidationError) as exc_info:
        PermissionSetProperties(name="foo", description=[Description(description="")])
    if sys.version_info < (3, 10):
        exc = exc_info.value
        captured_traceback_lines = traceback.format_exception(
            type(exc), exc, exc.__traceback__
        )
    else:
        captured_traceback_lines = traceback.format_exception(
            exc_info.value
        )  # this is a pytest specific format
    captured_traceback = "\n".join(captured_traceback_lines)
    assert "description must be between 1 and 700 characters" in captured_traceback


def test_description_sorting():
    description = [
        {"included_accounts": ["account_1", "account_2"], "description": "foo"},
        {"included_accounts": ["account_3"], "description": "bar"},
    ]
    properties_1 = PermissionSetProperties(name="foo", description=description)
    description_1 = properties_1.description
    description_2 = list(reversed(properties_1.description))
    assert description_1 != description_2  # because we reverse the list
    properties_1.description = description_2
    assert (
        properties_1.description == description_2
    )  # double check the list is reversed because validation doesn't happen after creation
    properties_1.validate_model_afterward()
    assert properties_1.description == description_1


def test_access_rule_validation():
    access_rules = [
        {"included_accounts": ["account_1", "account_2"], "users": ["foo"]},
        {"included_accounts": ["account_3"], "users": ["bar"]},
    ]
    properties_1 = PermissionSetProperties(name="foo")
    template_1 = AwsIdentityCenterPermissionSetTemplate(
        file_path="foo",
        identifier="foo",
        properties=properties_1,
        access_rules=access_rules,
    )
    access_rules_1 = template_1.access_rules
    access_rules_2 = list(reversed(template_1.access_rules))
    assert access_rules_1 != access_rules_2  # because we reverse the list
    template_1.access_rules = access_rules_2
    assert (
        template_1.access_rules == access_rules_2
    )  # double check the list is reversed because validation doesn't happen after creation
    template_1.validate_model_afterward()
    assert template_1.access_rules == access_rules_1


class FakeAccount(ProviderChild):
    name: str
    account_owner: str

    @property
    def parent_id(self) -> Optional[str]:
        """
        For example, the parent_id of an AWS account is the AWS organization ID
        """
        return self.account_owner

    @property
    def preferred_identifier(self) -> str:
        return self.name

    @property
    def all_identifiers(self) -> set[str]:
        return set([self.name])


def test_merge_template_access_rules(aws_accounts):
    existing_properties = {
        "name": "bar",
    }
    existing_access_rules = [
        {
            "included_orgs": ["org_1"],
            "users": [
                "user@example.com",
            ],
            "groups": ["group@example.com"],
            "expires_at": "in 3 days",
        }
    ]
    existing_document = AwsIdentityCenterPermissionSetTemplate(
        identifier="bar",
        file_path="foo",
        properties=existing_properties,
        access_rules=existing_access_rules,
    )
    new_properties = {
        "name": "bar",
    }
    new_access_rules = [
        {
            "included_orgs": ["org_1"],
            "users": [
                "another_user@example.com",
            ],
            "groups": ["another_group@example.com"],
        }
    ]
    new_document = AwsIdentityCenterPermissionSetTemplate(
        identifier="bar",
        file_path="foo",
        properties=new_properties,
        access_rules=new_access_rules,
    )
    merged_document: AwsIdentityCenterPermissionSetTemplate = merge_model(
        new_document, existing_document, aws_accounts
    )
    assert existing_access_rules != new_access_rules
    # the assignment for permission set is cloud driven, so we
    # merged document access_rules for permission sets has to follow
    # the cloud
    assert merged_document.access_rules[0].users == new_document.access_rules[0].users
    assert merged_document.access_rules[0].groups == new_document.access_rules[0].groups
    # but expires_at is iambic metadata, so that didn't get overwritten from cloud
    assert (
        merged_document.access_rules[0].expires_at
        == existing_document.access_rules[0].expires_at
    )


def test_merge_template_access_rules_selected_accounts(aws_accounts: list[AWSAccount]):
    existing_properties = {
        "name": "bar",
    }
    existing_access_rules = [
        {
            "included_orgs": ["org_1"],
            "included_accounts": [
                aws_accounts[0].account_name,
                aws_accounts[1].account_name,
            ],
            "users": [
                "user@example.com",
            ],
            "groups": ["group@example.com"],
            "expires_at": "in 3 days",
        }
    ]
    existing_document = AwsIdentityCenterPermissionSetTemplate(
        identifier="bar",
        file_path="foo",
        properties=existing_properties,
        access_rules=existing_access_rules,
    )
    new_properties = {
        "name": "bar",
    }
    new_access_rules = [
        {
            "included_orgs": ["org_1"],
            "included_accounts": [
                aws_accounts[0].account_name,
                aws_accounts[1].account_name,
            ],
            "users": [
                "another_user@example.com",
            ],
            "groups": ["another_group@example.com"],
        }
    ]
    new_document = AwsIdentityCenterPermissionSetTemplate(
        identifier="bar",
        file_path="foo",
        properties=new_properties,
        access_rules=new_access_rules,
    )
    merged_document: AwsIdentityCenterPermissionSetTemplate = merge_model(
        new_document, existing_document, aws_accounts
    )
    assert existing_access_rules != new_access_rules
    # the assignment for permission set is cloud driven, so we
    # merged document access_rules for permission sets has to follow
    # the cloud
    assert merged_document.access_rules[0].users == new_document.access_rules[0].users
    assert merged_document.access_rules[0].groups == new_document.access_rules[0].groups
    # but expires_at is iambic metadata, so that didn't get overwritten from cloud
    assert (
        merged_document.access_rules[0].expires_at
        == existing_document.access_rules[0].expires_at
    )


def test_merge_access_rule():
    # if we have an old list of PermissionSets and a an new list of reversed-order PermissionSets
    # after merging, the expectation is nothing has changed from the old list.

    local_access_rules = [
        {
            "included_accounts": ["account_3"],
            "users": ["bar"],
        },  # resource id is "account_3"
        {
            "included_accounts": ["account_1", "account_2"],
            "users": ["foo"],
        },  # resource id is "account_1_account_2"
    ]
    old_list = [PermissionSetAccess(**rule) for rule in local_access_rules]
    # important to use deep clone  because merge_access_model_list may mutate the the value.
    new_list = [PermissionSetAccess(**rule) for rule in reversed(local_access_rules)]
    assert old_list != new_list  # because we reverse the list
    accounts = [
        FakeAccount(name="account_1", account_owner="foo"),
        FakeAccount(name="account_2", account_owner="foo"),
        FakeAccount(name="account_3", account_owner="foo"),
    ]
    new_value = merge_access_model_list(new_list, old_list, accounts)
    for element in new_value:
        for compared_element in new_list:
            if compared_element.resource_id == element.resource_id:
                assert element.json() == compared_element.json()


@pytest.mark.asyncio
async def test_access_rules_for_account():
    # Helper function to create test data
    def create_test_data():
        properties = PermissionSetProperties(name="TestPermissionSet")
        access_rules = [
            PermissionSetAccess(
                included_accounts=["111111111111"],
                users=["user1"],
                groups=["group1"],
            ),
            PermissionSetAccess(
                included_accounts=["222222222222"],
                users=["*"],
                groups=["*"],
            ),
        ]

        return properties, access_rules

    # Set up test data
    properties, access_rules = create_test_data()
    template = AwsIdentityCenterPermissionSetTemplate(
        owner="TestOwner",
        properties=properties,
        access_rules=access_rules,
        identifier="TestIdentifier",
        file_path="TestFilePath",
    )
    aws_account = AWSAccount(
        account_id="111111111111", org_id="o-1234567890", account_name="test_account"
    )
    account_id = "111111111111"
    account_name = "test_account"
    reverse_user_map = {"user1": "u-1234567890abcdef0"}
    reverse_group_map = {"group1": "g-1234567890abcdef0"}

    # Test the _access_rules_for_account function
    result = await template._access_rules_for_account(
        aws_account, account_id, account_name, reverse_user_map, reverse_group_map
    )

    # Verify the access rules for the account
    assert result["account_id"] == account_id
    assert "u-1234567890abcdef0" in result["user"]
    assert "g-1234567890abcdef0" in result["group"]


@pytest.mark.asyncio
async def test_verbose_access_rules():
    # Helper function to create test data
    def create_test_data():
        properties = PermissionSetProperties(name="TestPermissionSet")
        access_rules = [
            PermissionSetAccess(
                included_accounts=["111111111111"],
                users=["user1"],
                groups=["group1"],
            ),
            PermissionSetAccess(
                included_accounts=["222222222222"],
                users=["*"],
                groups=["*"],
            ),
        ]

        return properties, access_rules

    # Set up test data
    properties, access_rules = create_test_data()
    template = AwsIdentityCenterPermissionSetTemplate(
        owner="TestOwner",
        properties=properties,
        access_rules=access_rules,
        identifier="TestIdentifier",
        file_path="TestFilePath",
    )
    aws_account = AWSAccount(
        account_id="111111111111",
        org_id="o-1234567890",
        account_name="test_account",
        identity_center_details=IdentityCenterDetails(
            user_map={
                "u-1234567890abcdef0": {"UserName": "user1"},
            },
            group_map={
                "g-1234567890abcdef0": {"DisplayName": "group1"},
            },
            org_account_map={
                "111111111111": "test_account",
            },
        ),
    )

    # Test the _verbose_access_rules function
    result = await template._verbose_access_rules(aws_account)

    # Verify the response
    expected_response = [
        {
            "account_id": "111111111111",
            "resource_id": "u-1234567890abcdef0",
            "resource_type": "USER",
            "resource_name": "user1",
            "account_name": "111111111111 (test_account)",
        },
        {
            "account_id": "111111111111",
            "resource_id": "g-1234567890abcdef0",
            "resource_type": "GROUP",
            "resource_name": "group1",
            "account_name": "111111111111 (test_account)",
        },
    ]
    assert result == expected_response


@pytest.fixture
def permission_set_content():
    return {
        "PermissionSet": {
            "PermissionSetArn": "arn:aws:identitycenter:us-east-1:111111111111:permissionset/ps-1234567890abcdef0",
            "Name": "TestPermissionSet",
            "Description": "A test permission set",
        }
    }


@pytest.mark.asyncio
async def test_apply_to_account(permission_set_content):
    class TestAwsIdentityCenterPermissionSetTemplate(
        AwsIdentityCenterPermissionSetTemplate
    ):
        def apply_resource_dict(self, aws_account: AWSAccount):
            return {
                "Name": "TestPermissionSet",
                "Description": "Test description",
            }

    class TestAWSAccount(AWSAccount):
        async def get_boto3_client(self, *args, **kwargs):
            identity_center_client = AsyncMock()
            return identity_center_client

    # Set up test data
    def create_test_data():
        properties = PermissionSetProperties(name="TestPermissionSet")
        access_rules = [
            PermissionSetAccess(
                included_accounts=["111111111111"],
                users=["user1"],
                groups=["group1"],
            ),
            PermissionSetAccess(
                included_accounts=["222222222222"],
                users=["*"],
                groups=["*"],
            ),
        ]

        return properties, access_rules

    (
        properties,
        access_rules,
    ) = create_test_data()  # Reuse the helper function from the previous test
    template = TestAwsIdentityCenterPermissionSetTemplate(
        owner="TestOwner",
        properties=properties,
        access_rules=access_rules,
        identifier="TestIdentifier",
        file_path="TestFilePath",
    )
    aws_account = TestAWSAccount(
        account_id="111111111111",
        org_id="o-1234567890",
        account_name="test_account",
        identity_center_details=IdentityCenterDetails(
            user_map={
                "u-1234567890abcdef0": {"UserName": "user1"},
            },
            group_map={
                "g-1234567890abcdef0": {"DisplayName": "group1"},
            },
            org_account_map={
                "111111111111": "test_account",
            },
            permission_set_map={},
        ),
    )

    identity_center_client = await aws_account.get_boto3_client("sso-admin")
    identity_center_client.create_permission_set.return_value = {
        "PermissionSet": {"PermissionSetArn": "arn:aws:sso:::permissionSet/test"},
    }

    with patch(
        "iambic.plugins.v0_1_0.aws.identity_center.permission_set.models.boto_crud_call",
        return_value=permission_set_content,
    ):
        # Execute the _apply_to_account function
        account_change_details = await template._apply_to_account(aws_account)

    # Verify the result
    assert isinstance(account_change_details, AccountChangeDetails)
    assert account_change_details.org_id == "o-1234567890"
    assert account_change_details.resource_id == "TestPermissionSet"
    assert len(account_change_details.proposed_changes) == 1
    assert account_change_details.proposed_changes[0].change_type.value == "Create"


@pytest.mark.asyncio
async def test_apply_to_account_with_current_permission_set(permission_set_content):
    class TestAwsIdentityCenterPermissionSetTemplate(
        AwsIdentityCenterPermissionSetTemplate
    ):
        def apply_resource_dict(self, aws_account: AWSAccount):
            return {
                "Name": "TestPermissionSet",
                "Description": "Test description",
            }

    class TestAWSAccount(AWSAccount):
        async def get_boto3_client(self, *args, **kwargs):
            identity_center_client = AsyncMock()
            return identity_center_client

    # Set up test data
    def create_test_data():
        properties = PermissionSetProperties(name="TestPermissionSet")
        access_rules = [
            PermissionSetAccess(
                included_accounts=["111111111111"],
                users=["user1"],
                groups=["group1"],
            ),
            PermissionSetAccess(
                included_accounts=["222222222222"],
                users=["*"],
                groups=["*"],
            ),
        ]

        return properties, access_rules

    (
        properties,
        access_rules,
    ) = create_test_data()  # Reuse the helper function from the previous test
    template = TestAwsIdentityCenterPermissionSetTemplate(
        owner="TestOwner",
        properties=properties,
        access_rules=access_rules,
        identifier="TestIdentifier",
        file_path="TestFilePath",
    )
    aws_account = TestAWSAccount(
        account_id="111111111111",
        org_id="o-1234567890",
        account_name="test_account",
        identity_center_details=IdentityCenterDetails(
            user_map={
                "u-1234567890abcdef0": {"UserName": "user1"},
            },
            group_map={
                "g-1234567890abcdef0": {"DisplayName": "group1"},
            },
            org_account_map={
                "111111111111": "test_account",
            },
            permission_set_map={
                "TestPermissionSet": {
                    "PermissionSetArn": "arn:aws:identitycenter:us-east-1:111111111111:permissionset/ps-1234567890abcdef0",
                    "Name": "TestPermissionSet",
                    "Description": "A test permission set",
                    "SessionDuration": "PT1H",
                    "RelayStateType": "SSO_USER_ATTRIBUTE",
                    "CreationDate": "2021-01-01T00:00:00.000Z",
                    "LastModifiedDate": "2021-01-01T00:00:00.000Z",
                    "Tags": [
                        {
                            "Key": "TestTag",
                            "Value": "TestValue",
                        }
                    ],
                }
            },
        ),
    )

    identity_center_client = await aws_account.get_boto3_client("sso-admin")
    identity_center_client.create_permission_set.return_value = {
        "PermissionSet": {"PermissionSetArn": "arn:aws:sso:::permissionSet/test"},
    }

    access_rules = [
        {
            "account_id": "111111111111",
            "resource_id": "TestPermissionSet",
            "resource_type": "permission_set",
            "resource_name": "TestPermissionSet",
            "account_name": "test_account",
        }
    ]

    with patch(
        "iambic.plugins.v0_1_0.aws.identity_center.permission_set.models.boto_crud_call",
        return_value=permission_set_content,
    ), patch(
        "iambic.plugins.v0_1_0.aws.identity_center.permission_set.models.get_permission_set_users_and_groups_as_access_rules",
        return_value=access_rules,
    ):
        # Execute the _apply_to_account function
        account_change_details = await template._apply_to_account(aws_account)

    # Verify the result
    assert isinstance(account_change_details, AccountChangeDetails)
    assert account_change_details.org_id == "o-1234567890"
    assert account_change_details.resource_id == "TestPermissionSet"
    assert len(account_change_details.proposed_changes) == 1
    assert account_change_details.proposed_changes[0].change_type.value == "Update"


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_ctx")
@mock_ssoadmin
async def test_apply():
    class TestAwsIdentityCenterPermissionSetTemplate(
        AwsIdentityCenterPermissionSetTemplate
    ):
        def evaluate_on_provider(self, *args, **kwargs):
            return MagicMock(return_value=True)

        def _apply_resource_dict(self, *args, **kwargs):
            return MagicMock(return_value={})

        async def _apply_to_account(
            self, aws_account: AWSAccount
        ) -> AccountChangeDetails:
            return AccountChangeDetails(
                account="AWS_ACCOUNT",
                resource_id="TestPermissionSet",
                exceptions_seen=[],
            )

    # Create a TestAwsIdentityCenterPermissionSetTemplate instance
    def create_test_data():
        properties = PermissionSetProperties(name="TestPermissionSet")
        access_rules = [
            PermissionSetAccess(
                included_accounts=["111111111111"],
                users=["user1"],
                groups=["group1"],
            ),
            PermissionSetAccess(
                included_accounts=["222222222222"],
                users=["*"],
                groups=["*"],
            ),
        ]

        return properties, access_rules

    properties, access_rules = create_test_data()
    template = TestAwsIdentityCenterPermissionSetTemplate(
        owner="TestOwner",
        properties=properties,
        access_rules=access_rules,
        identifier="TestIdentifier",
        file_path="TestFilePath",
    )

    # Create a AWSConfig instance with TestAWSAccount
    aws_account = AWSAccount(
        account_id="111111111111",
        org_id="o-1234567890",
        account_name="test_account",
        identity_center_details=IdentityCenterDetails(
            user_map={
                "u-1234567890abcdef0": {"UserName": "user1"},
            },
            group_map={
                "g-1234567890abcdef0": {"DisplayName": "group1"},
            },
            org_account_map={
                "111111111111": "test_account",
            },
        ),
    )
    config = AWSConfig(accounts=[aws_account])

    # Execute the apply function
    result = await template.apply(config)

    # Verify the result
    assert isinstance(result, TemplateChangeDetails)
    assert len(result.exceptions_seen) == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_ctx")
@mock_ssoadmin
async def test_apply_with_exception():
    class TestAwsIdentityCenterPermissionSetTemplate(
        AwsIdentityCenterPermissionSetTemplate
    ):
        def evaluate_on_provider(self, *args, **kwargs):
            return MagicMock(return_value=True)

        def _apply_resource_dict(self, *args, **kwargs):
            return MagicMock(return_value={})

        async def _apply_to_account(
            self, aws_account: AWSAccount
        ) -> AccountChangeDetails:
            return AccountChangeDetails(
                account="AWS_ACCOUNT",
                resource_id="TestPermissionSet",
                exceptions_seen=[
                    ProposedChange(
                        change_type=ProposedChangeType.CREATE,
                        account="AWS_ACCOUNT",
                        exceptions_seen=[],
                    )
                ],
            )

    # Create a TestAwsIdentityCenterPermissionSetTemplate instance
    def create_test_data():
        properties = PermissionSetProperties(name="TestPermissionSet")
        access_rules = [
            PermissionSetAccess(
                included_accounts=["111111111111"],
                users=["user1"],
                groups=["group1"],
            ),
            PermissionSetAccess(
                included_accounts=["222222222222"],
                users=["*"],
                groups=["*"],
            ),
        ]

        return properties, access_rules

    properties, access_rules = create_test_data()
    template = TestAwsIdentityCenterPermissionSetTemplate(
        owner="TestOwner",
        properties=properties,
        access_rules=access_rules,
        identifier="TestIdentifier",
        file_path="TestFilePath",
    )

    # Create a AWSConfig instance with TestAWSAccount
    aws_account = AWSAccount(
        account_id="111111111111",
        org_id="o-1234567890",
        account_name="test_account",
        identity_center_details=IdentityCenterDetails(
            user_map={
                "u-1234567890abcdef0": {"UserName": "user1"},
            },
            group_map={
                "g-1234567890abcdef0": {"DisplayName": "group1"},
            },
            org_account_map={
                "111111111111": "test_account",
            },
        ),
    )
    config = AWSConfig(accounts=[aws_account])

    # Execute the apply function
    result = await template.apply(config)

    # Verify the result
    assert isinstance(result, TemplateChangeDetails)
    assert len(result.exceptions_seen) == 1
