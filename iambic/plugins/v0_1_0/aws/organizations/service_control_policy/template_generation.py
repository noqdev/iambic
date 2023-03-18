from __future__ import annotations

import asyncio
import itertools
import json
import os
from collections import defaultdict
from typing import TYPE_CHECKING, List, Optional

import aiofiles

from iambic.core.logger import log
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import (
    base_group_str_attribute,
    create_or_update_template,
    delete_orphaned_templates,
    get_existing_template_map,
    group_dict_attribute,
)
from iambic.core.utils import NoqSemaphore
from iambic.plugins.v0_1_0.aws.event_bridge.models import SCPMessageDetails
from iambic.plugins.v0_1_0.aws.models import AWSAccount
from iambic.plugins.v0_1_0.aws.organizations.service_control_policy.models import (
    ServiceControlPolicyProperties,
    ServiceControlPolicyTemplate,
)
from iambic.plugins.v0_1_0.aws.organizations.service_control_policy.utils import (
    get_service_control_policy,
)
from iambic.plugins.v0_1_0.aws.utils import get_aws_account_map, normalize_boto3_resp

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig


RESOURCE_DIR = ("resources", "aws", "organizations", "service_control_policies")


def get_response_dir(exe_message: ExecutionMessage, aws_account: AWSAccount) -> str:
    if exe_message.provider_id:
        return exe_message.get_directory(*RESOURCE_DIR)
    else:
        return exe_message.get_directory(aws_account.account_id, *RESOURCE_DIR)


async def get_account_service_control_policies(aws_account: AWSAccount):
    organizations = await aws_account.get_boto3_client("organizations")

    scp_paginator = organizations.get_paginator("list_policies")
    scp_iterator = scp_paginator.paginate(Filter="SERVICE_CONTROL_POLICY")

    scps = []
    for page in scp_iterator:
        for policy in page["Policies"]:
            policy_details = organizations.describe_policy(PolicyId=policy["Id"])
            scps.append(policy_details["Policy"])

    return scps


async def generate_service_control_policy_resource_files(
    exe_message: ExecutionMessage,
    aws_account: AWSAccount,
):
    # TODO: This should be writing the files
    scps = await get_account_service_control_policies(aws_account)
    formatted_scps = []

    for scp in scps:
        formatted_scp = {
            "scp_name": scp["PolicySummary"]["Name"],
            "arn": scp["PolicySummary"]["Arn"],
            "content": scp["Content"],
            "account_id": aws_account.account_id,
        }
        formatted_scps.append(formatted_scp)

    return formatted_scps


async def gather_service_control_policy_ids(
    aws_accounts: list[AWSAccount],
    detect_messages: list[SCPMessageDetails],
) -> list[str]:
    organizations_client_map = {
        aws_account.account_id: (
            await aws_account.get_boto3_client(
                "organizations",
                region_name=aws_account.organizations_details.region.value,
            )
        )
        for aws_account in aws_accounts
        if aws_account.organizations_details
    }

    service_control_policies = await asyncio.gather(
        *[
            get_service_control_policy(
                organizations_client_map[message.account_id],
                message.policy_id,
            )
            for message in detect_messages
        ]
    )

    return list(
        {
            service_control_policy["PolicyId"]
            for service_control_policy in service_control_policies
            if service_control_policy
        }
    )


async def collect_service_control_policies(
    exe_message: ExecutionMessage,
    config: AWSConfig,
    base_output_dir: str,
    detect_messages: Optional[list[SCPMessageDetails]] = None,
):
    if detect_messages is None:
        detect_messages = []
    resource_dir = exe_message.get_directory(*RESOURCE_DIR)
    aws_account_map = await get_aws_account_map(config)

    if exe_message.provider_id:
        aws_account_map = {
            exe_message.provider_id: aws_account_map[exe_message.provider_id]
        }

    if detect_messages:
        detect_messages = [
            msg for msg in detect_messages if isinstance(msg, SCPMessageDetails)
        ]
        if not detect_messages:
            return

    org_accounts: list[AWSAccount] = []
    if config.accounts:
        org_accounts.extend(
            [account for account in config.accounts if account.organizations_details]
        )

    if not org_accounts:
        return

    log.info("Generating AWS Service Control Policy templates.")
    log.info(
        "Beginning to retrieve Service Control Policies.",
        org_accounts=list(aws_account_map.keys()),
    )

    # TODO: This is where I left off on
    # Follow this model: iambic/plugins/v0_1_0/aws/identity_center/permission_set/template_generation.py

    await asyncio.gather(
        *[account.set_organizations_details() for account in org_accounts]
    )

    messages = []
    service_control_policy_ids = []
    if detect_messages:
        service_control_policies_in_aws = set(
            list(
                itertools.chain.from_iterable(
                    [
                        aws_account.organizations_details.service_control_policy_map.keys()
                        for aws_account in org_accounts
                        if aws_account.organizations_details
                        and aws_account.organizations_details.service_control_policy_map
                    ]
                )
            )
        )

        service_control_policy_ids = await gather_service_control_policy_ids(
            org_accounts,
            detect_messages,
        )
        service_control_policy_ids = [
            policy_id
            for policy_id in service_control_policy_ids
            if policy_id in service_control_policies_in_aws
        ]

    # Upsert service control policies
    aws_account: AWSAccount
    for aws_account in aws_account_map.values():
        if not aws_account.organizations_details:
            continue
        if not aws_account.organizations_details.service_control_policy_map:
            continue

        organizations_client = await aws_account.get_boto3_client(
            "organizations", region_name=aws_account.organizations_details.region.value
        )

        if service_control_policy_ids:
            for policy_id in service_control_policy_ids:
                if service_control_policy := aws_account.organizations_details.service_control_policy_map.get(
                    policy_id
                ):
                    messages.append(
                        dict(
                            account_id=aws_account.account_id,
                            organizations_client=organizations_client,
                            service_control_policy=service_control_policy,
                            account_resource_dir=resource_dir,
                        )
                    )
        else:
            messages.extend(
                dict(
                    account_id=aws_account.account_id,
                    organizations_client=organizations_client,
                    service_control_policy=service_control_policy,
                    account_resource_dir=resource_dir,
                )
                for service_control_policy in aws_account.organizations_details.service_control_policy_map.values()
            )

    log.info(
        "Beginning to enrich AWS Service Control Policies.",
        org_accounts=list(aws_account_map.keys()),
        permission_set_count=len(messages),
    )

    generate_scp_resource_files_semaphore = NoqSemaphore(
        generate_service_control_policy_resource_files, 25
    )

    account_scps = await generate_scp_resource_files_semaphore.process(
        [
            {"exe_message": exe_message, "aws_account": aws_account}
            for aws_account in aws_account_map.values()
        ]
    )

    log.info(
        "Finished enriching AWS Service Control Policies.",
        org_accounts=list(aws_account_map.keys()),
        permission_set_count=len(messages),
    )

    all_account_scps_output = json.dumps(account_scps)

    with open(
        exe_message.get_file_path(*RESOURCE_DIR, file_name_and_extension="output.json"),
        "w",
    ) as f:
        f.write(all_account_scps_output)

    log.info("Finished collecting Service Control Policies")


