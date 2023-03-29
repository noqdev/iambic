from __future__ import annotations

import json

import boto3
import pytest
from moto import mock_iam

from iambic.core.models import ProposedChangeType
from iambic.plugins.v0_1_0.aws.iam.group.utils import (
    apply_group_inline_policies,
    apply_group_managed_policies,
    delete_iam_group,
    get_group,
    get_group_inline_policies,
    get_group_inline_policy_names,
    get_group_managed_policies,
    get_group_policy,
    list_groups,
    list_users_in_group,
)

EXAMPLE_GROUPNAME = "example_groupname"
EXAMPLE_INLINE_POLICY_NAME = "example_inline_policy_name"
EXAMPLE_INLINE_POLICY_DOCUMENT = """
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
EXAMPLE_MANAGED_POLICY_ARN = "arn:aws:iam::aws:policy/job-function/ViewOnlyAccess"


@pytest.fixture
def mock_iam_client():
    with mock_iam():
        iam_client = boto3.client("iam")
        _ = iam_client.create_group(
            GroupName=EXAMPLE_GROUPNAME,
        )
        _ = iam_client.put_group_policy(
            GroupName=EXAMPLE_GROUPNAME,
            PolicyName=EXAMPLE_INLINE_POLICY_NAME,
            PolicyDocument=EXAMPLE_INLINE_POLICY_DOCUMENT,
        )
        _ = iam_client.attach_group_policy(
            GroupName=EXAMPLE_GROUPNAME, PolicyArn=EXAMPLE_MANAGED_POLICY_ARN
        )
        yield iam_client


@pytest.mark.asyncio
async def test_list_users(mock_iam_client):
    groups = await list_groups(mock_iam_client)
    assert len(groups) > 0


@pytest.mark.asyncio
async def test_get_group_inline_policy_names(mock_iam_client):
    names = await get_group_inline_policy_names(EXAMPLE_GROUPNAME, mock_iam_client)
    assert names == [EXAMPLE_INLINE_POLICY_NAME]


@pytest.mark.asyncio
async def test_users_in_group(mock_iam_client):
    users = await list_users_in_group(EXAMPLE_GROUPNAME, mock_iam_client)
    assert users == []


@pytest.mark.asyncio
async def test_get_group_policy(mock_iam_client):
    inline_policy = await get_group_policy(
        EXAMPLE_GROUPNAME, EXAMPLE_INLINE_POLICY_NAME, mock_iam_client
    )
    assert inline_policy is not None


@pytest.mark.asyncio
async def test_get_group_inline_policies(mock_iam_client):
    inline_policies = await get_group_inline_policies(
        EXAMPLE_GROUPNAME, mock_iam_client
    )
    assert len(inline_policies) == 1
    assert EXAMPLE_INLINE_POLICY_NAME in inline_policies.keys()

    inline_policies = await get_group_inline_policies(
        EXAMPLE_GROUPNAME, mock_iam_client, as_dict=False
    )
    assert len(inline_policies) == 1
    assert inline_policies[0]["PolicyName"] == EXAMPLE_INLINE_POLICY_NAME


@pytest.mark.asyncio
async def test_get_group_managed_policies(mock_iam_client):
    managed_policies = await get_group_managed_policies(
        EXAMPLE_GROUPNAME, mock_iam_client
    )
    assert managed_policies[0]["PolicyArn"] == EXAMPLE_MANAGED_POLICY_ARN


@pytest.mark.asyncio
async def test_apply_group_managed_policies_on_attach(mock_iam_client):
    template_policies = [{"PolicyArn": EXAMPLE_MANAGED_POLICY_ARN}]
    existing_policies = []
    log_params = {}
    proposed_changes = await apply_group_managed_policies(
        EXAMPLE_GROUPNAME,
        mock_iam_client,
        template_policies,
        existing_policies,
        log_params,
    )
    assert proposed_changes[0].change_type == ProposedChangeType.ATTACH


@pytest.mark.asyncio
async def test_apply_group_managed_policies_on_detach(mock_iam_client):
    template_policies = []
    existing_policies = [{"PolicyArn": EXAMPLE_MANAGED_POLICY_ARN}]
    log_params = {}
    proposed_changes = await apply_group_managed_policies(
        EXAMPLE_GROUPNAME,
        mock_iam_client,
        template_policies,
        existing_policies,
        log_params,
    )
    assert proposed_changes[0].change_type == ProposedChangeType.DETACH


@pytest.mark.asyncio
async def test_apply_group_inline_policies_on_attach(mock_iam_client):
    template_policies = [{"PolicyName": EXAMPLE_INLINE_POLICY_NAME}]
    template_policies[0].update(json.loads(EXAMPLE_INLINE_POLICY_DOCUMENT))
    existing_policies = []
    log_params = {}
    proposed_changes = await apply_group_inline_policies(
        EXAMPLE_GROUPNAME,
        mock_iam_client,
        template_policies,
        existing_policies,
        log_params,
    )
    assert proposed_changes[0].change_type == ProposedChangeType.CREATE


@pytest.mark.asyncio
async def test_apply_group_inline_policies_on_detach(mock_iam_client):
    template_policies = []
    existing_policies = [{"PolicyName": EXAMPLE_INLINE_POLICY_NAME}]
    existing_policies[0].update(json.loads(EXAMPLE_INLINE_POLICY_DOCUMENT))
    log_params = {}
    proposed_changes = await apply_group_inline_policies(
        EXAMPLE_GROUPNAME,
        mock_iam_client,
        template_policies,
        existing_policies,
        log_params,
    )
    assert proposed_changes[0].change_type == ProposedChangeType.DELETE


@pytest.mark.asyncio
async def test_delete_iam_group(mock_iam_client):
    log_params = {}
    await delete_iam_group(EXAMPLE_GROUPNAME, mock_iam_client, log_params)


@pytest.mark.asyncio
async def test_get_group(mock_iam_client):
    group = await get_group(EXAMPLE_GROUPNAME, mock_iam_client)
    assert group["GroupName"] == EXAMPLE_GROUPNAME
