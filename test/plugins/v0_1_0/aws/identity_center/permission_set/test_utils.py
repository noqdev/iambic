import asyncio
import json
from typing import Any, Optional

import boto3
import botocore
import pytest
from mock import AsyncMock, MagicMock
from moto import mock_ssoadmin

from iambic.core.models import ProposedChangeType, ProviderChild
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import (
    AWS_IDENTITY_CENTER_PERMISSION_SET_TEMPLATE_TYPE,
)
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.utils import (
    apply_account_assignments,
    apply_permission_set_aws_managed_policies,
    apply_permission_set_customer_managed_policies,
    apply_permission_set_inline_policy,
    apply_permission_set_permission_boundary,
    apply_permission_set_tags,
    create_account_assignment,
    delete_account_assignment,
    delete_permission_set,
    enrich_permission_set_details,
    generate_permission_set_map,
    get_permission_set_details,
    get_permission_set_users_and_groups,
    get_permission_set_users_and_groups_as_access_rules,
)

EXAMPLE_PERMISSION_SET_NAME = "example_permission_set_name"
EXAMPLE_IDENTITY_CENTER_INSTANCE_ARN = "arn:aws:sso:::instance/ssoins-1234567890123456"
EXAMPLE_TAG_KEY = "test_key"
EXAMPLE_TAG_VALUE = "test_value"


class MockTemplate:
    def __init__(self, file_path, template_type, deleted=False):
        self.file_path = file_path
        self.template_type = AWS_IDENTITY_CENTER_PERMISSION_SET_TEMPLATE_TYPE
        self.deleted = deleted
        self.included_orgs: Optional[list[str]] = "*"

    __fields__ = {"template_type": MagicMock(default="type1")}


class FakeAccount(ProviderChild):
    name: str
    account_owner: str
    org_id: Optional[str] = None
    set_identity_center_details_called: int = 0
    identity_center_details: bool = True
    template_type: str = ""

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

    async def set_identity_center_details(self):
        self.set_identity_center_details_called += 1


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


@pytest.mark.asyncio
async def test_get_permission_set_details(mock_ssoadmin_client_bundle: tuple):
    mock_ssoadmin_client, permission_set_arn = mock_ssoadmin_client_bundle
    details = await get_permission_set_details(
        mock_ssoadmin_client, EXAMPLE_IDENTITY_CENTER_INSTANCE_ARN, permission_set_arn
    )
    assert details["Name"] == EXAMPLE_PERMISSION_SET_NAME
    assert details["PermissionSetArn"] == permission_set_arn


@pytest.mark.asyncio
async def test_get_permission_set_details_exception(mock_ssoadmin_client_bundle: tuple):
    mock_ssoadmin_client, permission_set_arn = mock_ssoadmin_client_bundle
    assert (
        await get_permission_set_details(
            mock_ssoadmin_client, EXAMPLE_IDENTITY_CENTER_INSTANCE_ARN, "bad_arn1234"
        )
        == {}
    )


@pytest.mark.asyncio
async def test_get_permission_set_details_invalid_arn_exception(
    mock_ssoadmin_client_bundle: tuple,
):
    mock_ssoadmin_client, permission_set_arn = mock_ssoadmin_client_bundle
    with pytest.raises(Exception):
        assert (
            await get_permission_set_details(
                mock_ssoadmin_client, EXAMPLE_IDENTITY_CENTER_INSTANCE_ARN, "bad_arn"
            )
            == {}
        )


@pytest.mark.asyncio
async def test_generate_permission_set_map(mock_ssoadmin_client_bundle: tuple):
    mock_ssoadmin_client, permission_set_arn = mock_ssoadmin_client_bundle
    accounts = [
        FakeAccount(
            account_id=f"12345678901{x}",
            name="test_account",
            account_owner="test_account",
        )
        for x in range(6)
    ]

    templates = [
        MockTemplate(
            file_path=f"test_path_{x}",
            template_type=f"AWS_IDENTITY_CENTER_PERMISSION_SET_TEMPLATE_TYPE",
        )
        for x in range(6)
    ]

    await generate_permission_set_map(accounts, templates)
    assert sum([x.set_identity_center_details_called for x in accounts]) == 6


