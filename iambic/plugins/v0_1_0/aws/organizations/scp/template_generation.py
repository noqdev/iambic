from __future__ import annotations

import asyncio
import os
from itertools import groupby
from typing import TYPE_CHECKING, Any, Optional, Union

import aiofiles

from iambic.core import noq_json as json
from iambic.core.logger import log
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import (
    create_or_update_template,
    delete_orphaned_templates,
)
from iambic.core.utils import NoqSemaphore, resource_file_upsert
from iambic.plugins.v0_1_0.aws.event_bridge.models import (
    SCPMessageDetails as SCPPolicyMessageDetails,
)
from iambic.plugins.v0_1_0.aws.models import AWSAccount, AWSOrganization
from iambic.plugins.v0_1_0.aws.organizations.scp.exceptions import (
    OrganizationAccountRequiredException,
)
from iambic.plugins.v0_1_0.aws.organizations.scp.models import (
    AWS_SCP_POLICY_TEMPLATE,
    AwsScpPolicyTemplate,
    PolicyProperties,
    ServiceControlPolicyCache,
    ServiceControlPolicyItem,
    ServiceControlPolicyResourceFiles,
)
from iambic.plugins.v0_1_0.aws.organizations.scp.utils import get_policy, list_policies
from iambic.plugins.v0_1_0.aws.utils import get_aws_account_map

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig

RESOURCE_DIR = ["organizations", "scp"]


def get_response_dir(exe_message: ExecutionMessage, aws_account: AWSAccount) -> str:
    if exe_message.provider_id:
        return exe_message.get_directory(*RESOURCE_DIR)
    else:
        return exe_message.get_directory(aws_account.account_id, *RESOURCE_DIR)


def get_template_dir(base_dir: str) -> str:
    return str(os.path.join(base_dir, "resources", "aws", *RESOURCE_DIR))


async def generate_scp_resource_files(
    exe_message: ExecutionMessage,
    aws_account: AWSAccount,
    filtered_policies: Optional[list[str]] = None,
) -> ServiceControlPolicyResourceFiles:
    resource_dir = get_response_dir(exe_message, aws_account)
    resource_file_upsert_semaphore = NoqSemaphore(resource_file_upsert, 10)
    messages = []

    response = ServiceControlPolicyResourceFiles(
        account_id=aws_account.account_id, policies=[]
    )
    organizations_client = await aws_account.get_boto3_client("organizations")
    if filtered_policies is None:
        scp_policies = await list_policies(organizations_client)
    elif len(filtered_policies) > 0:
        scp_policies = await asyncio.gather(
            *[
                get_policy(organizations_client, policy_id)
                for policy_id in set(filtered_policies)
            ]
        )
    else:
        return response

    log.debug(
        "Retrieved AWS SCP Policies.",
        account_id=aws_account.account_id,
        account_name=aws_account.account_name,
        scp_policies_count=len(scp_policies),
    )

    for policy in scp_policies:
        policy_path = os.path.join(resource_dir, f"{policy.Id}.json")
        response["policies"].append(
            ServiceControlPolicyCache(
                file_path=policy_path,
                policy_id=policy.Id,
                arn=policy.Arn,
                account_id=aws_account.account_id,
            )
        )
        messages.append(
            dict(
                file_path=policy_path,
                content_as_dict=policy.dict(),
                replace_file=True,
            )
        )

    await resource_file_upsert_semaphore.process(messages)
    log.debug(
        "Finished caching AWS SCP Policies.",
        account_id=aws_account.account_id,
        managed_policy_count=len(scp_policies),
    )

    return response


async def collect_aws_scp_policies(
    exe_message: ExecutionMessage,
    config: AWSConfig,
    scp_template_map: dict,
    detect_messages: Optional[list[Union[SCPPolicyMessageDetails, Any]]] = None,
):
    aws_account_map = await get_organizations_account_map(exe_message, config)

    if detect_messages:
        detect_messages = [
            dm
            for dm in detect_messages
            if isinstance(dm, SCPPolicyMessageDetails)
            and exe_message.provider_id == dm.account_id
        ]
        if not detect_messages:
            return

    log.info(
        "Generating AWS SCP templates. Beginning to retrieve AWS SCP policies.",
        accounts=list(aws_account_map.keys()),
    )

    if detect_messages:
        # Remove deleted or mark templates for update
        delete_policies = set([dm.policy_id for dm in detect_messages if dm.delete])

        if delete_policies:
            existing_template_map = dict(
                [
                    (k, next(g))
                    for k, g in groupby(
                        scp_template_map.get(AWS_SCP_POLICY_TEMPLATE, {}).values(),
                        lambda p: p.properties.policy_id,
                    )
                ]
            )

            for policy in delete_policies:
                if existing_template := existing_template_map.get(policy):
                    existing_template.delete()

        generate_scp_resource_files_semaphore = NoqSemaphore(
            generate_scp_resource_files, 25
        )

        scp_policies: list[
            ServiceControlPolicyResourceFiles
        ] = await generate_scp_resource_files_semaphore.process(
            [
                {
                    "exe_message": exe_message,
                    "aws_account": aws_account_map[exe_message.provider_id],
                    "filtered_policies": set(
                        [
                            dm.policy_id
                            for dm in detect_messages
                            if not dm.delete and dm.policy_id not in delete_policies
                        ]
                    ),
                }
            ]
        )

    else:
        generate_scp_resource_files_semaphore = NoqSemaphore(
            generate_scp_resource_files, 25
        )

        scp_policies: list[
            ServiceControlPolicyResourceFiles
        ] = await generate_scp_resource_files_semaphore.process(
            [
                {
                    "exe_message": exe_message,
                    "aws_account": aws_account_map[exe_message.provider_id],  # type: ignore
                }
            ]
        )

    log.info(
        "Finished retrieving AWS SCP policy details",
        accounts=list(aws_account_map.keys()),
    )

    with open(
        exe_message.get_file_path(
            *RESOURCE_DIR,
            file_name_and_extension=f"output-{exe_message.provider_id}.json",
        ),
        "w",
    ) as f:
        f.write(json.dumps(scp_policies))


