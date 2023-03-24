import boto3
import pytest
from moto import mock_ssoadmin

from iambic.plugins.v0_1_0.aws.identity_center.permission_set.utils import (
    get_permission_set_details,
)

EXAMPLE_PERMISSION_SET_NAME = "example_permission_set_name"
EXAMPLE_IDENTITY_CENTER_INSTANCE_ARN = "arn:aws:sso:::instance/ssoins-1234567890123456"
EXAMPLE_TAG_KEY = "test_key"
EXAMPLE_TAG_VALUE = "test_value"


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
