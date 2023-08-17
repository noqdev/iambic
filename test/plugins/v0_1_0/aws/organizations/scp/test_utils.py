from __future__ import annotations

import json

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_organizations
from moto.organizations.models import FakePolicy

import iambic.plugins.v0_1_0.aws.organizations.scp.utils as utils
from iambic.core.models import ProposedChangeType
from iambic.core.utils import normalize_dict_keys, snake_to_camelcap
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.models import AWSAccount, AWSOrganization
from iambic.plugins.v0_1_0.aws.organizations.scp.models import (
    AwsScpPolicyTemplate,
    PolicyDocumentItem,
    ServiceControlPolicyItem,
    ServiceControlPolicyTargetItem,
    TagItem,
)
from iambic.plugins.v0_1_0.aws.organizations.scp.utils import (
    apply_update_policy,
    apply_update_policy_tags,
    apply_update_policy_targets,
    create_policy,
    delete_policy,
    get_policy,
    list_policies,
    service_control_policy_is_enabled,
)

EXAMPLE_POLICY_NAME = "ServiceControlPolicyExample"
EXAMPLE_POLICY_DESCRIPTION = "Example description"
EXAMPLE_POLICY_DOCUMENT = """
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Deny",
            "Action": [
                "lex:*"
            ],
            "Resource": "*",
            "Condition": {
                "StringNotEquals": {
                    "aws:RequestedRegion": "us-west-1"
                }
            }
        }
    ]
}"""

EXAMPLE_TAGS = [
    dict(
        Key="test_key",
        Value="test_value",
    )
]

EXAMPLE_ACCOUNT_NAME = "Account Name"
EXAMPLE_ACCOUNT_EMAIL = "account@noq.dev"

EXAMPLE_ORGANIZATIONAL_UNIT_NAME = "Organizational Unit Name"


@pytest.fixture
def mock_organizations_client(monkeypatch):
    with mock_organizations():
        client = boto3.client("organizations")
        organization = client.create_organization(FeatureSet="ALL")["Organization"]
        account = client.create_account(
            AccountName=EXAMPLE_ACCOUNT_NAME,
            Email=EXAMPLE_ACCOUNT_EMAIL,
        )["CreateAccountStatus"]

        root = client.list_roots()["Roots"][0]

        org_unit = client.create_organizational_unit(
            ParentId=root["Id"], Name=EXAMPLE_ORGANIZATIONAL_UNIT_NAME
        )["OrganizationalUnit"]

        account_nested = client.create_account(
            AccountName=EXAMPLE_ACCOUNT_NAME + "_nested",
            Email=EXAMPLE_ACCOUNT_EMAIL + "_nested",
        )["CreateAccountStatus"]

        client.move_account(
            AccountId=account_nested.get("AccountId"),
            SourceParentId=root.get("Id"),
            DestinationParentId=org_unit.get("Id"),
        )

        _current_init = FakePolicy.__init__

        def new_init(self, organization, **kwargs):
            # CHECK pull request https://github.com/getmoto/moto/pull/6338
            self.tags = kwargs.get("Tags", {})
            _current_init(self, organization, **kwargs)

        FakePolicy.__init__ = new_init

        policy = client.create_policy(
            Content=EXAMPLE_POLICY_DOCUMENT,
            Description=EXAMPLE_POLICY_DESCRIPTION,
            Name=EXAMPLE_POLICY_NAME,
            Type="SERVICE_CONTROL_POLICY",
        )["Policy"]["PolicySummary"]

        client.attach_policy(PolicyId=policy["Id"], TargetId=account["AccountId"])

        client.tag_resource(ResourceId=policy["Id"], Tags=EXAMPLE_TAGS)

        yield client, [root, organization, account, org_unit, account_nested, policy]


@pytest.mark.asyncio
async def test_list_policies(mock_organizations_client, mocker):
    client, data = mock_organizations_client
    policy = data[-1]

    spy_list_targets_for_policy = mocker.spy(utils, "list_targets_for_policy")
    spy_get_policy_statements = mocker.spy(utils, "get_policy_statements")
    spy_list_tags_by_policy = mocker.spy(utils, "list_tags_by_policy")
    spy_describe_policy = mocker.spy(utils, "describe_policy")

    resp = await list_policies(client)

    assert len(resp) == 1
    assert isinstance(resp[0], ServiceControlPolicyItem)
    assert resp[0].Id == policy["Id"]
    assert len(resp[0].Targets) == 1

    spy_list_targets_for_policy.assert_called_once()
    spy_get_policy_statements.assert_called_once()
    spy_list_tags_by_policy.assert_called_once()
    spy_describe_policy.assert_called_once()


@pytest.mark.asyncio
async def test_get_policy(mock_organizations_client):
    client, data = mock_organizations_client
    policy = data[-1]

    resp = await get_policy(client, policy["Id"])

    assert isinstance(resp, ServiceControlPolicyItem)
    assert resp.Id == policy["Id"]
    assert len(resp.Targets) == 1


@pytest.mark.asyncio
async def test_delete_policy(mock_organizations_client, mocker):
    client, data = mock_organizations_client
    root = data[0]

    policy = client.create_policy(
        Content=EXAMPLE_POLICY_DOCUMENT,
        Description=EXAMPLE_POLICY_DESCRIPTION,
        Name="PolicyToDelete",
        Type="SERVICE_CONTROL_POLICY",
    )["Policy"]["PolicySummary"]

    org_unit = client.create_organizational_unit(
        ParentId=root["Id"], Name=EXAMPLE_ORGANIZATIONAL_UNIT_NAME
    )["OrganizationalUnit"]

    client.attach_policy(
        PolicyId=policy["Id"],
        TargetId=org_unit["Id"],
    )

    spy_detach_policy = mocker.spy(utils, "detach_policy")
    spy_list_targets_for_policy = mocker.spy(utils, "list_targets_for_policy")

    await delete_policy(client, policy["Id"])

    with pytest.raises(ClientError):
        client.describe_policy(PolicyId=policy["Id"])

    spy_detach_policy.assert_called_once()
    spy_list_targets_for_policy.assert_called_once()


