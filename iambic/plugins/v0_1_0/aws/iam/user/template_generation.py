from __future__ import annotations

import itertools
import os
from collections import defaultdict
from typing import TYPE_CHECKING

import aiofiles

from iambic.core import noq_json as json
from iambic.core.logger import log
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import (
    create_or_update_template,
    delete_orphaned_templates,
)
from iambic.core.utils import NoqSemaphore, normalize_dict_keys, resource_file_upsert
from iambic.plugins.v0_1_0.aws.event_bridge.models import UserMessageDetails
from iambic.plugins.v0_1_0.aws.iam.user.models import (
    AWS_IAM_USER_TEMPLATE_TYPE,
    AwsIamUserTemplate,
    UserProperties,
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
from iambic.plugins.v0_1_0.aws.template_generation import (
    base_group_str_attribute,
    group_dict_attribute,
    group_int_or_str_attribute,
)
from iambic.plugins.v0_1_0.aws.utils import (
    calculate_import_preference,
    get_aws_account_map,
)

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig

RESOURCE_DIR = ["iam", "user"]


def get_response_dir(exe_message: ExecutionMessage, aws_account: AWSAccount) -> str:
    if exe_message.provider_id:
        return exe_message.get_directory(*RESOURCE_DIR)
    else:
        return exe_message.get_directory(aws_account.account_id, *RESOURCE_DIR)


def get_template_dir(base_dir: str) -> str:
    return str(os.path.join(base_dir, "resources", "aws", *RESOURCE_DIR))


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
        user_name.replace(" ", "")
        .replace("{{var.", "")
        .replace("{{", "")
        .replace("}}_", "_")
        .replace("}}", "_")
        .replace(".", "_")
        .lower()
    )
    return str(os.path.join(user_dir, separator, f"{file_name}.yaml"))


