import asyncio
import os
import pathlib

import aiofiles

from iambic.aws.iam.policy.models import ManagedPolicyTemplate
from iambic.aws.iam.policy.utils import list_managed_policies
from iambic.aws.models import AWSAccount
from iambic.aws.sso.permission_set.models import AWSSSOPermissionSetTemplate, AWS_SSO_PERMISSION_SET_TEMPLATE_TYPE
from iambic.aws.sso.permission_set.utils import enrich_permission_set_details
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

SSO_PERMISSION_SET_RESPONSE_DIR = pathlib.Path.home().joinpath(
    ".iambic", "resources", "aws", "sso", "permission_sets"
)


def get_permission_set_dir(base_dir: str) -> str:
    repo_dir = os.path.join(base_dir, "resources", "aws", "sso", "permission_sets")
    os.makedirs(repo_dir, exist_ok=True)
    return str(repo_dir)


def get_templated_permission_set_file_path(
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


def get_account_permission_set_resource_dir(account_id: str) -> str:
    account_resource_dir = os.path.join(SSO_PERMISSION_SET_RESPONSE_DIR, account_id)
    os.makedirs(account_resource_dir, exist_ok=True)
    return account_resource_dir


async def generate_permission_set_resource_file(
    sso_client, account_id: str, instance_arn: str, permission_set: dict
) -> dict:
    permission_set = await enrich_permission_set_details(sso_client, instance_arn, permission_set)
    account_resource_dir = get_account_permission_set_resource_dir(account_id)
    file_path = os.path.join(account_resource_dir, f'{permission_set["Name"]}.json')
    response = dict(account_id=account_id, permission_set=permission_set, file_path=file_path)
    await resource_file_upsert(file_path, permission_set)

    return response


async def create_templated_permission_set(  # noqa: C901
    aws_account_map: dict[str, AWSAccount],
    managed_policy_name: str,
    managed_policy_refs: list[dict],
    managed_policy_dir: str,
    existing_template_map: dict,
):
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

    if len(managed_policy_refs) != len(aws_account_map):
        managed_policy_template_params["included_accounts"] = [
            aws_account_map[managed_policy_ref["account_id"]].account_name
            for managed_policy_ref in managed_policy_refs
        ]

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
                get_templated_permission_set_file_path(
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


async def generate_aws_permission_set_templates(
    configs: list[Config], base_output_dir: str
):
    aws_account_map = await get_aws_account_map(configs)
    existing_template_map = await get_existing_template_file_map(
        base_output_dir, AWS_SSO_PERMISSION_SET_TEMPLATE_TYPE
    )
    resource_dir = get_permission_set_dir(base_output_dir)

    accounts_to_set_sso = []
    for config in configs:
        accounts_to_set_sso.extend([account for account in config.aws_accounts if account.sso_details])

    if not accounts_to_set_sso:
        return

    log.info("Generating AWS SSO Permission Set templates.")
    log.info(
        "Beginning to retrieve AWS IAM SSO Permission Sets.",
        org_accounts=list(aws_account_map.keys()),
    )

    await asyncio.gather(*[account.set_sso_details() for account in accounts_to_set_sso])

    messages = []
    for aws_account in aws_account_map.values():
        if not aws_account.sso_details:
            continue

        instance_arn = aws_account.sso_details.instance_arn
        sso_client = await aws_account.get_boto3_client("sso-admin", region_name=aws_account.sso_details.region)

        for permission_set in aws_account.sso_details.permission_set_map.values():
            messages.append(
                dict(
                    account_id=aws_account.account_id,
                    sso_client=sso_client,
                    instance_arn=instance_arn,
                    permission_set=permission_set,
                )
            )

    log.info(
        "Beginning to enrich AWS IAM SSO Permission Sets.",
        org_accounts=list(aws_account_map.keys()),
        permission_set_count=len(messages),
    )
    generate_permission_set_resource_file_semaphore = NoqSemaphore(generate_permission_set_resource_file, 30)
    all_permission_sets = await generate_permission_set_resource_file_semaphore.process(messages)

    log.info(
        "Finished enriching AWS IAM SSO Permission Sets.",
        org_accounts=list(aws_account_map.keys()),
        permission_set_count=len(messages),
    )
    # Use these for testing `create_templated_permission_set`
    all_permission_sets_output = json.dumps(all_permission_sets)
    with open("all_permission_sets_output.json", "w") as f:
        f.write(all_permission_sets_output)
    # with open("all_permission_sets_output.json") as f:
    #     all_permission_sets = json.loads(f.read())

    log.info("Grouping managed policies")
    # Move everything to required structure
    # for account_mp_elem in range(len(account_managed_policies)):
    #     for mp_elem in range(
    #         len(account_managed_policies[account_mp_elem]["managed_policies"])
    #     ):
    #         policy_name = account_managed_policies[account_mp_elem]["managed_policies"][
    #             mp_elem
    #         ].pop("policy_name")
    #         account_managed_policies[account_mp_elem]["managed_policies"][mp_elem][
    #             "resource_val"
    #         ] = policy_name
    #
    #     account_managed_policies[account_mp_elem][
    #         "resources"
    #     ] = account_managed_policies[account_mp_elem].pop("managed_policies", [])
    #
    # grouped_managed_policy_map = await base_group_str_attribute(
    #     aws_account_map, account_managed_policies
    # )
    #
    # log.info("Writing templated roles")
    # for policy_name, policy_refs in grouped_managed_policy_map.items():
    #     await create_templated_permission_set(
    #         aws_account_map,
    #         policy_name,
    #         policy_refs,
    #         resource_dir,
    #         existing_template_map,
    #     )

    log.info("Finished templated managed policy generation")
