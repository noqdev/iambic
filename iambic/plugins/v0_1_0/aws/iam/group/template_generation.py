from __future__ import annotations

import asyncio
import itertools
import os
from collections import defaultdict
from typing import TYPE_CHECKING, Optional

import aiofiles

from iambic.core import noq_json as json
from iambic.core.detect import generate_template_output, group_detect_messages
from iambic.core.logger import log
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import (
    create_or_update_template,
    delete_orphaned_templates,
)
from iambic.core.utils import (
    NoqSemaphore,
    get_rendered_template_str_value,
    normalize_dict_keys,
    resource_file_upsert,
)
from iambic.plugins.v0_1_0.aws.event_bridge.models import GroupMessageDetails
from iambic.plugins.v0_1_0.aws.iam.group.models import (
    AWS_IAM_GROUP_TEMPLATE_TYPE,
    AwsIamGroupTemplate,
    GroupProperties,
)
from iambic.plugins.v0_1_0.aws.iam.group.utils import (
    get_group,
    get_group_inline_policies,
    get_group_managed_policies,
    list_groups,
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
    process_import_rules,
)

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig

RESOURCE_DIR = ["iam", "group"]


def get_response_dir(exe_message: ExecutionMessage, aws_account: AWSAccount) -> str:
    if exe_message.provider_id:
        return exe_message.get_directory(*RESOURCE_DIR)
    else:
        return exe_message.get_directory(aws_account.account_id, *RESOURCE_DIR)


def get_template_dir(base_dir: str) -> str:
    return str(os.path.join(base_dir, "resources", "aws", *RESOURCE_DIR))


def get_templated_group_file_path(
    group_dir: str,
    group_name: str,
    included_accounts: list[str],
    group_path: str = None,
) -> str:
    if included_accounts is not None and len(included_accounts) > 1:
        separator = "multi_account"
    elif included_accounts == ["*"] or included_accounts is None:
        separator = "all_accounts"
    else:
        separator = included_accounts[0]

    file_name = (
        group_name.replace(" ", "")
        .replace("{{var.", "")
        .replace("{{", "")
        .replace("}}_", "_")
        .replace("}}", "_")
        .replace(".", "_")
        .lower()
    )

    # stitch desired location together
    os_paths = [group_dir, separator]
    # using path components from path attribute
    if group_path and "{{" not in group_path:
        group_path_components = group_path.split("/")
        # get rid of empty component
        group_path_components = [
            component for component in group_path_components if component
        ]
        os_paths.extend(group_path_components)
    os_paths.append(f"{file_name}.yaml")

    return str(os.path.join(*os_paths))


