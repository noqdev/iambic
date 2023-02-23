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
from iambic.plugins.v0_1_0.aws.event_bridge.models import UserMessageDetails
from iambic.plugins.v0_1_0.aws.iam.user.models import (
    AWS_IAM_USER_TEMPLATE_TYPE,
    UserProperties,
    UserTemplate,
)
from iambic.plugins.v0_1_0.aws.iam.user.utils import (
    get_user_across_accounts,
    get_user_groups,
    get_user_inline_policies,
    get_user_managed_policies,
    list_user_tags,
    list_users,
)
from iambic.plugins.v0_1_0.aws.models import AWSAccount
from iambic.plugins.v0_1_0.aws.utils import get_aws_account_map, normalize_boto3_resp

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig


def get_user_response_dir() -> pathlib.Path:
    return get_writable_directory().joinpath(".iambic", "resources", "aws", "users")


def get_user_dir(base_dir: str) -> str:
    return str(os.path.join(base_dir, "resources", "aws", "users"))


def get_templated_user_file_path(
    user_dir: str,
    user_name: str,
    included_accounts: list[str],
) -> str:
    if included_accounts is not None and len(included_accounts) > 1:
        separator = "multi_account"
    elif included_accounts == ["*"] or included_accounts is None:
        separator = "all_accounts"
    else:
        separator = included_accounts[0]

    file_name = (
        user_name.replace("{{", "")
        .replace("}}_", "_")
        .replace("}}", "_")
        .replace(".", "_")
        .lower()
    )
    return str(os.path.join(user_dir, separator, f"{file_name}.yaml"))


def get_account_user_resource_dir(account_id: str) -> str:
    account_user_response_dir = os.path.join(get_user_response_dir(), account_id)
    os.makedirs(account_user_response_dir, exist_ok=True)
    return account_user_response_dir


async def generate_account_user_resource_files(aws_account: AWSAccount) -> dict:
    account_user_response_dir = get_account_user_resource_dir(aws_account.account_id)
    user_resource_file_upsert_semaphore = NoqSemaphore(resource_file_upsert, 10)
    messages = []

    response = dict(account_id=aws_account.account_id, users=[])
    iam_client = await aws_account.get_boto3_client("iam")
    account_users = await list_users(iam_client)

    log.info(
        "Retrieved AWS IAM Users.",
        account_id=aws_account.account_id,
        account_name=aws_account.account_name,
        user_count=len(account_users),
    )

    for account_user in account_users:
        user_path = os.path.join(
            account_user_response_dir, f'{account_user["UserName"]}.json'
        )
        response["users"].append(
            {
                "path": user_path,
                "name": account_user["UserName"],
                "account_id": aws_account.account_id,
            }
        )
        messages.append(
            dict(file_path=user_path, content_as_dict=account_user, replace_file=True)
        )

    await user_resource_file_upsert_semaphore.process(messages)
    log.info(
        "Finished caching AWS IAM Users.",
        account_id=aws_account.account_id,
        user_count=len(account_users),
    )

    return response


async def generate_user_resource_file_for_all_accounts(
    aws_accounts: list[AWSAccount], user_name: str
) -> list:
    account_user_response_dir_map = {
        aws_account.account_id: get_account_user_resource_dir(aws_account.account_id)
        for aws_account in aws_accounts
    }
    user_resource_file_upsert_semaphore = NoqSemaphore(resource_file_upsert, 10)
    messages = []
    response = []

    user_across_accounts = await get_user_across_accounts(
        aws_accounts, user_name, False
    )
    user_across_accounts = {k: v for k, v in user_across_accounts.items() if v}

    log.info(
        "Retrieved AWS IAM User for all accounts.",
        user_name=user_name,
        total_accounts=len(user_across_accounts),
    )

    for account_id, account_user in user_across_accounts.items():
        user_path = os.path.join(
            account_user_response_dir_map[account_id],
            f'{account_user["UserName"]}.json',
        )
        response.append(
            {
                "path": user_path,
                "name": account_user["UserName"],
                "account_id": account_id,
            }
        )
        messages.append(
            dict(file_path=user_path, content_as_dict=account_user, replace_file=True)
        )

    await user_resource_file_upsert_semaphore.process(messages)
    log.info(
        "Finished caching AWS IAM User for all accounts.",
        user_name=user_name,
        total_accounts=len(user_across_accounts),
    )

    return response


async def set_user_resource_tags(
    user_name: str, user_resource_path: str, aws_account: AWSAccount
):
    iam_client = await aws_account.get_boto3_client("iam")
    user_tags = await list_user_tags(user_name, iam_client)
    await resource_file_upsert(user_resource_path, {"Tags": user_tags}, False)


async def set_user_resource_inline_policies(
    user_name: str, user_resource_path: str, aws_account: AWSAccount
):
    iam_client = await aws_account.get_boto3_client("iam")
    user_inline_policies = await get_user_inline_policies(user_name, iam_client)
    for k in user_inline_policies.keys():
        user_inline_policies[k]["policy_name"] = k

    user_inline_policies = list(user_inline_policies.values())
    await resource_file_upsert(
        user_resource_path, {"InlinePolicies": user_inline_policies}, False
    )


