from __future__ import annotations

import itertools
import os
import pathlib
from collections import defaultdict
from typing import TYPE_CHECKING

import aiofiles

from iambic.core import noq_json as json
from iambic.core.logger import log
from iambic.core.template_generation import (
    base_group_str_attribute,
    create_or_update_template,
    delete_orphaned_templates,
    get_existing_template_map,
    group_dict_attribute,
    group_int_or_str_attribute,
)
from iambic.core.utils import NoqSemaphore, get_writable_directory, resource_file_upsert
from iambic.plugins.v0_1_0.aws.event_bridge.models import GroupMessageDetails
from iambic.plugins.v0_1_0.aws.iam.group.models import (
    AWS_IAM_GROUP_TEMPLATE_TYPE,
    GroupProperties,
    GroupTemplate,
)
from iambic.plugins.v0_1_0.aws.iam.group.utils import (
    get_group_across_accounts,
    get_group_inline_policies,
    get_group_managed_policies,
    list_groups,
)
from iambic.plugins.v0_1_0.aws.models import AWSAccount
from iambic.plugins.v0_1_0.aws.utils import get_aws_account_map, normalize_boto3_resp

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig


def get_group_response_dir() -> pathlib.Path:
    return get_writable_directory().joinpath(".iambic", "resources", "aws", "groups")


def get_group_dir(base_dir: str) -> str:
    return str(os.path.join(base_dir, "resources", "aws", "groups"))


def get_templated_group_file_path(
    group_dir: str,
    group_name: str,
    included_accounts: list[str],
) -> str:
    if included_accounts is not None and len(included_accounts) > 1:
        separator = "multi_account"
    elif included_accounts == ["*"] or included_accounts is None:
        separator = "all_accounts"
    else:
        separator = included_accounts[0]

    file_name = (
        group_name.replace("{{", "")
        .replace("}}_", "_")
        .replace("}}", "_")
        .replace(".", "_")
        .lower()
    )
    return str(os.path.join(group_dir, separator, f"{file_name}.yaml"))


def get_account_group_resource_dir(account_id: str) -> str:
    account_group_response_dir = os.path.join(get_group_response_dir(), account_id)
    os.makedirs(account_group_response_dir, exist_ok=True)
    return account_group_response_dir


async def generate_account_group_resource_files(aws_account: AWSAccount) -> dict:
    account_group_response_dir = get_account_group_resource_dir(aws_account.account_id)
    group_resource_file_upsert_semaphore = NoqSemaphore(resource_file_upsert, 10)
    messages = []

    response = dict(account_id=aws_account.account_id, groups=[])
    iam_client = await aws_account.get_boto3_client("iam")
    account_groups = await list_groups(iam_client)

    log.info(
        "Retrieved AWS IAM Groups.",
        account_id=aws_account.account_id,
        account_name=aws_account.account_name,
        group_count=len(account_groups),
    )

    for account_group in account_groups:
        group_path = os.path.join(
            account_group_response_dir, f'{account_group["GroupName"]}.json'
        )
        response["groups"].append(
            {
                "path": group_path,
                "name": account_group["GroupName"],
                "account_id": aws_account.account_id,
            }
        )
        messages.append(
            dict(file_path=group_path, content_as_dict=account_group, replace_file=True)
        )

    await group_resource_file_upsert_semaphore.process(messages)
    log.info(
        "Finished caching AWS IAM Groups.",
        account_id=aws_account.account_id,
        group_count=len(account_groups),
    )

    return response


async def generate_group_resource_file_for_all_accounts(
    aws_accounts: list[AWSAccount], group_name: str
) -> list:
    account_group_response_dir_map = {
        aws_account.account_id: get_account_group_resource_dir(aws_account.account_id)
        for aws_account in aws_accounts
    }
    group_resource_file_upsert_semaphore = NoqSemaphore(resource_file_upsert, 10)
    messages = []
    response = []

    group_across_accounts = await get_group_across_accounts(
        aws_accounts, group_name, False
    )
    group_across_accounts = {k: v for k, v in group_across_accounts.items() if v}

    log.info(
        "Retrieved AWS IAM Group for all accounts.",
        group_name=group_name,
        total_accounts=len(group_across_accounts),
    )

    for account_id, account_group in group_across_accounts.items():
        group_path = os.path.join(
            account_group_response_dir_map[account_id],
            f'{account_group["GroupName"]}.json',
        )
        response.append(
            {
                "path": group_path,
                "name": account_group["GroupName"],
                "account_id": account_id,
            }
        )
        messages.append(
            dict(file_path=group_path, content_as_dict=account_group, replace_file=True)
        )

    await group_resource_file_upsert_semaphore.process(messages)
    log.info(
        "Finished caching AWS IAM Group for all accounts.",
        group_name=group_name,
        total_accounts=len(group_across_accounts),
    )

    return response