async def generate_account_group_resource_files(
    exe_message: ExecutionMessage,
    aws_account: AWSAccount,
) -> dict:
    account_group_response_dir = get_response_dir(exe_message, aws_account)
    group_resource_file_upsert_semaphore = NoqSemaphore(resource_file_upsert, 10)
    messages = []

    response = dict(account_id=aws_account.account_id, groups=[])
    iam_client = await aws_account.get_boto3_client("iam")
    account_groups = await list_groups(iam_client)

    log.debug(
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
    log.debug(
        "Finished caching AWS IAM Groups.",
        account_id=aws_account.account_id,
        group_count=len(account_groups),
    )

    return response


async def generate_group_resource_file_for_all_accounts(
    exe_message: ExecutionMessage,
    group_name: str,
    aws_account_map: dict[str, AWSAccount],
    updated_account_ids: list[str],
    iambic_template: Optional[AwsIamGroupTemplate],
) -> list:
    async def get_group_for_account(aws_account: AWSAccount):
        iam_client = await aws_account.get_boto3_client("iam")
        account_group_name = get_rendered_template_str_value(group_name, aws_account)
        return {aws_account.account_id: await get_group(account_group_name, iam_client)}

    account_group_response_dir_map = {
        aws_account.account_id: get_response_dir(exe_message, aws_account)
        for aws_account in aws_account_map.values()
    }
    group_resource_file_upsert_semaphore = NoqSemaphore(resource_file_upsert, 10)
    messages = []
    response = []

    group_across_accounts = generate_template_output(
        updated_account_ids, aws_account_map, iambic_template
    )
    updated_account_groups = await asyncio.gather(
        *[
            get_group_for_account(aws_account_map[account_id])
            for account_id in updated_account_ids
        ]
    )
    for updated_account_group in updated_account_groups:
        group_across_accounts.update(updated_account_group)
    group_across_accounts = {k: v for k, v in group_across_accounts.items() if v}

    log.debug(
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
    log.debug(
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

            account_id_to_group_map[group_ref["account_id"]] = normalize_dict_keys(
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
) -> Optional[AwsIamGroupTemplate]:
    account_id_to_group_map = await _account_id_to_group_map(group_refs)
    num_of_accounts = len(group_refs)

    min_accounts_required_for_wildcard_included_accounts = (
        config.min_accounts_required_for_wildcard_included_accounts
    )

    # calculate preference based on existing template
    prefer_templatized = calculate_import_preference(
        existing_template_map.get(group_name)
    )

    # Generate the params used for attribute creation
    group_template_params = {"identifier": group_name}
    group_template_properties = {"group_name": group_name}
    path_resources = list()
    managed_policy_resources = list()
    inline_policy_document_resources = list()
    import_actions = set()
    for account_id, group_dict in account_id_to_group_map.items():
        import_actions.update(
            await process_import_rules(
                config,
                AWS_IAM_GROUP_TEMPLATE_TYPE,
                group_name,
                group_dict.get("tags", []),
                group_dict,
            )
        )
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

    for action in import_actions:
        if action.value == "set_import_only":
            group_template_params["iambic_managed"] = "import_only"
        if action.value == "ignore":
            return None

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
            aws_account_map,
            num_of_accounts,
            managed_policy_resources,
            False,
            prefer_templatized=prefer_templatized,
        )

    if inline_policy_document_resources:
        group_template_properties["inline_policies"] = await group_dict_attribute(
            aws_account_map,
            num_of_accounts,
            inline_policy_document_resources,
            False,
            prefer_templatized=prefer_templatized,
        )

    file_path = get_templated_group_file_path(
        group_dir,
        group_name,
        group_template_params.get("included_accounts"),
        group_path=path if isinstance(path, str) else None,
    )
    return create_or_update_template(
        file_path,
        existing_template_map,
        group_name,
        AwsIamGroupTemplate,
        group_template_params,
        GroupProperties(**group_template_properties),
        [aws_account_map[group_ref["account_id"]] for group_ref in group_refs],
    )


async def collect_aws_groups(
    exe_message: ExecutionMessage,
    config: AWSConfig,
    iam_template_map: dict,
    detect_messages: list[GroupMessageDetails] = None,
):
    aws_account_map = await get_aws_account_map(config)
    if exe_message.provider_id:
        aws_account_map = {
            exe_message.provider_id: aws_account_map[exe_message.provider_id]
        }

    if detect_messages:
        detect_messages = [
            msg for msg in detect_messages if isinstance(msg, GroupMessageDetails)
        ]
        if not detect_messages:
            return

    existing_template_map = iam_template_map.get(AWS_IAM_GROUP_TEMPLATE_TYPE, {})
    set_group_resource_inline_policies_semaphore = NoqSemaphore(
        set_group_resource_inline_policies, 20
    )
    set_group_resource_managed_policies_semaphore = NoqSemaphore(
        set_group_resource_managed_policies, 30
    )

    log.info(
        "Generating AWS group templates. Beginning to retrieve AWS IAM Groups.",
        accounts=list(aws_account_map.keys()),
    )

    if detect_messages:
        generate_group_resource_file_for_all_accounts_semaphore = NoqSemaphore(
            generate_group_resource_file_for_all_accounts, 45
        )
        grouped_detect_messages = group_detect_messages("group_name", detect_messages)
        tasks = [
            {
                "exe_message": exe_message,
                "aws_account_map": aws_account_map,
                "group_name": group_name,
                "updated_account_ids": [
                    message.account_id for message in group_messages
                ],
                "iambic_template": existing_template_map.get(group_name),
            }
            for group_name, group_messages in grouped_detect_messages.items()
        ]

        # Remove deleted or mark templates for update
        deleted_groups = [group for group in detect_messages if group.delete]
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
    elif exe_message.provider_id:
        aws_account = aws_account_map[exe_message.provider_id]
        account_groups = [
            (await generate_account_group_resource_files(exe_message, aws_account))
        ]
    else:
        generate_account_group_resource_files_semaphore = NoqSemaphore(
            generate_account_group_resource_files, 5
        )
        account_groups = await generate_account_group_resource_files_semaphore.process(
            [
                {"exe_message": exe_message, "aws_account": aws_account}
                for aws_account in aws_account_map.values()
            ]
        )

    if not any(account_group["groups"] for account_group in account_groups):
        log.info(
            "No groups found in any AWS accounts.",
            accounts=list(aws_account_map.keys()),
        )
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

    if not detect_messages:
        log.info(
            "Setting inline policies in group templates",
            accounts=list(aws_account_map.keys()),
        )
        await set_group_resource_inline_policies_semaphore.process(messages)
        log.info(
            "Setting managed policies in group templates",
            accounts=list(aws_account_map.keys()),
        )
        await set_group_resource_managed_policies_semaphore.process(messages)
        log.info(
            "Finished retrieving group details", accounts=list(aws_account_map.keys())
        )

    account_group_output = json.dumps(account_groups)
    with open(
        exe_message.get_file_path(*RESOURCE_DIR, file_name_and_extension="output.json"),
        "w",
    ) as f:
        f.write(account_group_output)


async def generate_aws_group_templates(
    exe_message: ExecutionMessage,
    config: AWSConfig,
    base_output_dir: str,
    iam_template_map: dict,
    detect_messages: list[GroupMessageDetails] = None,
):
    aws_account_map = await get_aws_account_map(config)
    existing_template_map = iam_template_map.get(AWS_IAM_GROUP_TEMPLATE_TYPE, {})
    group_dir = get_template_dir(base_output_dir)
    account_groups = await exe_message.get_sub_exe_files(
        *RESOURCE_DIR, file_name_and_extension="output.json", flatten_results=True
    )

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

    log.debug("Writing templated groups")
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
        if not resource_template:
            # Template not updated. Most likely because it's an `enforced` template.
            continue
        all_resource_ids.add(resource_template.resource_id)

    if not detect_messages:
        # NEVER call this if messages are passed in because all_resource_ids will only contain those resources
        delete_orphaned_templates(
            list(existing_template_map.values()), all_resource_ids
        )

    log.info("Finished templated group generation")
