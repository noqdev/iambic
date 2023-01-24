from __future__ import annotations

import os
import pathlib

import botocore

from iambic.aws.cloudcontrol.utils import list_resources
from iambic.aws.models import AWSAccount
from iambic.aws.utils import get_aws_account_map
from iambic.config.models import Config
from iambic.core import noq_json as json
from iambic.core.logger import log
from iambic.core.template_generation import base_group_str_attribute
from iambic.core.utils import NoqSemaphore, aio_wrapper, resource_file_upsert, yaml

CLOUDCONTROL_RESPONSE_DIR = pathlib.Path.home().joinpath(
    ".iambic", "resources", "aws", "resources"
)
BOTO_CONFIG = botocore.config.Config(
    retries={"total_max_attempts": 5, "mode": "standard"}
)


async def get_available_resource_types(boto_session, region):
    """
    Returns a list of resource types that are supported in a region by querying the CloudFormation registry.
    Examples: AWS::EC2::RouteTable, AWS::IAM::Role, AWS::KMS::Key, etc.
    """
    resource_types = set()
    cloudformation_client = await aio_wrapper(
        boto_session.client,
        "cloudformation",
        region_name=region,
        config=BOTO_CONFIG,
    )

    provisioning_types = ("FULLY_MUTABLE", "IMMUTABLE")
    for provisioning_type in provisioning_types:
        call_params = {
            "Type": "RESOURCE",
            "Visibility": "PUBLIC",
            "ProvisioningType": provisioning_type,
            "DeprecatedStatus": "LIVE",
            "Filters": {"Category": "AWS_TYPES"},
        }
        while True:
            cloudformation_response = cloudformation_client.list_types(**call_params)
            for type in cloudformation_response["TypeSummaries"]:
                resource_types.add(type["TypeName"])
            try:
                call_params["NextToken"] = cloudformation_response["NextToken"]
            except KeyError:
                break

    return sorted(resource_types)


def get_account_cloudcontrol_resource_dir(account_id: str, region: str) -> str:
    account_cloudcontrol_response_dir = os.path.join(
        CLOUDCONTROL_RESPONSE_DIR, account_id, region
    )
    os.makedirs(account_cloudcontrol_response_dir, exist_ok=True)
    return account_cloudcontrol_response_dir


async def generate_account_cloudcontrol_resource_files_for_region(
    aws_account: AWSAccount, region: str, supported_resource_types: list[str]
) -> dict:
    account_role_response_dir = get_account_cloudcontrol_resource_dir(
        aws_account.account_id, region
    )
    cloudcontrol_client = await aws_account.get_boto3_client(
        "cloudcontrol", region_name=region
    )
    account_resources = await list_resources(
        cloudcontrol_client, supported_resource_types
    )
    return account_resources


async def generate_account_regions(aws_account: AWSAccount) -> list[str]:
    regions = await aws_account.get_active_regions()
    return {"aws_account_id": aws_account.account_id, "regions": regions}


async def generate_account_cloudcontrol_resource_files(
    aws_account_map, supported_resource_types: list[str]
) -> dict:
    cloudcontrol_region_semaphore = NoqSemaphore(generate_account_regions, 10)
    account_regions = await cloudcontrol_region_semaphore.process(
        [{"aws_account": aws_account} for aws_account in aws_account_map.values()]
    )
    account_regions_combined = {}
    for d in account_regions:
        account_regions_combined[d["aws_account_id"]] = d["regions"]

    cloud_control_generate_resource_files_semaphore = NoqSemaphore(
        generate_account_cloudcontrol_resource_files_for_region, 10
    )

    account_regional_resources = (
        await cloud_control_generate_resource_files_semaphore.process(
            [
                {
                    "aws_account": aws_account,
                    "region": region,
                    "supported_resource_types": supported_resource_types,
                }
                for aws_account in aws_account_map.values()
                for region in account_regions_combined.get(aws_account.account_id, [])
            ]
        )
    )

    messages = []

    response = dict(account_id=aws_account.account_id, roles=[])

    account_roles = await list_roles(iam_client)

    log.info(
        "Retrieved AWS IAM Roles.",
        account_id=aws_account.account_id,
        account_name=aws_account.account_name,
        role_count=len(account_roles),
    )

    for account_role in account_roles:
        role_path = os.path.join(
            account_role_response_dir, f'{account_role["RoleName"]}.json'
        )
        response["roles"].append(
            {
                "path": role_path,
                "name": account_role["RoleName"],
                "account_id": aws_account.account_id,
            }
        )
        messages.append(
            dict(file_path=role_path, content_as_dict=account_role, replace_file=True)
        )

    await role_resource_file_upsert_semaphore.process(messages)
    log.info(
        "Finished caching AWS IAM Roles.",
        account_id=aws_account.account_id,
        role_count=len(account_roles),
    )

    return response