@pytest.mark.asyncio
async def test_create_policy(mock_organizations_client):
    client, data = mock_organizations_client

    policy = await create_policy(
        client,
        dict(
            PolicyDocument=EXAMPLE_POLICY_DOCUMENT,
            Description="DESCRIPTION",
            PolicyName="create-policy",
        ),
    )

    assert client.describe_policy(PolicyId=policy["Id"])


@pytest.mark.asyncio
async def test_service_control_policy_is_enabled(mock_organizations_client, mocker):
    client, data = mock_organizations_client
    spy_describe_organization = mocker.spy(utils, "describe_organization")

    assert await service_control_policy_is_enabled(client)
    spy_describe_organization.assert_called_once()


@pytest.mark.asyncio
async def test_apply_update_policy(mock_organizations_client):
    client, data = mock_organizations_client
    scp_item = ServiceControlPolicyItem(
        Id="p-id",
        Arn="arn:aws:organizations:::policy/p-id",
        Name="OldPolicy",
        Description="this is a new policy",
        Type="SERVICE_CONTROL_POLICY",
        AwsManaged=False,
        Targets=[],
        PolicyDocument=PolicyDocumentItem.parse_obj(
            json.loads(EXAMPLE_POLICY_DOCUMENT)
        ),
        Tags=[],
    )

    template_params, template_properties = AwsScpPolicyTemplate.factory_template_props(
        "123456789123",
        scp_item,
        AWSConfig(),
        AWSOrganization(
            org_id="o-id",
            org_account_id="123456789123",
            hub_role_arn="",
        ),
    )
    policy = AwsScpPolicyTemplate(
        **template_params,
        properties=template_properties,
        file_path="/",
    )
    scp_item.Name = "NewPolicy"
    changes = await apply_update_policy(
        client,
        normalize_dict_keys(policy.properties.dict(), snake_to_camelcap),
        scp_item.dict(),
        dict(resource_type="policy"),
    )

    assert len(changes) == 1
    assert changes[0].change_type == ProposedChangeType.UPDATE


@pytest.mark.asyncio
async def test_apply_update_policy_targets(mock_organizations_client):
    client, data = mock_organizations_client
    scp_item = ServiceControlPolicyItem(
        Id="p-id",
        Arn="arn:aws:organizations:::policy/p-id",
        Name="OldPolicy",
        Description="this is a new policy",
        Type="SERVICE_CONTROL_POLICY",
        AwsManaged=False,
        Targets=[
            ServiceControlPolicyTargetItem(
                TargetId="ou-123456789",
                Arn="Asf",
                Name="Asf",
            )
        ],
        PolicyDocument=PolicyDocumentItem.parse_obj(
            json.loads(EXAMPLE_POLICY_DOCUMENT)
        ),
        Tags=[],
    )

    template_params, template_properties = AwsScpPolicyTemplate.factory_template_props(
        "123456789123",
        scp_item,
        AWSConfig(),
        AWSOrganization(
            org_id="o-id",
            org_account_id="123456789123",
            hub_role_arn="",
        ),
    )

    policy = AwsScpPolicyTemplate(
        **template_params,
        properties=template_properties,
        file_path="/",
    )

    scp_item.Targets[0].TargetId = "123456789123"

    changes = await apply_update_policy_targets(
        client,
        normalize_dict_keys(policy.properties.dict(), snake_to_camelcap),
        scp_item.dict(),
        dict(resource_type="policy"),
        AWSAccount(account_name="test"),
        AWSConfig(),
    )

    assert len(changes) == 2
    assert changes[0].change_type == ProposedChangeType.DETACH
    assert changes[1].change_type == ProposedChangeType.ATTACH


@pytest.mark.asyncio
async def test_apply_update_policy_tags(mock_organizations_client):
    client, data = mock_organizations_client
    scp_item = ServiceControlPolicyItem(
        Id="p-id",
        Arn="arn:aws:organizations:::policy/p-id",
        Name="OldPolicy",
        Description="this is a new policy",
        Type="SERVICE_CONTROL_POLICY",
        AwsManaged=False,
        Targets=[],
        PolicyDocument=PolicyDocumentItem.parse_obj(
            json.loads(EXAMPLE_POLICY_DOCUMENT)
        ),
        Tags=[TagItem(Key="key", Value="value")],
    )

    template_params, template_properties = AwsScpPolicyTemplate.factory_template_props(
        "123456789123",
        scp_item,
        AWSConfig(),
        AWSOrganization(
            org_id="o-id",
            org_account_id="123456789123",
            hub_role_arn="",
        ),
    )

    policy = AwsScpPolicyTemplate(
        **template_params,
        properties=template_properties,
        file_path="/",
    )

    scp_item.Tags[0].Key = "newKey"

    changes = await apply_update_policy_tags(
        client,
        normalize_dict_keys(policy.properties.dict(), snake_to_camelcap),
        scp_item.dict(),
        dict(resource_type="policy"),
        AWSAccount(account_name="test"),
    )

    assert len(changes) == 2
    assert changes[0].change_type == ProposedChangeType.DETACH
    assert changes[1].change_type == ProposedChangeType.ATTACH