@pytest.mark.asyncio
async def test_get_permission_set_users_and_groups(mock_ssoadmin_client_bundle: tuple):
    mock_ssoadmin_client, permission_set_arn = mock_ssoadmin_client_bundle
    accounts = [
        FakeAccount(
            account_id=f"12345678901{x}",
            name="test_account",
            account_owner="test_account",
        )
        for x in range(6)
    ]

    response = await get_permission_set_users_and_groups(
        mock_ssoadmin_client,
        EXAMPLE_IDENTITY_CENTER_INSTANCE_ARN,
        permission_set_arn,
        {},
        {},
    )

    assert response == {"user": {}, "group": {}}


@pytest.mark.asyncio
async def test_get_permission_set_users_and_groups_as_access_rules(
    mock_ssoadmin_client_bundle: tuple,
):
    mock_ssoadmin_client, permission_set_arn = mock_ssoadmin_client_bundle
    accounts = [
        FakeAccount(
            account_id=f"12345678901{x}",
            name="test_account",
            account_owner="test_account",
        )
        for x in range(6)
    ]

    response = await get_permission_set_users_and_groups_as_access_rules(
        mock_ssoadmin_client,
        EXAMPLE_IDENTITY_CENTER_INSTANCE_ARN,
        permission_set_arn,
        {},
        {},
        {},
    )

    assert response == []


@pytest.mark.asyncio
@mock_ssoadmin
async def test_enrich_permission_set_details(mock_ssoadmin_client_bundle: tuple):
    from botocore.exceptions import ClientError

    mock_ssoadmin_client, permission_set_arn = mock_ssoadmin_client_bundle

    # Set up test data
    instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef"
    permission_set_arn = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )
    permission_set_details = {"PermissionSetArn": permission_set_arn}

    # Test the enrich_permission_set_details function
    enriched_details = await enrich_permission_set_details(
        mock_ssoadmin_client, instance_arn, permission_set_details
    )

    # Assert that the enriched details contain the expected data
    assert enriched_details["PermissionSetArn"] == permission_set_arn


# Helper function to create test data
def create_test_data():
    instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef0"
    permission_set_arn = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef0/ps-1234567890abcdef0"
    )
    template_policy_arns = ["arn:aws:iam::aws:policy/AmazonS3FullAccess"]
    existing_policy_arns = ["arn:aws:iam::aws:policy/AmazonEC2FullAccess"]
    log_params = {"test_log_key": "test_log_value"}

    return (
        instance_arn,
        permission_set_arn,
        template_policy_arns,
        existing_policy_arns,
        log_params,
    )


@pytest.mark.asyncio
@mock_ssoadmin
async def test_apply_permission_set_aws_managed_policies():
    from boto3 import client

    # Set up the moto mock SSO Admin client
    sso_admin = client("sso-admin", region_name="us-west-2")

    # Set up test data
    (
        instance_arn,
        permission_set_arn,
        template_policy_arns,
        existing_policy_arns,
        log_params,
    ) = create_test_data()

    # Test the apply_permission_set_aws_managed_policies function
    response = await apply_permission_set_aws_managed_policies(
        sso_admin,
        instance_arn,
        permission_set_arn,
        template_policy_arns,
        existing_policy_arns,
        log_params,
    )

    # Assert that the response contains the expected data
    assert len(response) == 2
    assert response[0].change_type == ProposedChangeType.ATTACH
    assert response[0].resource_id == template_policy_arns[0]
    assert response[1].change_type == ProposedChangeType.DETACH
    assert response[1].resource_id == existing_policy_arns[0]


@pytest.mark.asyncio
@mock_ssoadmin
async def test_apply_permission_set_customer_managed_policies():
    from boto3 import client

    # Set up the moto mock SSO Admin client
    sso_admin = client("sso-admin", region_name="us-west-2")

    # Set up test data
    instance_arn, permission_set_arn, _, _, log_params = create_test_data()

    template_policies = [{"Path": "/custom/", "Name": "CustomS3FullAccess"}]
    existing_policies = [{"Path": "/custom/", "Name": "CustomEC2FullAccess"}]

    # Test the apply_permission_set_customer_managed_policies function
    response = await apply_permission_set_customer_managed_policies(
        sso_admin,
        instance_arn,
        permission_set_arn,
        template_policies,
        existing_policies,
        log_params,
    )

    # Assert that the response contains the expected data
    assert len(response) == 2
    assert response[0].change_type == ProposedChangeType.ATTACH
    assert response[0].resource_id == "/custom/CustomS3FullAccess"
    assert response[1].change_type == ProposedChangeType.DETACH
    assert response[1].resource_id == "/custom/CustomEC2FullAccess"