async def generate_aws_scp_policy_templates(
    exe_message: ExecutionMessage,
    config: AWSConfig,
    base_output_dir: str,
    scp_template_map: dict,
    detect_messages: Optional[list[Union[SCPPolicyMessageDetails, Any]]] = None,
):
    """Generate AWS SCP policy templates

    Note:
        this function is executed for each organization account (provider_id)
        thus, each output file has one item in the list (scp_policies)
    """

    aws_account_map = await get_organizations_account_map(exe_message, config)

    existing_template_map = scp_template_map.get(AWS_SCP_POLICY_TEMPLATE, {})
    resource_dir = get_template_dir(base_output_dir)

    scp_policies: list[
        ServiceControlPolicyResourceFiles
    ] = await exe_message.get_sub_exe_files(
        *RESOURCE_DIR,
        file_name_and_extension=f"output-{exe_message.provider_id}.json",
        flatten_results=True,
    )  # type: ignore

    policies: list[Union[ServiceControlPolicyCache, dict]] = []
    account_id: str
    account_id, policies = scp_policies[0].values()  # type: ignore

    tasks = []
    organization: AWSOrganization = list(
        filter(lambda o: o.org_account_id == account_id, config.organizations)
    )[0]

    for policy in policies:
        tasks.append(
            upsert_templated_scp_policies(
                aws_account_map,
                account_id,
                policy,  # type: ignore
                resource_dir,
                existing_template_map,
                config,
                organization,
            )
        )

    log.debug("Writing templated scp policies")

    templates: list[AwsScpPolicyTemplate] = await asyncio.gather(*tasks)

    # NEVER call this if messages are passed in because all_resource_ids will only contain those resources
    if not detect_messages:
        # if some templates are iambic managed, they will be None
        all_resource_ids = set([t.identifier for t in templates if t is not None])
        delete_orphaned_templates(
            list(existing_template_map.values()), all_resource_ids
        )

    log.info("Finished templated scp policies generation")

    return


async def get_organizations_account_map(exe_message, config):
    aws_account_map = await get_aws_account_map(config)

    # SCP policies should be retrieved just for the organization account (provider_id)
    if not exe_message.provider_id or not aws_account_map.get(exe_message.provider_id):
        raise OrganizationAccountRequiredException()

    aws_account_map = {
        exe_message.provider_id: aws_account_map[exe_message.provider_id]
    }

    return aws_account_map


async def upsert_templated_scp_policies(
    aws_account_map: dict,
    account_id: str,
    policy: ServiceControlPolicyCache,  # type: ignore
    resource_dir: str,
    existing_template_map: dict,
    config,
    organization: AWSOrganization,
):
    async with aiofiles.open(policy.get("file_path"), mode="r") as f:
        content_dict = json.loads(await f.read())
        # policy = normalize_dict_keys(content_dict)  # type: ignore
        policy: ServiceControlPolicyItem = ServiceControlPolicyItem.parse_obj(
            content_dict
        )

    file_path = get_template_file_path(
        resource_dir,
        policy.Name,
        [aws_account_map[account_id].account_name],
        aws_account_map,
    )

    template_params, template_properties = AwsScpPolicyTemplate.factory_template_props(
        account_id,
        policy,
        config,
        organization,
    )

    return create_or_update_template(
        file_path,
        existing_template_map,
        policy.Name,
        AwsScpPolicyTemplate,
        template_params,
        PolicyProperties(**template_properties),
        list(aws_account_map.values()),
    )


def get_template_file_path(
    managed_policy_dir: str,
    policy_name: str,
    included_accounts: list[str],
    account_map: dict[str, AWSAccount],
):
    if len(included_accounts) > 1:
        separator = "multi_account"
    elif included_accounts == ["*"] or included_accounts is None:
        separator = "all_accounts"
    else:
        separator = included_accounts[0]

    file_name = (
        policy_name.replace(" ", "")
        .replace("{{var.", "")
        .replace("{{", "")
        .replace("}}_", "_")
        .replace("}}", "_")
        .replace(".", "_")
        .lower()
    )
    return str(os.path.join(managed_policy_dir, separator, f"{file_name}.yaml"))