async def set_group_resource_inline_policies(
    group_name: str, group_resource_path: str, aws_account: AWSAccount
):
    iam_client = await aws_account.get_boto3_client("iam")
    group_inline_policies = await get_group_inline_policies(group_name, iam_client)
    for k in group_inline_policies.keys():
        group_inline_policies[k]["policy_name"] = k

    group_inline_policies = list(group_inline_policies.values())
    await resource_file_upsert(
        group_resource_path, {"InlinePolicies": group_inline_policies}, False
    )


async def set_group_resource_managed_policies(
    group_name: str, group_resource_path: str, aws_account: AWSAccount
):
    iam_client = await aws_account.get_boto3_client("iam")
    group_managed_policies = await get_group_managed_policies(group_name, iam_client)
    await resource_file_upsert(
        group_resource_path, {"ManagedPolicies": group_managed_policies}, False
    )


async def _account_id_to_group_map(group_refs):
    account_id_to_group_map = {}
    for group_ref in group_refs:
        async with aiofiles.open(group_ref["path"], mode="r") as f:
            content_dict = json.loads(await f.read())

            account_id_to_group_map[group_ref["account_id"]] = normalize_boto3_resp(
                content_dict
            )
    return account_id_to_group_map


async def create_templated_group(  # noqa: C901
    aws_account_map: dict[str, AWSAccount],
    group_name: str,
    group_refs: list[dict],
    group_dir: str,
    existing_template_map: dict,
    config: AWSConfig,
) -> GroupTemplate:
    account_id_to_group_map = await _account_id_to_group_map(group_refs)
    num_of_accounts = len(group_refs)

    min_accounts_required_for_wildcard_included_accounts = (
        config.min_accounts_required_for_wildcard_included_accounts
    )

    # Generate the params used for attribute creation
    group_template_params = {"identifier": group_name}
    group_template_properties = {"group_name": group_name}
    path_resources = list()
    managed_policy_resources = list()
    inline_policy_document_resources = list()
    for account_id, group_dict in account_id_to_group_map.items():
        path_resources.append(
            {
                "account_id": account_id,
                "resources": [{"resource_val": group_dict["path"]}],
            }
        )

        if managed_policies := group_dict.get("managed_policies"):
            managed_policy_resources.append(
                {
                    "account_id": account_id,
                    "resources": [{"resource_val": mp} for mp in managed_policies],
                }
            )

        if inline_policies := group_dict.get("inline_policies"):
            # Normalize the inline policy statements to be a list
            for inline_policy in inline_policies:
                if isinstance(inline_policy.get("statement"), dict):
                    inline_policy["statement"] = [inline_policy["statement"]]
            inline_policy_document_resources.append(
                {
                    "account_id": account_id,
                    "resources": [
                        {"resource_val": inline_policy}
                        for inline_policy in inline_policies
                    ],
                }
            )

    if (
        len(group_refs) != len(aws_account_map)
        or len(aws_account_map) <= min_accounts_required_for_wildcard_included_accounts
    ):
        group_template_params["included_accounts"] = [
            aws_account_map[group_ref["account_id"]].account_name
            for group_ref in group_refs
        ]
    else:
        group_template_params["included_accounts"] = ["*"]

    path = await group_int_or_str_attribute(
        aws_account_map, num_of_accounts, path_resources, "path"
    )
    if path != "/":
        group_template_properties["path"] = path

    if managed_policy_resources:
        group_template_properties["managed_policies"] = await group_dict_attribute(
            aws_account_map, num_of_accounts, managed_policy_resources, False
        )

    if inline_policy_document_resources:
        group_template_properties["inline_policies"] = await group_dict_attribute(
            aws_account_map, num_of_accounts, inline_policy_document_resources, False
        )

    file_path = get_templated_group_file_path(
        group_dir,
        group_name,
        group_template_params.get("included_accounts"),
    )
    return create_or_update_template(
        file_path,
        existing_template_map,
        group_name,
        GroupTemplate,
        group_template_params,
        GroupProperties(**group_template_properties),
        list(aws_account_map.values()),
    )