@pytest.mark.asyncio
@mock_ssoadmin
async def test_create_account_assignment(mock_ssoadmin_client_bundle: tuple):
    from boto3 import client

    # Set up the moto mock SSO Admin client
    sso_admin = client("sso-admin", region_name="us-west-2")

    account_id = "123456789012"
    instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef0"
    permission_set_arn = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef0/ps-1234567890abcdef0"
    )
    resource_type = "GROUP"
    resource_id = "test-group-id"
    resource_name = "Test Group"
    log_params = {"test_log_key": "test_log_value"}

    # Test the create_account_assignment function
    await create_account_assignment(
        sso_admin,
        account_id,
        instance_arn,
        permission_set_arn,
        resource_type,
        resource_id,
        resource_name,
        log_params,
    )

    # Verify the account assignment creation
    assignments = sso_admin.list_account_assignments(
        InstanceArn=instance_arn,
        PermissionSetArn=permission_set_arn,
        AccountId=account_id,
    )

    assert len(assignments["AccountAssignments"]) == 1
    assert (
        assignments["AccountAssignments"][0]["PermissionSetArn"] == permission_set_arn
    )
    assert assignments["AccountAssignments"][0]["PrincipalType"] == resource_type
    assert assignments["AccountAssignments"][0]["PrincipalId"] == resource_id


@pytest.mark.asyncio
@mock_ssoadmin
async def test_create_account_assignment_creation_status_check(
    mocker, mock_ssoadmin_client_bundle
):
    MockBotoCrudCall = AsyncMock(
        autospec=True,
        return_value={
            "AccountAssignmentCreationStatus": {
                "RequestId": "test-request-id",
                "Status": "IN_PROGRESS",
            }
        },
    )
    ssoadmin_client, _ = mock_ssoadmin_client_bundle
    account_id = "123456789012"
    instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef0"
    permission_set_arn = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef0/ps-1234567890abcdef0"
    )
    resource_type = "GROUP"
    resource_id = "test-group-id"
    resource_name = "Test Group"
    log_params = {"test_log_key": "test_log_value"}

    mocker.patch(
        "iambic.plugins.v0_1_0.aws.identity_center.permission_set.utils.boto_crud_call",
        new=MockBotoCrudCall,
    )
    task = asyncio.create_task(
        create_account_assignment(
            ssoadmin_client,
            account_id,
            instance_arn,
            permission_set_arn,
            resource_type,
            resource_id,
            resource_name,
            log_params,
        )
    )
    await asyncio.sleep(1.0)
    MockBotoCrudCall = AsyncMock(
        autospec=True,
        return_value={
            "AccountAssignmentCreationStatus": {
                "RequestId": "test-request-id",
                "Status": "FAILED",
            }
        },
    )
    mocker.patch(
        "iambic.plugins.v0_1_0.aws.identity_center.permission_set.utils.boto_crud_call",
        new=MockBotoCrudCall,
    )
    await asyncio.wait_for(task, timeout=2.0)
    assert task.done()


