from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from typing import List

import aiofiles

from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import (
    base_group_str_attribute,
    create_or_update_template,
    delete_orphaned_templates,
    get_existing_template_map,
    group_dict_attribute,
)
from iambic.core.utils import NoqSemaphore
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.models import AWSAccount
from iambic.plugins.v0_1_0.aws.organizations.service_control_policy.models import (
    ServiceControlPolicyProperties,
    ServiceControlPolicyTemplate,
)
from iambic.plugins.v0_1_0.aws.utils import get_aws_account_map, normalize_boto3_resp

log = logging.getLogger(__name__)

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
    scps = await get_account_service_control_policies(aws_account)
    formatted_scps = []

    for scp in scps:
        formatted_scp = {
            "scp_name": scp["Name"],
            "arn": scp["Arn"],
            "content": scp["Content"],
            "account_id": aws_account.account_id,
        }
        formatted_scps.append(formatted_scp)

    return formatted_scps


async def collect_service_control_policies(
    exe_message: ExecutionMessage,
    config: AWSConfig,
    base_output_dir: str,
):
    aws_account_map = await get_aws_account_map(config)

    if exe_message.provider_id:
        aws_account_map = {
            exe_message.provider_id: aws_account_map[exe_message.provider_id]
        }

    generate_scp_resource_files_semaphore = NoqSemaphore(
        generate_service_control_policy_resource_files, 25
    )

    account_scps = await generate_scp_resource_files_semaphore.process(
        [
            {"exe_message": exe_message, "aws_account": aws_account}
            for aws_account in aws_account_map.values()
        ]
    )

    # Save SCPs to JSON files
    for account in account_scps:
        for scp in account["scps"]:
            scp_path = os.path.join(
                get_response_dir(exe_message, aws_account_map[scp["account_id"]]),
                f'{scp["scp_name"]}.json',
            )

            async with aiofiles.open(scp_path, mode="w") as f:
                await f.write(json.dumps(scp["content"]))

    # Generate output JSON
    account_scp_output = json.dumps(account_scps)
    with open(
        exe_message.get_file_path(*RESOURCE_DIR, file_name_and_extension="output.json"),
        "w",
    ) as f:
        f.write(account_scp_output)

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

    # Generate the params used for attribute creation
    template_properties = {"scp_name": scp_name}
    template_params = {"identifier": scp_name}
    policy_document_resources = list()

    for account_id, scp_dict in account_id_to_scp_map.items():
        policy_document_resources.append(
            {
                "account_id": account_id,
                "resources": [{"resource_val": scp_dict["policy_document"]}],
            }
        )

    template_params["included_accounts"] = [
        aws_account_map[scp_ref["account_id"]].account_name for scp_ref in scp_refs
    ]

    template_properties["policy_document"] = await group_dict_attribute(
        aws_account_map,
        num_of_accounts,
        policy_document_resources,
        True,
    )

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
):
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