async def generate_aws_group_templates(
    config: AWSConfig,
    base_output_dir: str,
    group_messages: list[GroupMessageDetails] = None,
):
    aws_account_map = await get_aws_account_map(config)
    existing_template_map = await get_existing_template_map(
        base_output_dir, AWS_IAM_GROUP_TEMPLATE_TYPE
    )
    group_dir = get_group_dir(base_output_dir)
    set_group_resource_inline_policies_semaphore = NoqSemaphore(
        set_group_resource_inline_policies, 20
    )
    set_group_resource_managed_policies_semaphore = NoqSemaphore(
        set_group_resource_managed_policies, 30
    )

    log.info("Generating AWS group templates.")
    log.info(
        "Beginning to retrieve AWS IAM Groups.", accounts=list(aws_account_map.keys())
    )

    if group_messages:
        aws_accounts = list(aws_account_map.values())
        generate_group_resource_file_for_all_accounts_semaphore = NoqSemaphore(
            generate_group_resource_file_for_all_accounts, 45
        )
        tasks = [
            {"aws_accounts": aws_accounts, "group_name": group.group_name}
            for group in group_messages
            if not group.delete
        ]

        # Remove deleted or mark templates for update
        deleted_groups = [group for group in group_messages if group.delete]
        if deleted_groups:
            for group in deleted_groups:
                group_account = aws_account_map.get(group.account_id)
                if existing_template := existing_template_map.get(group.group_name):
                    if len(existing_template.included_accounts) == 1 and (
                        existing_template.included_accounts[0]
                        == group_account.account_name
                        or existing_template.included_accounts[0]
                        == group_account.account_id
                    ):
                        # It's the only account for the template so delete it
                        existing_template.delete()
                    else:
                        # There are other accounts for the template so re-eval the template
                        tasks.append(
                            {
                                "aws_accounts": aws_accounts,
                                "group_name": existing_template.properties.group_name,
                            }
                        )

        account_group_list = (
            await generate_group_resource_file_for_all_accounts_semaphore.process(tasks)
        )
        account_group_list = list(itertools.chain.from_iterable(account_group_list))
        account_group_map = defaultdict(list)
        for account_group in account_group_list:
            account_group_map[account_group["account_id"]].append(account_group)
        account_groups = [
            dict(account_id=account_id, groups=groups)
            for account_id, groups in account_group_map.items()
        ]
    else:
        generate_account_group_resource_files_semaphore = NoqSemaphore(
            generate_account_group_resource_files, 5
        )
        account_groups = await generate_account_group_resource_files_semaphore.process(
            [{"aws_account": aws_account} for aws_account in aws_account_map.values()]
        )

    if not any(account_group["groups"] for account_group in account_groups):
        log.info("No groups found in any AWS accounts.")
        return

    messages = []
    # Upsert groups
    for account_group in account_groups:
        for group in account_group["groups"]:
            messages.append(
                {
                    "group_name": group["name"],
                    "group_resource_path": group["path"],
                    "aws_account": aws_account_map[account_group["account_id"]],
                }
            )

    log.info("Setting inline policies in group templates")
    await set_group_resource_inline_policies_semaphore.process(messages)
    log.info("Setting managed policies in group templates")
    await set_group_resource_managed_policies_semaphore.process(messages)
    log.info("Finished retrieving group details")

    # Use these for testing `create_templated_group`
    # account_group_output = json.dumps(account_groups)
    # with open("account_group_output.json", "w") as f:
    #     f.write(account_group_output)
    # with open("account_group_output.json") as f:
    #     account_groups = json.loads(f.read())

    log.info("Grouping groups")
    # Move everything to required structure
    for account_group_elem in range(len(account_groups)):
        for group_elem in range(len(account_groups[account_group_elem]["groups"])):
            group_name = account_groups[account_group_elem]["groups"][group_elem].pop(
                "name"
            )
            account_groups[account_group_elem]["groups"][group_elem][
                "resource_val"
            ] = group_name

        account_groups[account_group_elem]["resources"] = account_groups[
            account_group_elem
        ].pop("groups", [])

    grouped_group_map = await base_group_str_attribute(aws_account_map, account_groups)

    log.info("Writing templated groups")
    all_resource_ids = set()
    for group_name, group_refs in grouped_group_map.items():
        resource_template = await create_templated_group(
            aws_account_map,
            group_name,
            group_refs,
            group_dir,
            existing_template_map,
            config,
        )
        all_resource_ids.add(resource_template.resource_id)

    if not group_messages:
        # NEVER call this if messages are passed in because all_resource_ids will only contain those resources
        delete_orphaned_templates(
            list(existing_template_map.values()), all_resource_ids
        )

    log.info("Finished templated group generation")