@pytest.mark.asyncio
@mock_ssoadmin
async def test_delete_account_assignment(mock_ssoadmin_client_bundle: tuple):
    from boto3 import client

    # Set up the moto mock SSO Admin client
    sso_admin = client("sso-admin", region_name="us-west-2")

    account_id = "123456789012"
    instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef0"
    permission_set_arn = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef0/ps-1234567890abcdef0"
    )
    resource_type = "GROUP"
    resource_id = "test-group-id"
    resource_name = "Test Group"
    log_params = {"test_log_key": "test_log_value"}

    # Test the create_account_assignment function
    await create_account_assignment(
        sso_admin,
        account_id,
        instance_arn,
        permission_set_arn,
        resource_type,
        resource_id,
        resource_name,
        log_params,
    )

    # Verify the account assignment creation
    assignments = sso_admin.list_account_assignments(
        InstanceArn=instance_arn,
        PermissionSetArn=permission_set_arn,
        AccountId=account_id,
    )

    assert len(assignments["AccountAssignments"]) == 1
    assert (
        assignments["AccountAssignments"][0]["PermissionSetArn"] == permission_set_arn
    )
    assert assignments["AccountAssignments"][0]["PrincipalType"] == resource_type
    assert assignments["AccountAssignments"][0]["PrincipalId"] == resource_id

    await delete_account_assignment(
        sso_admin,
        account_id,
        instance_arn,
        permission_set_arn,
        resource_type,
        resource_id,
        resource_name,
        log_params,
    )

    # Verify the account assignment creation
    assignments = sso_admin.list_account_assignments(
        InstanceArn=instance_arn,
        PermissionSetArn=permission_set_arn,
        AccountId=account_id,
    )

    assert len(assignments["AccountAssignments"]) == 0


@pytest.mark.asyncio
@mock_ssoadmin
async def test_delete_account_assignment_creation_status_check(
    mocker, mock_ssoadmin_client_bundle
):
    MockBotoCrudCall = AsyncMock(
        autospec=True,
        return_value={
            "AccountAssignmentDeletionStatus": {
                "RequestId": "test-request-id",
                "Status": "IN_PROGRESS",
            }
        },
    )
    ssoadmin_client, _ = mock_ssoadmin_client_bundle
    account_id = "123456789012"
    instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef0"
    permission_set_arn = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef0/ps-1234567890abcdef0"
    )
    resource_type = "GROUP"
    resource_id = "test-group-id"
    resource_name = "Test Group"
    log_params = {"test_log_key": "test_log_value"}

    mocker.patch(
        "iambic.plugins.v0_1_0.aws.identity_center.permission_set.utils.boto_crud_call",
        new=MockBotoCrudCall,
    )
    task = asyncio.create_task(
        delete_account_assignment(
            ssoadmin_client,
            account_id,
            instance_arn,
            permission_set_arn,
            resource_type,
            resource_id,
            resource_name,
            log_params,
        )
    )
    await asyncio.sleep(1.0)
    MockBotoCrudCall = AsyncMock(
        autospec=True,
        return_value={
            "AccountAssignmentDeletionStatus": {
                "RequestId": "test-request-id",
                "Status": "FAILED",
            }
        },
    )
    mocker.patch(
        "iambic.plugins.v0_1_0.aws.identity_center.permission_set.utils.boto_crud_call",
        new=MockBotoCrudCall,
    )
    await asyncio.wait_for(task, timeout=2.0)
    assert task.done()


@pytest.mark.asyncio
@mock_ssoadmin
async def test_apply_account_assignments():
    from boto3 import client

    # Helper function to create test data
    def create_test_data():
        instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef0"
        permission_set_arn = (
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef0/ps-1234567890abcdef0"
        )
        template_assignments = [
            {
                "account_id": "123456789012",
                "resource_id": "test-group-id",
                "resource_name": "Test Group",
                "account_name": "Test Account",
                "resource_type": "GROUP",
            }
        ]
        existing_assignments = []
        log_params = {"test_log_key": "test_log_value"}

        return (
            instance_arn,
            permission_set_arn,
            template_assignments,
            existing_assignments,
            log_params,
        )

    # Set up the moto mock SSO Admin client
    sso_admin = client("sso-admin", region_name="us-west-2")

    # Set up test data
    (
        instance_arn,
        permission_set_arn,
        template_assignments,
        existing_assignments,
        log_params,
    ) = create_test_data()

    # Test the apply_account_assignments function
    proposed_changes = await apply_account_assignments(
        sso_admin,
        instance_arn,
        permission_set_arn,
        template_assignments,
        existing_assignments,
        log_params,
    )

    # Verify the account assignment creation
    assert len(proposed_changes) == 1
    created_assignment = proposed_changes[0]
    assert created_assignment.change_type == ProposedChangeType.CREATE
    assert created_assignment.account == template_assignments[0]["account_name"]
    assert created_assignment.resource_id == template_assignments[0]["resource_name"]
    assert created_assignment.resource_type in [
        "arn:aws:iam::aws:user",
        "arn:aws:iam::aws:group",
    ]
    assert created_assignment.attribute == "account_assignment"