async def generate_cloudcontrol_resource_files(
    configs: list[Config],
    base_output_dir: str,
) -> dict:
    # TODO: Depends on resource type
    # account_resource_dir = get_account_managed_policy_resource_dir(
    #     aws_account.account_id
    # )
    aws_account_map = await get_aws_account_map(configs)
    aws_accounts = list(aws_account_map.values())
    if len(aws_accounts) < 1:
        return {}
    boto3_session = await aws_accounts[0].get_boto3_session()
    supported_resource_types = await get_available_resource_types(
        boto3_session, aws_accounts[0].default_region
    )

    account_resources = await generate_account_cloudcontrol_resource_files(
        aws_account_map, supported_resource_types
    )

    resource_file_upsert_semaphore = NoqSemaphore(resource_file_upsert, 10)
    messages = []

    response = dict(account_id=aws_account.account_id, resources=[])
    # TODO: Remove in final version. Used to speed things up
    if aws_account.account_id != "259868150464":
        return {}
    # TODO: We need to parse all active regions, not just the default one
    account_ids = list(aws_account_map.keys())

    cloudcontrol_client = boto3_session.client(
        "cloudcontrol", region_name=aws_account.default_region
    )
    collected_resources = {}
    base_path = os.path.expanduser(output_dir)

    log.info(
        "Retrieved Supported AWS CloudControl resources.",
        account_id=aws_account.account_id,
        account_name=aws_account.account_name,
        managed_policy_count=len(account_resources),
    )

    for managed_policy in account_resources:
        policy_path = os.path.join(
            account_resource_dir, f'{managed_policy["PolicyName"]}.json'
        )
        response["managed_policies"].append(
            {
                "file_path": policy_path,
                "policy_name": managed_policy["PolicyName"],
                "arn": managed_policy["Arn"],
                "account_id": aws_account.account_id,
            }
        )
        messages.append(
            dict(
                file_path=policy_path, content_as_dict=managed_policy, replace_file=True
            )
        )

    await resource_file_upsert_semaphore.process(messages)
    log.info(
        "Finished caching AWS IAM Managed Policies.",
        account_id=aws_account.account_id,
        managed_policy_count=len(account_managed_policies),
    )

    return response


async def generate_cloudcontrol_templates(configs: list[Config], base_output_dir: str):
    aws_account_map = await get_aws_account_map(configs)
    # existing_template_map = await get_existing_template_file_map(
    #     base_output_dir, "NOQ::"
    # )
    generate_cloudcontrol_resource_files_semaphore = NoqSemaphore(
        generate_cloudcontrol_resource_files, 25
    )

    log.info("Generating AWS Cloud Control templates.")
    log.info(
        "Beginning to retrieve AWS Cloud Control templates.",
        accounts=list(aws_account_map.keys()),
    )

    account_cloudcontrol_resources = (
        await generate_cloudcontrol_resource_files_semaphore.process(
            [
                {
                    "aws_account": aws_account,
                    "output_dir": base_output_dir,
                    "aws_account_map": aws_account_map,
                }
                for aws_account in aws_account_map.values()
            ]
        )
    )
    messages = []
    for account in account_cloudcontrol_resources:
        for managed_policy in account["managed_policies"]:
            messages.append(
                {
                    "policy_name": managed_policy["policy_name"],
                    "arn": managed_policy["arn"],
                    "file_path": managed_policy["file_path"],
                    "aws_account": aws_account_map[managed_policy["account_id"]],
                }
            )

    log.info("Finished retrieving managed policy details")

    # Use these for testing `create_templated_managed_policy`
    # account_managed_policy_output = json.dumps(account_managed_policies)
    # with open("account_managed_policy_output.json", "w") as f:
    #     f.write(account_managed_policy_output)
    # with open("account_managed_policy_output.json") as f:
    #     account_managed_policies = json.loads(f.read())

    log.info("Grouping managed policies")
    # Move everything to required structure
    for account_mp_elem in range(len(account_managed_policies)):
        for mp_elem in range(
            len(account_managed_policies[account_mp_elem]["managed_policies"])
        ):
            policy_name = account_managed_policies[account_mp_elem]["managed_policies"][
                mp_elem
            ].pop("policy_name")
            account_managed_policies[account_mp_elem]["managed_policies"][mp_elem][
                "resource_val"
            ] = policy_name

        account_managed_policies[account_mp_elem][
            "resources"
        ] = account_managed_policies[account_mp_elem].pop("managed_policies", [])

    grouped_managed_policy_map = await base_group_str_attribute(
        aws_account_map, account_managed_policies
    )

    log.info("Writing templated roles")
    for policy_name, policy_refs in grouped_managed_policy_map.items():
        await create_templated_managed_policy(
            aws_account_map,
            policy_name,
            policy_refs,
            resource_dir,
            existing_template_map,
        )

    log.info("Finished templated managed policy generation")