def get_templated_scp_file_path(
    scp_dir: str,
    scp_name: str,
    included_accounts: list[str],
    aws_account_map: dict[str, AWSAccount],
):
    account_names = sorted(
        [aws_account_map[account_id].account_name for account_id in included_accounts]
    )
    account_name_str = "-".join(account_names)

    file_name = f"{scp_name}_{account_name_str}.json"
    return os.path.join(scp_dir, file_name)


async def create_templated_service_control_policy(
    aws_account_map: dict[str, AWSAccount],
    scp_name: str,
    scp_refs: list[dict],
    scp_dir: str,
    existing_template_map: dict,
    config: AWSConfig,
):
    num_of_accounts = len(scp_refs)
    account_id_to_scp_map = {}
    for scp_ref in scp_refs:
        async with aiofiles.open(scp_ref["file_path"], mode="r") as f:
            content_dict = json.loads(await f.read())
            account_id_to_scp_map[scp_ref["account_id"]] = normalize_boto3_resp(
                content_dict
            )

    policy_document_resources = [
        {
            "account_id": account_id,
            "resources": [{"resource_val": scp_dict["policy_document"]}],
        }
        for account_id, scp_dict in account_id_to_scp_map.items()
    ]
    template_params = {
        "identifier": scp_name,
        "included_accounts": [
            aws_account_map[scp_ref["account_id"]].account_name for scp_ref in scp_refs
        ],
    }
    template_properties = {
        "scp_name": scp_name,
        "policy_document": await group_dict_attribute(
            aws_account_map,
            num_of_accounts,
            policy_document_resources,
            True,
        ),
    }
    file_path = get_templated_scp_file_path(
        scp_dir,
        scp_name,
        template_params.get("included_accounts"),
        aws_account_map,
    )
    return create_or_update_template(
        file_path,
        existing_template_map,
        scp_name,
        ServiceControlPolicyTemplate,
        template_params,
        ServiceControlPolicyProperties(**template_properties),
        list(aws_account_map.values()),
    )


def get_template_dir(base_dir: str) -> str:
    return str(os.path.join(base_dir, "resources", "aws", *RESOURCE_DIR))


async def generate_service_control_policy_templates(
    exe_message: ExecutionMessage,
    config: AWSConfig,
    base_output_dir: str,
    detect_messages: Optional[list[SCPMessageDetails]] = None,
):
    if not detect_messages:
        detect_messages = []
    aws_account_map = await get_aws_account_map(config)
    existing_template_map = await get_existing_template_map(
        base_output_dir, "NOQ::AWS::Organizations::ServiceControlPolicy"
    )
    resource_dir = get_template_dir(base_output_dir)
    account_scps = await exe_message.get_sub_exe_files(
        *RESOURCE_DIR, file_name_and_extension="output.json", flatten_results=True
    )

    log.info("Grouping service control policies")

    for account_scp_elem in range(len(account_scps)):
        for scp_elem in range(len(account_scps[account_scp_elem]["scps"])):
            scp_name = account_scps[account_scp_elem]["scps"][scp_elem].pop("scp_name")
            account_scps[account_scp_elem]["scps"][scp_elem]["resource_val"] = scp_name

        account_scps[account_scp_elem]["resources"] = account_scps[
            account_scp_elem
        ].pop("scps", [])

    grouped_scp_map = await base_group_str_attribute(aws_account_map, account_scps)

    log.info("Writing templated service control policies")
    all_resource_ids = set()
    for scp_name, scp_refs in grouped_scp_map.items():
        resource_template = await create_templated_service_control_policy(
            aws_account_map,
            scp_name,
            scp_refs,
            resource_dir,
            existing_template_map,
            config,
        )
        all_resource_ids.add(resource_template.resource_id)

    delete_orphaned_templates(list(existing_template_map.values()), all_resource_ids)

    log.info("Finished templated service control policy generation")