@pytest.mark.asyncio
@mock_ssoadmin
async def test_apply_permission_set_inline_policy(mock_ssoadmin_client_bundle: tuple):
    mock_ssoadmin_client, _ = mock_ssoadmin_client_bundle

    # Helper function to create test data
    def create_test_data():
        instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef0"
        permission_set_arn = (
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef0/ps-1234567890abcdef0"
        )
        template_inline_policy = json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": "*"}
                ],
            }
        )
        existing_inline_policy = None
        log_params = {"test_log_key": "test_log_value"}

        return (
            instance_arn,
            permission_set_arn,
            template_inline_policy,
            existing_inline_policy,
            log_params,
        )

    # Set up test data
    (
        instance_arn,
        permission_set_arn,
        template_inline_policy,
        existing_inline_policy,
        log_params,
    ) = create_test_data()

    # Test the apply_permission_set_inline_policy function
    proposed_changes = await apply_permission_set_inline_policy(
        mock_ssoadmin_client,
        instance_arn,
        permission_set_arn,
        template_inline_policy,
        existing_inline_policy,
        log_params,
    )

    # Verify the InlinePolicyDocument creation
    assert len(proposed_changes) == 1
    created_policy = proposed_changes[0]
    assert created_policy.change_type == ProposedChangeType.CREATE
    assert created_policy.resource_id == permission_set_arn
    assert created_policy.resource_type == "aws:identity_center:permission_set"
    assert created_policy.attribute == "inline_policy_document"
    assert created_policy.new_value == json.loads(template_inline_policy)


@pytest.mark.asyncio
@mock_ssoadmin
async def test_apply_permission_set_permission_boundary(
    mock_ssoadmin_client_bundle: tuple,
):
    from boto3 import client

    sso_admin_client, _ = mock_ssoadmin_client_bundle

    def create_test_data():
        instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef0"
        permission_set_arn = (
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef0/ps-1234567890abcdef0"
        )
        template_permission_boundary = {
            "ManagedPolicyArn": "arn:aws:iam::aws:policy/ReadOnlyAccess"
        }
        existing_permission_boundary = None
        log_params = {"test_log_key": "test_log_value"}
        return (
            instance_arn,
            permission_set_arn,
            template_permission_boundary,
            existing_permission_boundary,
            log_params,
        )

    # Set up test data
    (
        instance_arn,
        permission_set_arn,
        template_permission_boundary,
        existing_permission_boundary,
        log_params,
    ) = create_test_data()

    # Test the apply_permission_set_permission_boundary function
    proposed_changes = await apply_permission_set_permission_boundary(
        sso_admin_client,
        instance_arn,
        permission_set_arn,
        template_permission_boundary,
        existing_permission_boundary,
        log_params,
    )

    # Verify the PermissionsBoundary creation
    assert len(proposed_changes) == 1
    created_boundary = proposed_changes[0]
    assert created_boundary.change_type == ProposedChangeType.CREATE
    assert created_boundary.resource_id == permission_set_arn
    assert created_boundary.resource_type == "aws:identity_center:permission_set"
    assert created_boundary.attribute == "permissions_boundary"
    assert created_boundary.new_value == template_permission_boundary