async def generate_account_user_resource_files(
    exe_message: ExecutionMessage,
    aws_account: AWSAccount,
) -> dict:
    account_resource_dir = get_response_dir(exe_message, aws_account)
    user_resource_file_upsert_semaphore = NoqSemaphore(resource_file_upsert, 10)
    messages = []

    response = dict(account_id=aws_account.account_id, users=[])
    iam_client = await aws_account.get_boto3_client("iam")
    account_users = await list_users(iam_client)

    log.debug(
        "Retrieved AWS IAM Users.",
        account_id=aws_account.account_id,
        account_name=aws_account.account_name,
        user_count=len(account_users),
    )

    for account_user in account_users:
        user_path = os.path.join(
            account_resource_dir, f'{account_user["UserName"]}.json'
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
    log.debug(
        "Finished caching AWS IAM Users.",
        account_id=aws_account.account_id,
        user_count=len(account_users),
    )

    return response


async def generate_user_resource_file_for_all_accounts(
    exe_message: ExecutionMessage, aws_accounts: list[AWSAccount], user_name: str
) -> list:
    account_resource_dir_map = {
        aws_account.account_id: get_response_dir(exe_message, aws_account)
        for aws_account in aws_accounts
    }
    user_resource_file_upsert_semaphore = NoqSemaphore(resource_file_upsert, 10)
    messages = []
    response = []

    user_across_accounts = await get_user_across_accounts(
        aws_accounts, user_name, False
    )
    user_across_accounts = {k: v for k, v in user_across_accounts.items() if v}

    log.debug(
        "Retrieved AWS IAM User for all accounts.",
        user_name=user_name,
        total_accounts=len(user_across_accounts),
    )

    for account_id, account_user in user_across_accounts.items():
        user_path = os.path.join(
            account_resource_dir_map[account_id],
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
    log.debug(
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
            account_id_to_user_map[user_ref["account_id"]] = normalize_dict_keys(
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
) -> AwsIamUserTemplate:
    account_id_to_user_map = await _account_id_to_user_map(user_refs)
    num_of_accounts = len(user_refs)

    min_accounts_required_for_wildcard_included_accounts = (
        config.min_accounts_required_for_wildcard_included_accounts
    )

    # calculate preference based on existing template
    prefer_templatized = calculate_import_preference(
        existing_template_map.get(user_name)
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
            aws_account_map,
            num_of_accounts,
            permissions_boundary_resources,
            prefer_templatized=prefer_templatized,
        )

    if description_resources:
        user_template_properties["description"] = await group_int_or_str_attribute(
            aws_account_map, num_of_accounts, description_resources, "description"
        )

    if managed_policy_resources:
        user_template_properties["managed_policies"] = await group_dict_attribute(
            aws_account_map,
            num_of_accounts,
            managed_policy_resources,
            False,
            prefer_templatized=prefer_templatized,
        )

    if inline_policy_document_resources:
        user_template_properties["inline_policies"] = await group_dict_attribute(
            aws_account_map,
            num_of_accounts,
            inline_policy_document_resources,
            False,
            prefer_templatized=prefer_templatized,
        )

    if group_resources:
        user_template_properties["groups"] = await group_dict_attribute(
            aws_account_map,
            num_of_accounts,
            group_resources,
            False,
            prefer_templatized=prefer_templatized,
        )
    if tag_resources:
        tags = await group_dict_attribute(
            aws_account_map,
            num_of_accounts,
            tag_resources,
            True,
            prefer_templatized=prefer_templatized,
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
        AwsIamUserTemplate,
        user_template_params,
        UserProperties(**user_template_properties),
        list(aws_account_map.values()),
    )


async def collect_aws_users(
    exe_message: ExecutionMessage,
    config: AWSConfig,
    iam_template_map: dict,
    detect_messages: list[UserMessageDetails] = None,
):
    aws_account_map = await get_aws_account_map(config)
    if exe_message.provider_id:
        aws_account_map = {
            exe_message.provider_id: aws_account_map[exe_message.provider_id]
        }

    existing_template_map = iam_template_map.get(AWS_IAM_USER_TEMPLATE_TYPE, {})
    set_user_resource_inline_policies_semaphore = NoqSemaphore(
        set_user_resource_inline_policies, 20
    )
    set_user_resource_managed_policies_semaphore = NoqSemaphore(
        set_user_resource_managed_policies, 30
    )

    set_user_resource_groups_semaphore = NoqSemaphore(set_user_resource_groups, 25)
    set_user_resource_tags_semaphore = NoqSemaphore(set_user_resource_tags, 30)

    log.info(
        "Generating AWS user templates. Beginning to retrieve AWS IAM Users.",
        accounts=list(aws_account_map.keys()),
    )

    if detect_messages:
        aws_accounts = list(aws_account_map.values())
        generate_user_resource_file_for_all_accounts_semaphore = NoqSemaphore(
            generate_user_resource_file_for_all_accounts, 50
        )
        tasks = [
            {
                "exe_message": exe_message,
                "aws_accounts": aws_accounts,
                "user_name": user.user_name,
            }
            for user in detect_messages
            if not user.delete
        ]

        # Remove deleted or mark templates for update
        deleted_users = [user for user in detect_messages if user.delete]
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
                                "exe_message": exe_message,
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
    elif exe_message.provider_id:
        aws_account = aws_account_map[exe_message.provider_id]
        account_users = [
            (await generate_account_user_resource_files(exe_message, aws_account))
        ]
    else:
        generate_account_user_resource_files_semaphore = NoqSemaphore(
            generate_account_user_resource_files, 5
        )
        account_users = await generate_account_user_resource_files_semaphore.process(
            [
                {"exe_message": exe_message, "aws_account": aws_account}
                for aws_account in aws_account_map.values()
            ]
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

    log.info(
        "Setting inline policies in user templates",
        accounts=list(aws_account_map.keys()),
    )
    await set_user_resource_inline_policies_semaphore.process(messages)
    log.info(
        "Setting managed policies in user templates",
        accounts=list(aws_account_map.keys()),
    )
    await set_user_resource_managed_policies_semaphore.process(messages)
    log.info("Setting groups in user templates", accounts=list(aws_account_map.keys()))
    await set_user_resource_groups_semaphore.process(messages)
    log.info("Setting tags in user templates", accounts=list(aws_account_map.keys()))
    await set_user_resource_tags_semaphore.process(messages)
    log.info("Finished retrieving user details", accounts=list(aws_account_map.keys()))

    account_user_output = json.dumps(account_users)
    with open(
        exe_message.get_file_path(*RESOURCE_DIR, file_name_and_extension="output.json"),
        "w",
    ) as f:
        f.write(account_user_output)


async def generate_aws_user_templates(
    exe_message: ExecutionMessage,
    config: AWSConfig,
    base_output_dir: str,
    iam_template_map: dict,
    detect_messages: list[UserMessageDetails] = None,
):
    aws_account_map = await get_aws_account_map(config)

    if detect_messages:
        detect_messages = [
            msg for msg in detect_messages if isinstance(msg, UserMessageDetails)
        ]
        if not detect_messages:
            return

    existing_template_map = iam_template_map.get(AWS_IAM_USER_TEMPLATE_TYPE, {})
    user_dir = get_template_dir(base_output_dir)
    account_users = await exe_message.get_sub_exe_files(
        *RESOURCE_DIR, file_name_and_extension="output.json", flatten_results=True
    )

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

    log.debug("Writing templated users")
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
        if not resource_template:
            # Template not updated. Most likely because it's an `enforced` template.
            continue
        all_resource_ids.add(resource_template.resource_id)

    if not detect_messages:
        # NEVER call this if messages are passed in because all_resource_ids will only contain those resources
        delete_orphaned_templates(
            list(existing_template_map.values()), all_resource_ids
        )

    log.info("Finished templated user generation")
