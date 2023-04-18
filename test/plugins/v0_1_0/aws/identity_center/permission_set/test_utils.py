from typing import Optional
import boto3
from mock import MagicMock
import pytest
from moto import mock_ssoadmin
from iambic.core.models import ProviderChild
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import AWS_IDENTITY_CENTER_PERMISSION_SET_TEMPLATE_TYPE

from iambic.plugins.v0_1_0.aws.identity_center.permission_set.utils import (
    generate_permission_set_map,
    get_permission_set_details,
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

    __fields__ = {
            "template_type": MagicMock(default="type1")
        }


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
        yield ssoadmin_client, permission_set_arn


@pytest.mark.asyncio
async def test_get_permission_set_details(mock_ssoadmin_client_bundle):
    mock_ssoadmin_client, permission_set_arn = mock_ssoadmin_client_bundle
    details = await get_permission_set_details(
        mock_ssoadmin_client, EXAMPLE_IDENTITY_CENTER_INSTANCE_ARN, permission_set_arn
    )
    assert details["Name"] == EXAMPLE_PERMISSION_SET_NAME
    assert details["PermissionSetArn"] == permission_set_arn


@pytest.mark.asyncio
async def test_generate_permission_set_map(mock_ssoadmin_client_bundle):
    mock_ssoadmin_client, permission_set_arn = mock_ssoadmin_client_bundle
    accounts = [FakeAccount(
        account_id=f"12345678901{x}",
        name="test_account",
        account_owner="test_account",
    ) for x in range(6)]

    templates = [MockTemplate(
        file_path=f"test_path_{x}",
        template_type=f"AWS_IDENTITY_CENTER_PERMISSION_SET_TEMPLATE_TYPE",
    ) for x in range(6)]

    await generate_permission_set_map(accounts, templates)
    assert sum([x.set_identity_center_details_called for x in accounts]) == 6
