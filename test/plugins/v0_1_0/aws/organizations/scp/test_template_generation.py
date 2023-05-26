from __future__ import annotations

import json
import os
from test.plugins.v0_1_0.aws.iam.policy.test_utils import (  # noqa: F401 # intentional for mocks
    EXAMPLE_POLICY_DOCUMENT,
)
from test.plugins.v0_1_0.aws.organizations.scp.test_utils import (
    EXAMPLE_POLICY_DESCRIPTION,
)

import pytest

import iambic.plugins.v0_1_0.aws.organizations.scp.template_generation as template_generation
from iambic.plugins.v0_1_0.aws.event_bridge.models import (
    SCPMessageDetails as SCPPolicyMessageDetails,
)
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.models import AWSOrganization
from iambic.plugins.v0_1_0.aws.organizations.scp.models import (
    AWS_SCP_POLICY_TEMPLATE,
    AwsScpPolicyTemplate,
    PolicyDocumentItem,
    ServiceControlPolicyCache,
    ServiceControlPolicyItem,
)
from iambic.plugins.v0_1_0.aws.organizations.scp.template_generation import (
    collect_aws_scp_policies,
    generate_scp_resource_files,
    get_response_dir,
    get_template_dir,
    get_template_file_path,
    upsert_templated_scp_policies,
)

TEST_TEMPLATE_DIR = "resources/aws/organizations/scp"
TEST_TEMPLATE_PATH = f"{TEST_TEMPLATE_DIR}/example_policy.yaml"


def test_get_response_dir(mock_fs, mock_execution_message, mock_aws_account):
    _, templates_base_dir = mock_fs
    dir = get_response_dir(mock_execution_message(), mock_aws_account)
    assert (
        dir
        == f"{templates_base_dir}/.iambic/fake_execution_id/123456789012/organizations/scp"
    )


@pytest.mark.asyncio
def test_get_template_file_path(mock_aws_account, mock_aws_config, mock_fs):
    _ = mock_aws_config()
    aws_account = mock_aws_account
    account_id = aws_account.account_id
    aws_account_map = {aws_account.account_id: aws_account}

    _, templates_base_dir = mock_fs
    resource_dir = get_template_dir(templates_base_dir)

    file_path = get_template_file_path(
        resource_dir,
        "PolicyName",
        [aws_account_map[account_id].account_name],
        aws_account_map,
    )

    assert file_path == "/".join(
        [
            templates_base_dir,
            TEST_TEMPLATE_DIR,
            aws_account.account_name,
            "policyname".lower() + ".yaml",
        ]
    )