async def set_user_resource_managed_policies(
    user_name: str, user_resource_path: str, aws_account: AWSAccount
):
    iam_client = await aws_account.get_boto3_client("iam")
    user_managed_policies = await get_user_managed_policies(user_name, iam_client)
    await resource_file_upsert(
        user_resource_path, {"ManagedPolicies": user_managed_policies}, False
    )


async def set_user_resource_groups(
    user_name: str, user_resource_path: str, aws_account: AWSAccount
):
    iam_client = await aws_account.get_boto3_client("iam")
    user_groups = await get_user_groups(user_name, iam_client)
    await resource_file_upsert(user_resource_path, {"Groups": user_groups}, False)


async def _account_id_to_user_map(user_refs):
    account_id_to_user_map = {}
    for user_ref in user_refs:
        async with aiofiles.open(user_ref["path"], mode="r") as f:
            content_dict = json.loads(await f.read())
            account_id_to_user_map[user_ref["account_id"]] = normalize_boto3_resp(
                content_dict
            )
    return account_id_to_user_map


async def create_templated_user(  # noqa: C901
    aws_account_map: dict[str, AWSAccount],
    user_name: str,
    user_refs: list[dict],
    user_dir: str,
    existing_template_map: dict,
    config: AWSConfig,
) -> UserTemplate:
    account_id_to_user_map = await _account_id_to_user_map(user_refs)
    num_of_accounts = len(user_refs)

    min_accounts_required_for_wildcard_included_accounts = (
        config.min_accounts_required_for_wildcard_included_accounts
    )

    # Generate the params used for attribute creation
    user_template_params = {"identifier": user_name}
    user_template_properties = {"user_name": user_name}
    path_resources = list()
    description_resources = list()
    managed_policy_resources = list()
    inline_policy_document_resources = list()
    permissions_boundary_resources = list()
    group_resources = list()
    tag_resources = list()
    for account_id, user_dict in account_id_to_user_map.items():
        path_resources.append(
            {
                "account_id": account_id,
                "resources": [{"resource_val": user_dict["path"]}],
            }
        )

        if managed_policies := user_dict.get("managed_policies"):
            managed_policy_resources.append(
                {
                    "account_id": account_id,
                    "resources": [{"resource_val": mp} for mp in managed_policies],
                }
            )

        if groups := user_dict.get("groups"):
            group_resources.append(
                {
                    "account_id": account_id,
                    "resources": [{"resource_val": v} for _, v in groups.items()],
                }
            )

        if permissions_boundary := user_dict.get("permissions_boundary"):
            permissions_boundary_resources.append(
                {
                    "account_id": account_id,
                    "resources": [{"resource_val": permissions_boundary}],
                }
            )

        if inline_policies := user_dict.get("inline_policies"):
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

        if tags := user_dict.get("tags"):
            tag_resources.append(
                {
                    "account_id": account_id,
                    "resources": [{"resource_val": tag} for tag in tags],
                }
            )

        if description := user_dict.get("description"):
            description_resources.append(
                {"account_id": account_id, "resources": [{"resource_val": description}]}
            )

    if (
        len(user_refs) != len(aws_account_map)
        or len(aws_account_map) <= min_accounts_required_for_wildcard_included_accounts
    ):
        user_template_params["included_accounts"] = [
            aws_account_map[user_ref["account_id"]].account_name
            for user_ref in user_refs
        ]
    else:
        user_template_params["included_accounts"] = ["*"]

    path = await group_int_or_str_attribute(
        aws_account_map, num_of_accounts, path_resources, "path"
    )
    if path != "/":
        user_template_properties["path"] = path

    if permissions_boundary_resources:
        user_template_properties["permissions_boundary"] = await group_dict_attribute(
            aws_account_map, num_of_accounts, permissions_boundary_resources
        )

    if description_resources:
        user_template_properties["description"] = await group_int_or_str_attribute(
            aws_account_map, num_of_accounts, description_resources, "description"
        )

    if managed_policy_resources:
        user_template_properties["managed_policies"] = await group_dict_attribute(
            aws_account_map, num_of_accounts, managed_policy_resources, False
        )

    if inline_policy_document_resources:
        user_template_properties["inline_policies"] = await group_dict_attribute(
            aws_account_map, num_of_accounts, inline_policy_document_resources, False
        )

    if group_resources:
        user_template_properties["groups"] = await group_dict_attribute(
            aws_account_map, num_of_accounts, group_resources, False
        )
    if tag_resources:
        tags = await group_dict_attribute(
            aws_account_map, num_of_accounts, tag_resources, True
        )
        if isinstance(tags, dict):
            tags = [tags]

        user_template_properties["tags"] = tags

    file_path = get_templated_user_file_path(
        user_dir,
        user_name,
        user_template_params.get("included_accounts"),
    )
    return create_or_update_template(
        file_path,
        existing_template_map,
        user_name,
        UserTemplate,
        user_template_params,
        UserProperties(**user_template_properties),
        list(aws_account_map.values()),
    )


