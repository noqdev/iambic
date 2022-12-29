from __future__ import annotations

import os
import pathlib

import aiofiles

from iambic.aws.iam.policy.models import ManagedPolicyTemplate
from iambic.aws.iam.policy.utils import list_managed_policies
from iambic.aws.models import AWSAccount
from iambic.aws.utils import get_aws_account_map, normalize_boto3_resp
from iambic.config.models import Config
from iambic.core import noq_json as json
from iambic.core.logger import log
from iambic.core.template_generation import (
    base_group_str_attribute,
    get_existing_template_file_map,
    group_dict_attribute,
    group_int_or_str_attribute,
)
from iambic.core.utils import NoqSemaphore, resource_file_upsert

MANAGED_POLICY_RESPONSE_DIR = pathlib.Path.home().joinpath(
    ".iambic", "resources", "aws", "managed_policies"
)


def get_managed_policy_dir(base_dir: str) -> str:
    return str(os.path.join(base_dir, "resources", "aws", "managed_policies"))


def get_templated_managed_policy_file_path(
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
        policy_name.replace("{{", "")
        .replace("}}_", "_")
        .replace("}}", "_")
        .replace(".", "_")
        .lower()
    )
    return str(os.path.join(managed_policy_dir, separator, f"{file_name}.yaml"))


def get_account_managed_policy_resource_dir(account_id: str) -> str:
    account_resource_dir = os.path.join(MANAGED_POLICY_RESPONSE_DIR, account_id)
    os.makedirs(account_resource_dir, exist_ok=True)
    return account_resource_dir


async def generate_account_managed_policy_resource_files(
    aws_account: AWSAccount,
) -> dict:
    account_resource_dir = get_account_managed_policy_resource_dir(
        aws_account.account_id
    )
    resource_file_upsert_semaphore = NoqSemaphore(resource_file_upsert, 10)
    messages = []

    response = dict(account_id=aws_account.account_id, managed_policies=[])
    iam_client = await aws_account.get_boto3_client("iam")
    account_managed_policies = await list_managed_policies(iam_client)

    log.info(
        "Retrieved AWS IAM Managed Policies.",
        account_id=aws_account.account_id,
        account_name=aws_account.account_name,
        managed_policy_count=len(account_managed_policies),
    )

    for managed_policy in account_managed_policies:
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


async def create_templated_managed_policy(  # noqa: C901
    aws_account_map: dict[str, AWSAccount],
    managed_policy_name: str,
    managed_policy_refs: list[dict],
    managed_policy_dir: str,
    existing_template_map: dict,
    configs: list[Config],
):
    min_accounts_required_for_wildcard_included_accounts = max(
        [
            config.aws.min_accounts_required_for_wildcard_included_accounts
            for config in configs
        ]
    )
    account_id_to_mp_map = {}
    num_of_accounts = len(managed_policy_refs)
    for managed_policy_ref in managed_policy_refs:
        async with aiofiles.open(managed_policy_ref["file_path"], mode="r") as f:
            content_dict = json.loads(await f.read())
            account_id_to_mp_map[
                managed_policy_ref["account_id"]
            ] = normalize_boto3_resp(content_dict)

    # Generate the params used for attribute creation
    managed_policy_properties = {"policy_name": managed_policy_name}

    # TODO: Fix identifier it should be something along the lines of v but path can vary by account
    #       f"arn:aws:iam::{account_id}:policy{resource['Path']}{managed_policy_name}"
    managed_policy_template_params = {"identifier": managed_policy_name}
    path_resources = list()
    description_resources = list()
    policy_document_resources = list()
    tag_resources = list()
    for account_id, managed_policy_dict in account_id_to_mp_map.items():
        path_resources.append(
            {
                "account_id": account_id,
                "resources": [{"resource_val": managed_policy_dict["path"]}],
            }
        )
        policy_document_resources.append(
            {
                "account_id": account_id,
                "resources": [{"resource_val": managed_policy_dict["policy_document"]}],
            }
        )

        if tags := managed_policy_dict.get("tags"):
            tag_resources.append(
                {
                    "account_id": account_id,
                    "resources": [{"resource_val": tag} for tag in tags],
                }
            )

        if description := managed_policy_dict.get("description"):
            description_resources.append(
                {"account_id": account_id, "resources": [{"resource_val": description}]}
            )

    if (
        len(managed_policy_refs) != len(aws_account_map)
        or len(aws_account_map) <= min_accounts_required_for_wildcard_included_accounts
    ):
        managed_policy_template_params["included_accounts"] = [
            aws_account_map[managed_policy_ref["account_id"]].account_name
            for managed_policy_ref in managed_policy_refs
        ]
    else:
        managed_policy_template_params["included_accounts"] = ["*"]

    path = await group_int_or_str_attribute(
        aws_account_map, num_of_accounts, path_resources, "path"
    )
    if path != "/":
        managed_policy_properties["path"] = path

    managed_policy_properties["policy_document"] = await group_dict_attribute(
        aws_account_map, num_of_accounts, policy_document_resources, True
    )

    if description_resources:
        managed_policy_properties["description"] = await group_int_or_str_attribute(
            aws_account_map, num_of_accounts, description_resources, "description"
        )

    if tag_resources:
        tags = await group_dict_attribute(
            aws_account_map, num_of_accounts, tag_resources, True
        )
        if isinstance(tags, dict):
            tags = [tags]
        managed_policy_properties["tags"] = tags

    try:
        managed_policy = ManagedPolicyTemplate(
            file_path=existing_template_map.get(
                managed_policy_name,
                get_templated_managed_policy_file_path(
                    managed_policy_dir,
                    managed_policy_name,
                    managed_policy_template_params.get("included_accounts"),
                    aws_account_map,
                ),
            ),
            properties=managed_policy_properties,
            **managed_policy_template_params,
        )
        managed_policy.write()
    except Exception as err:
        log.info(
            str(err),
            managed_policy_params=managed_policy_template_params,
            managed_policy_properties=managed_policy_properties,
        )


async def generate_aws_managed_policy_templates(
    configs: list[Config], base_output_dir: str
):
    aws_account_map = await get_aws_account_map(configs)
    existing_template_map = await get_existing_template_file_map(
        base_output_dir, "NOQ::IAM::ManagedPolicy"
    )
    resource_dir = get_managed_policy_dir(base_output_dir)
    generate_account_managed_policy_resource_files_semaphore = NoqSemaphore(
        generate_account_managed_policy_resource_files, 25
    )

    log.info("Generating AWS managed policy templates.")
    log.info(
        "Beginning to retrieve AWS IAM Managed Policies.",
        accounts=list(aws_account_map.keys()),
    )

    account_managed_policies = (
        await generate_account_managed_policy_resource_files_semaphore.process(
            [{"aws_account": aws_account} for aws_account in aws_account_map.values()]
        )
    )
    messages = []
    for account in account_managed_policies:
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
            configs,
        )

    log.info("Finished templated managed policy generation")