class TestCollectPolicies:
    @pytest.mark.asyncio
    async def test_collect_aws_scp_policies(
        self,
        mock_aws_config,
        mock_aws_account,
        mock_execution_message,
        mocker,
        mock_organizations_client,
        mock_fs,
    ):
        config = mock_aws_config()
        exe_message = mock_execution_message()
        exe_message.provider_id = mock_aws_account.account_id
        _, templates_base_dir = mock_fs
        _, data = mock_organizations_client
        policy = data[-1]

        spy_generate_scp_resource_files = mocker.spy(
            template_generation, "generate_scp_resource_files"
        )

        await collect_aws_scp_policies(
            exe_message=exe_message,
            config=config,
            scp_template_map={},
            detect_messages=[],
        )

        spy_generate_scp_resource_files.assert_called_once()

        output_path = f"{templates_base_dir}/.iambic/fake_execution_id/{exe_message.provider_id}/organizations/scp/output-{exe_message.provider_id}.json"
        with open(output_path, "r") as f:
            output = json.load(f)
            assert len(output[0].get("policies")) == 1
            assert output[0].get("policies")[0].get("policy_id") == policy.get("Id")

    @pytest.mark.asyncio
    async def test_detect_messages_when_create_policy(
        self,
        mock_aws_config,
        mock_aws_account,
        mock_execution_message,
        mocker,
        mock_organizations_client,
        mock_fs,
    ):
        config = mock_aws_config()
        exe_message = mock_execution_message()
        exe_message.provider_id = mock_aws_account.account_id
        client, _ = mock_organizations_client
        _, templates_base_dir = mock_fs

        spy_generate_scp_resource_files = mocker.spy(
            template_generation, "generate_scp_resource_files"
        )

        new_policy = client.create_policy(
            Content=EXAMPLE_POLICY_DOCUMENT,
            Description=EXAMPLE_POLICY_DESCRIPTION,
            Name="PolicyToRemove",
            Type="SERVICE_CONTROL_POLICY",
        )["Policy"]["PolicySummary"]

        await collect_aws_scp_policies(
            exe_message=exe_message,
            config=config,
            scp_template_map={},
            detect_messages=[
                SCPPolicyMessageDetails(
                    account_id=exe_message.provider_id,
                    policy_id=new_policy["Id"],
                    delete=False,
                    event="CreatePolicy",
                )
            ],
        )

        output_path = f"{templates_base_dir}/.iambic/fake_execution_id/{exe_message.provider_id}/organizations/scp/output-{exe_message.provider_id}.json"

        with open(output_path, "r") as f:
            output = json.load(f)
            assert len(output[0].get("policies")) == 1
            assert output[0].get("policies")[0].get("policy_id") == new_policy["Id"]

        spy_generate_scp_resource_files.assert_called_once()

    @pytest.mark.asyncio
    async def test_detect_messages_when_deleted_policy(
        self,
        mock_aws_config,
        mock_aws_account,
        mock_execution_message,
        mocker,
        mock_organizations_client,
        mock_fs,
    ):
        config = mock_aws_config()
        exe_message = mock_execution_message()
        exe_message.provider_id = mock_aws_account.account_id
        _ = mock_organizations_client
        _ = mock_fs

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

        (
            template_params,
            template_properties,
        ) = AwsScpPolicyTemplate.factory_template_props(
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
        policy = mocker.Mock()
        policy.properties.policy_id = template_properties.get("policy_id")
        spy_resource_file_upsert = mocker.spy(
            template_generation, "resource_file_upsert"
        )
        await collect_aws_scp_policies(
            exe_message=exe_message,
            config=config,
            scp_template_map={
                AWS_SCP_POLICY_TEMPLATE: {policy.properties.policy_id: policy}
            },
            detect_messages=[
                SCPPolicyMessageDetails(
                    account_id=exe_message.provider_id,
                    policy_id=template_properties.get("policy_id"),
                    delete=True,
                    event="CreatePolicy",
                )
            ],
        )

        policy.delete.asset_called_once()
        spy_resource_file_upsert.assert_not_called()


@pytest.mark.asyncio
async def test_generate_scp_resource_files(
    mock_aws_config,
    mock_aws_account,
    mock_execution_message,
    mock_organizations_client,
    mock_fs,
):
    _ = mock_aws_config()
    exe_message = mock_execution_message()
    exe_message.provider_id = mock_aws_account.account_id
    _, data = mock_organizations_client
    _ = mock_fs
    aws_account = mock_aws_account

    resource_files = await generate_scp_resource_files(exe_message, aws_account)

    assert len(resource_files.get("policies")) == 1
    with open(resource_files.get("policies")[0].get("file_path"), "r") as f:
        output = json.load(f)
        assert output.get("Id") == data[-1].get("Id")


@pytest.mark.asyncio
async def test_upsert_templated_scp_policies(
    mock_aws_config,
    mock_aws_account,
    mock_fs,
    mock_aws_organization,
    mock_organizations_client,
    mock_execution_message,
):
    config = mock_aws_config()
    aws_account = mock_aws_account
    account_id = aws_account.account_id
    aws_account_map = {aws_account.account_id: aws_account}
    existing_template_map = {}
    exe_message = mock_execution_message()
    exe_message.provider_id = mock_aws_account.account_id
    _, templates_base_dir = mock_fs
    resource_dir = get_template_dir(templates_base_dir)
    organization = mock_aws_organization
    client, data = mock_organizations_client
    template_path = f"{templates_base_dir}/.iambic/fake_execution_id/{exe_message.provider_id}/organizations/scp"
    template_file_path = f"{template_path}/output-{exe_message.provider_id}.json"

    policy = ServiceControlPolicyItem(
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

    os.makedirs(template_path)
    file = open(template_file_path, "w")
    json.dump(policy.dict(), file)
    file.close()

    policy_cache = ServiceControlPolicyCache(
        file_path=template_file_path,
        policy_id=data[-1].get("Id"),
        arn="arn:aws:organizations:::policy/p-id",
        account_id=account_id,
    )

    template: AwsScpPolicyTemplate = await upsert_templated_scp_policies(
        aws_account_map,
        account_id,
        policy_cache,  # type: ignore
        resource_dir,
        existing_template_map,
        config,
        organization,
    )

    assert template.properties.policy_name == policy.Name
    assert template.identifier == policy.Name
    assert template.properties.policy_id == policy.Id
    print(template)