@pytest.mark.asyncio
@mock_ssoadmin
async def test_apply_permission_set_tags(mock_ssoadmin_client_bundle: tuple):
    from boto3 import client

    sso_admin_client, _ = mock_ssoadmin_client_bundle

    # Helper function to create test data
    def create_test_data():
        instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef0"
        permission_set_arn = (
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef0/ps-1234567890abcdef0"
        )
        template_tags = [
            {"Key": "key1", "Value": "value1"},
            {"Key": "key2", "Value": "value2"},
        ]
        existing_tags = [
            {"Key": "key2", "Value": "value2"},
            {"Key": "key3", "Value": "value3"},
        ]
        log_params = {"test_log_key": "test_log_value"}

        return (
            instance_arn,
            permission_set_arn,
            template_tags,
            existing_tags,
            log_params,
        )

    # Set up test data
    (
        instance_arn,
        permission_set_arn,
        template_tags,
        existing_tags,
        log_params,
    ) = create_test_data()

    # Test the apply_permission_set_tags function
    proposed_changes = await apply_permission_set_tags(
        sso_admin_client,
        instance_arn,
        permission_set_arn,
        template_tags,
        existing_tags,
        log_params,
    )

    # Verify the tag changes
    assert len(proposed_changes) == 2

    # Verify tag removal
    removed_tag = proposed_changes[0]
    assert removed_tag
    assert removed_tag.change_type == ProposedChangeType.DETACH
    assert removed_tag.resource_id == permission_set_arn
    assert removed_tag.resource_type == "aws:identity_center:permission_set"
    assert removed_tag.attribute == "tags"
    assert "key3" in removed_tag.change_summary["TagKeys"]

    # Verify tag addition
    added_tag = proposed_changes[1]
    assert added_tag.change_type == ProposedChangeType.ATTACH
    assert added_tag.resource_id == permission_set_arn
    assert added_tag.resource_type == "aws:identity_center:permission_set"
    assert added_tag.attribute == "tags"
    assert added_tag.new_value == {"Key": "key1", "Value": "value1"}


@pytest.mark.asyncio
@mock_ssoadmin
async def test_delete_permission_set_not_found(mock_ssoadmin_client_bundle: tuple):
    from boto3 import client

    sso_admin_client, _ = mock_ssoadmin_client_bundle

    # Helper function to create test data
    def create_test_data():
        instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef0"
        permission_set_arn = (
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef0/ps-1234567890abcdef0"
        )
        current_permission_set = {
            "ManagedPolicies": [{"Arn": "arn:aws:iam::aws:policy/ReadOnlyAccess"}],
            "Tags": [{"Key": "key1", "Value": "value1"}],
        }
        account_assignments = []
        log_params = {"test_log_key": "test_log_value"}

        return (
            instance_arn,
            permission_set_arn,
            current_permission_set,
            account_assignments,
            log_params,
        )

    # Set up test data
    (
        instance_arn,
        permission_set_arn,
        current_permission_set,
        account_assignments,
        log_params,
    ) = create_test_data()

    with pytest.raises(botocore.exceptions.ClientError):
        await delete_permission_set(
            sso_admin_client,
            instance_arn,
            permission_set_arn,
            current_permission_set,
            account_assignments,
            log_params,
        )

    # Verify the permission set deletion
    permission_sets = sso_admin_client.list_permission_sets(InstanceArn=instance_arn)[
        "PermissionSets"
    ]
    assert permission_set_arn not in permission_sets


@pytest.mark.asyncio
@mock_ssoadmin
async def test_delete_permission_set(mock_ssoadmin_client_bundle: tuple):
    from boto3 import client

    sso_admin_client, _ = mock_ssoadmin_client_bundle

    # Helper function to create test data
    def create_test_data():
        instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef0"
        permission_set_arn = (
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef0/ps-1234567890abcdef0"
        )
        current_permission_set = {
            "ManagedPolicies": [{"Arn": "arn:aws:iam::aws:policy/ReadOnlyAccess"}],
            "Tags": [{"Key": "key1", "Value": "value1"}],
        }
        account_assignments = []
        log_params = {"test_log_key": "test_log_value"}

        return (
            instance_arn,
            permission_set_arn,
            current_permission_set,
            account_assignments,
            log_params,
        )

    # Set up test data
    (
        instance_arn,
        permission_set_arn,
        current_permission_set,
        account_assignments,
        log_params,
    ) = create_test_data()

    with pytest.raises(botocore.exceptions.ClientError):
        await delete_permission_set(
            sso_admin_client,
            instance_arn,
            permission_set_arn,
            current_permission_set,
            account_assignments,
            log_params,
        )

    # Verify the permission set deletion
    permission_sets = sso_admin_client.list_permission_sets(InstanceArn=instance_arn)[
        "PermissionSets"
    ]
    assert permission_set_arn not in permission_sets
