import json

import boto3
import pytest
from moto import mock_iam

from iambic.core.context import ExecutionContext
from iambic.core.models import ProposedChangeType
from iambic.plugins.v0_1_0.aws.iam.policy.utils import (
    apply_managed_policy_tags,
    apply_update_managed_policy,
    delete_managed_policy,
    get_managed_policy,
    get_managed_policy_attachments,
    get_managed_policy_version_doc,
    get_oldest_policy_version_id,
    list_managed_policies,
    list_managed_policy_tags,
    list_managed_policy_versions,
)

EXAMPLE_MANAGED_POLICY_NAME = "example_managed_policy_name"
EXAMPLE_POLICY_DOCUMENT = """
{
   "Version":"2012-10-17",
   "Statement":[
      {
         "Effect":"Allow",
         "Action":"acm:ListCertificates",
         "Resource":"*"
      }
   ]
}
"""
EXAMPLE_TAG_KEY = "test_key"
EXAMPLE_TAG_VALUE = "test_value"
EXAMPLE_POLICY_ARN = "arn:aws:iam::123456789012:policy/example_managed_policy_name"


@pytest.fixture
def mock_iam_client():
    with mock_iam():
        iam_client = boto3.client("iam")
        _ = iam_client.create_policy(
            PolicyName=EXAMPLE_MANAGED_POLICY_NAME,
            PolicyDocument=EXAMPLE_POLICY_DOCUMENT,
            Tags=[
                {
                    "Key": EXAMPLE_TAG_KEY,
                    "Value": EXAMPLE_TAG_VALUE,
                }
            ],
        )
        yield iam_client


@pytest.mark.asyncio
async def test_list_managed_policy_versions(mock_iam_client):
    versions = await list_managed_policy_versions(mock_iam_client, EXAMPLE_POLICY_ARN)
    assert len(versions) == 1


@pytest.mark.asyncio
async def test_list_managed_policy_tags(mock_iam_client):
    tags = await list_managed_policy_tags(mock_iam_client, EXAMPLE_POLICY_ARN)
    assert tags == [{"Key": EXAMPLE_TAG_KEY, "Value": EXAMPLE_TAG_VALUE}]


@pytest.mark.asyncio
async def test_get_managed_policy_version_doc(mock_iam_client):
    doc = await get_managed_policy_version_doc(
        mock_iam_client, EXAMPLE_POLICY_ARN, "v1"
    )
    assert doc == json.loads(EXAMPLE_POLICY_DOCUMENT)


@pytest.mark.asyncio
async def test_get_managed_policy_attachments(mock_iam_client):
    attachments = await get_managed_policy_attachments(
        mock_iam_client, EXAMPLE_POLICY_ARN
    )
    assert attachments["PolicyGroups"] == []
    assert attachments["PolicyUsers"] == []
    assert attachments["PolicyRoles"] == []


@pytest.mark.asyncio
async def test_get_managed_policy(mock_iam_client):
    policy = await get_managed_policy(mock_iam_client, EXAMPLE_POLICY_ARN)
    assert policy["PolicyName"] == EXAMPLE_MANAGED_POLICY_NAME


@pytest.mark.asyncio
async def test_get_oldest_policy_version_id(mock_iam_client):
    policy = await get_managed_policy(mock_iam_client, EXAMPLE_POLICY_ARN)
    policy["IsDefaultVersion"] = False
    policy["VersionId"] = "v1"
    policies = [policy]
    version = get_oldest_policy_version_id(policies)
    assert version == "v1"


@pytest.mark.asyncio
async def test_managed_policies(mock_iam_client):
    policies = await list_managed_policies(mock_iam_client)
    assert len(policies) == 1
    assert policies[0]["PolicyName"] == EXAMPLE_MANAGED_POLICY_NAME


@pytest.mark.asyncio
async def test_delete_managed_policy(mock_iam_client):
    await delete_managed_policy(mock_iam_client, EXAMPLE_POLICY_ARN, {})


@pytest.mark.asyncio
async def test_apply_update_managed_policy(mock_iam_client):
    template_policy_document = json.loads(EXAMPLE_POLICY_DOCUMENT)
    existing_policy_document = []
    log_params = {}
    context = ExecutionContext()
    proposed_changes = await apply_update_managed_policy(
        mock_iam_client,
        EXAMPLE_POLICY_ARN,
        template_policy_document,
        existing_policy_document,
        False,
        log_params,
        context,
    )
    assert proposed_changes[0].change_type == ProposedChangeType.UPDATE


@pytest.mark.asyncio
async def test_apply_user_tags_on_detach(mock_iam_client):
    template_tags = []
    existing_tags = [{"Key": EXAMPLE_TAG_KEY, "Value": EXAMPLE_TAG_VALUE}]
    log_params = {}
    context = ExecutionContext()
    proposed_changes = await apply_managed_policy_tags(
        mock_iam_client,
        EXAMPLE_POLICY_ARN,
        template_tags,
        existing_tags,
        False,
        log_params,
        context,
    )
    assert proposed_changes[0].change_type == ProposedChangeType.DETACH


@pytest.mark.asyncio
async def test_apply_user_tags_on_attach(mock_iam_client):
    template_tags = [{"Key": EXAMPLE_TAG_KEY, "Value": EXAMPLE_TAG_VALUE}]
    existing_tags = []
    log_params = {}
    context = ExecutionContext()
    proposed_changes = await apply_managed_policy_tags(
        mock_iam_client,
        EXAMPLE_POLICY_ARN,
        template_tags,
        existing_tags,
        False,
        log_params,
        context,
    )
    assert proposed_changes[0].change_type == ProposedChangeType.ATTACH