async def generate_aws_user_templates(
    config: AWSConfig,
    base_output_dir: str,
    user_messages: list[UserMessageDetails] = None,
):
    aws_account_map = await get_aws_account_map(config)
    existing_template_map = await get_existing_template_map(
        base_output_dir, AWS_IAM_USER_TEMPLATE_TYPE
    )
    user_dir = get_user_dir(base_output_dir)
    set_user_resource_inline_policies_semaphore = NoqSemaphore(
        set_user_resource_inline_policies, 20
    )
    set_user_resource_managed_policies_semaphore = NoqSemaphore(
        set_user_resource_managed_policies, 30
    )

    set_user_resource_groups_semaphore = NoqSemaphore(set_user_resource_groups, 30)
    set_user_resource_tags_semaphore = NoqSemaphore(set_user_resource_tags, 50)

    log.info("Generating AWS user templates.")
    log.info(
        "Beginning to retrieve AWS IAM Users.", accounts=list(aws_account_map.keys())
    )

    if user_messages:
        aws_accounts = list(aws_account_map.values())
        generate_user_resource_file_for_all_accounts_semaphore = NoqSemaphore(
            generate_user_resource_file_for_all_accounts, 50
        )
        tasks = [
            {"aws_accounts": aws_accounts, "user_name": user.user_name}
            for user in user_messages
            if not user.delete
        ]

        # Remove deleted or mark templates for update
        deleted_users = [user for user in user_messages if user.delete]
        if deleted_users:
            for user in deleted_users:
                user_account = aws_account_map.get(user.account_id)
                if existing_template := existing_template_map.get(user.user_name):
                    if len(existing_template.included_accounts) == 1 and (
                        existing_template.included_accounts[0]
                        == user_account.account_name
                        or existing_template.included_accounts[0]
                        == user_account.account_id
                    ):
                        # It's the only account for the template so delete it
                        existing_template.delete()
                    else:
                        # There are other accounts for the template so re-eval the template
                        tasks.append(
                            {
                                "aws_accounts": aws_accounts,
                                "user_name": existing_template.properties.user_name,
                            }
                        )

        account_user_list = (
            await generate_user_resource_file_for_all_accounts_semaphore.process(tasks)
        )
        account_user_list = list(itertools.chain.from_iterable(account_user_list))
        account_user_map = defaultdict(list)
        for account_user in account_user_list:
            account_user_map[account_user["account_id"]].append(account_user)
        account_users = [
            dict(account_id=account_id, users=users)
            for account_id, users in account_user_map.items()
        ]
    else:
        generate_account_user_resource_files_semaphore = NoqSemaphore(
            generate_account_user_resource_files, 5
        )
        account_users = await generate_account_user_resource_files_semaphore.process(
            [{"aws_account": aws_account} for aws_account in aws_account_map.values()]
        )

    messages = []
    # Upsert users
    for account_user in account_users:
        for user in account_user["users"]:
            messages.append(
                {
                    "user_name": user["name"],
                    "user_resource_path": user["path"],
                    "aws_account": aws_account_map[account_user["account_id"]],
                }
            )

    log.info("Setting inline policies in user templates")
    await set_user_resource_inline_policies_semaphore.process(messages)
    log.info("Setting managed policies in user templates")
    await set_user_resource_managed_policies_semaphore.process(messages)
    log.info("Setting groups in user templates")
    await set_user_resource_groups_semaphore.process(messages)
    log.info("Setting tags in user templates")
    await set_user_resource_tags_semaphore.process(messages)
    log.info("Finished retrieving user details")

    # Use these for testing `create_templated_user`
    # account_user_output = json.dumps(account_users)
    # with open("account_user_output.json", "w") as f:
    #     f.write(account_user_output)
    # with open("account_user_output.json") as f:
    #     account_users = json.loads(f.read())

    log.info("Grouping users")
    # Move everything to required structure
    for account_user_elem in range(len(account_users)):
        for user_elem in range(len(account_users[account_user_elem]["users"])):
            user_name = account_users[account_user_elem]["users"][user_elem].pop("name")
            account_users[account_user_elem]["users"][user_elem][
                "resource_val"
            ] = user_name

        account_users[account_user_elem]["resources"] = account_users[
            account_user_elem
        ].pop("users", [])

    grouped_user_map = await base_group_str_attribute(aws_account_map, account_users)

    log.info("Writing templated users")
    all_resource_ids = set()
    for user_name, user_refs in grouped_user_map.items():
        resource_template = await create_templated_user(
            aws_account_map,
            user_name,
            user_refs,
            user_dir,
            existing_template_map,
            config,
        )
        all_resource_ids.add(resource_template.resource_id)

    if not user_messages:
        # NEVER call this if messages are passed in because all_resource_ids will only contain those resources
        delete_orphaned_templates(
            list(existing_template_map.values()), all_resource_ids
        )

    log.info("Finished templated user generation")
