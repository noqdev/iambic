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
from iambic.plugins.v0_1_0.aws.event_bridge.models import ManagedPolicyMessageDetails
from iambic.plugins.v0_1_0.aws.iam.policy.models import (
    AWS_MANAGED_POLICY_TEMPLATE_TYPE,
    AwsIamManagedPolicyTemplate,
    ManagedPolicyProperties,
)
from iambic.plugins.v0_1_0.aws.iam.policy.utils import (
    get_managed_policy_across_accounts,
    list_managed_policies,
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

RESOURCE_DIR = ["iam", "managed_policy"]


def get_response_dir(exe_message: ExecutionMessage, aws_account: AWSAccount) -> str:
    if exe_message.provider_id:
        return exe_message.get_directory(*RESOURCE_DIR)
    else:
        return exe_message.get_directory(aws_account.account_id, *RESOURCE_DIR)


def get_template_dir(base_dir: str) -> str:
    return str(os.path.join(base_dir, "resources", "aws", *RESOURCE_DIR))


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
        policy_name.replace(" ", "")
        .replace("{{var.", "")
        .replace("{{", "")
        .replace("}}_", "_")
        .replace("}}", "_")
        .replace(".", "_")
        .lower()
    )
    return str(os.path.join(managed_policy_dir, separator, f"{file_name}.yaml"))


async def generate_account_managed_policy_resource_files(
    exe_message: ExecutionMessage,
    aws_account: AWSAccount,
) -> dict:
    account_resource_dir = get_response_dir(exe_message, aws_account)
    resource_file_upsert_semaphore = NoqSemaphore(resource_file_upsert, 10)
    messages = []

    response = dict(account_id=aws_account.account_id, managed_policies=[])
    iam_client = await aws_account.get_boto3_client("iam")
    account_managed_policies = await list_managed_policies(iam_client)

    log.debug(
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
    log.debug(
        "Finished caching AWS IAM Managed Policies.",
        account_id=aws_account.account_id,
        managed_policy_count=len(account_managed_policies),
    )

    return response


async def generate_managed_policy_resource_file_for_all_accounts(
    exe_message: ExecutionMessage,
    aws_accounts: list[AWSAccount],
    policy_path: str,
    policy_name: str,
) -> list:
    account_resource_dir_map = {
        aws_account.account_id: get_response_dir(exe_message, aws_account)
        for aws_account in aws_accounts
    }
    mp_resource_file_upsert_semaphore = NoqSemaphore(resource_file_upsert, 10)
    messages = []
    response = []

    mp_across_accounts = await get_managed_policy_across_accounts(
        aws_accounts, policy_path, policy_name
    )
    mp_across_accounts = {k: v for k, v in mp_across_accounts.items() if v}

    log.debug(
        "Retrieved AWS IAM Managed Policy for all accounts.",
        policy_name=policy_name,
        policy_path=policy_path,
        total_accounts=len(mp_across_accounts),
    )

    for account_id, managed_policy in mp_across_accounts.items():
        policy_path = os.path.join(
            account_resource_dir_map[account_id],
            f'{managed_policy["PolicyName"]}.json',
        )

        response.append(
            {
                "file_path": policy_path,
                "policy_name": managed_policy["PolicyName"],
                "arn": managed_policy["Arn"],
                "account_id": account_id,
            }
        )
        messages.append(
            dict(
                file_path=policy_path, content_as_dict=managed_policy, replace_file=True
            )
        )

    await mp_resource_file_upsert_semaphore.process(messages)
    log.debug(
        "Finished caching AWS IAM Managed Policy for all accounts.",
        policy_name=policy_name,
        policy_path=policy_path,
        total_accounts=len(mp_across_accounts),
    )

    return response


async def create_templated_managed_policy(  # noqa: C901
    aws_account_map: dict[str, AWSAccount],
    managed_policy_name: str,
    managed_policy_refs: list[dict],
    managed_policy_dir: str,
    existing_template_map: dict,
    config: AWSConfig,
):
    min_accounts_required_for_wildcard_included_accounts = (
        config.min_accounts_required_for_wildcard_included_accounts
    )
    account_id_to_mp_map = {}
    num_of_accounts = len(managed_policy_refs)
    for managed_policy_ref in managed_policy_refs:
        async with aiofiles.open(managed_policy_ref["file_path"], mode="r") as f:
            content_dict = json.loads(await f.read())
            account_id_to_mp_map[
                managed_policy_ref["account_id"]
            ] = normalize_dict_keys(content_dict)

    # calculate preference based on existing template
    prefer_templatized = calculate_import_preference(
        existing_template_map.get(managed_policy_name)
    )

    # Generate the params used for attribute creation
    template_properties = {"policy_name": managed_policy_name}

    # TODO: Fix identifier it should be something along the lines of v but path can vary by account
    #       f"arn:aws:iam::{account_id}:policy{resource['Path']}{managed_policy_name}"
    template_params = {"identifier": managed_policy_name}
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
        template_params["included_accounts"] = [
            aws_account_map[managed_policy_ref["account_id"]].account_name
            for managed_policy_ref in managed_policy_refs
        ]
    else:
        template_params["included_accounts"] = ["*"]

    path = await group_int_or_str_attribute(
        aws_account_map, num_of_accounts, path_resources, "path"
    )
    if path != "/":
        template_properties["path"] = path

    template_properties["policy_document"] = await group_dict_attribute(
        aws_account_map,
        num_of_accounts,
        policy_document_resources,
        True,
        prefer_templatized=prefer_templatized,
    )

    if description_resources:
        template_properties["description"] = await group_int_or_str_attribute(
            aws_account_map, num_of_accounts, description_resources, "description"
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
        template_properties["tags"] = tags

    file_path = get_templated_managed_policy_file_path(
        managed_policy_dir,
        managed_policy_name,
        template_params.get("included_accounts"),
        aws_account_map,
    )
    return create_or_update_template(
        file_path,
        existing_template_map,
        managed_policy_name,
        AwsIamManagedPolicyTemplate,
        template_params,
        ManagedPolicyProperties(**template_properties),
        list(aws_account_map.values()),
    )


async def collect_aws_managed_policies(
    exe_message: ExecutionMessage,
    config: AWSConfig,
    iam_template_map: dict,
    detect_messages: list[ManagedPolicyMessageDetails] = None,
):
    aws_account_map = await get_aws_account_map(config)
    if exe_message.provider_id:
        aws_account_map = {
            exe_message.provider_id: aws_account_map[exe_message.provider_id]
        }

    if detect_messages:
        detect_messages = [
            msg
            for msg in detect_messages
            if isinstance(msg, ManagedPolicyMessageDetails)
        ]
        if not detect_messages:
            return

    existing_template_map = iam_template_map.get(AWS_MANAGED_POLICY_TEMPLATE_TYPE, {})

    log.info(
        "Generating AWS managed policy templates. Beginning to retrieve AWS IAM Managed Policies.",
        accounts=list(aws_account_map.keys()),
    )

    if detect_messages:
        aws_accounts = list(aws_account_map.values())
        generate_mp_resource_file_for_all_accounts_semaphore = NoqSemaphore(
            generate_managed_policy_resource_file_for_all_accounts, 50
        )

        tasks = [
            {
                "exe_message": exe_message,
                "aws_accounts": aws_accounts,
                "policy_path": managed_policy.policy_path,
                "policy_name": managed_policy.policy_name,
            }
            for managed_policy in detect_messages
            if not managed_policy.delete
        ]

        # Remove deleted or mark templates for update
        deleted_managed_policies = [
            managed_policy
            for managed_policy in detect_messages
            if managed_policy.delete
        ]
        if deleted_managed_policies:
            for managed_policy in deleted_managed_policies:
                policy_account = aws_account_map.get(managed_policy.account_id)
                if existing_template := existing_template_map.get(
                    managed_policy.policy_name
                ):
                    if len(existing_template.included_accounts) == 1 and (
                        existing_template.included_accounts[0]
                        == policy_account.account_name
                        or existing_template.included_accounts[0]
                        == policy_account.account_id
                    ):
                        # It's the only account for the template so delete it
                        existing_template.delete()
                    else:
                        # There are other accounts for the template so re-eval the template
                        tasks.append(
                            {
                                "exe_message": exe_message,
                                "aws_accounts": aws_accounts,
                                "policy_path": existing_template.properties.path,
                                "policy_name": existing_template.properties.policy_name,
                            }
                        )

        account_mp_list = (
            await generate_mp_resource_file_for_all_accounts_semaphore.process(tasks)
        )
        account_mp_list = list(itertools.chain.from_iterable(account_mp_list))
        account_policy_map = defaultdict(list)
        for account_policy in account_mp_list:
            account_policy_map[account_policy["account_id"]].append(account_policy)
        account_managed_policies = [
            dict(account_id=account_id, managed_policies=account_managed_policies)
            for account_id, account_managed_policies in account_policy_map.items()
        ]
    elif exe_message.provider_id:
        aws_account = aws_account_map[exe_message.provider_id]
        account_managed_policies = [
            (
                await generate_account_managed_policy_resource_files(
                    exe_message, aws_account
                )
            )
        ]
    else:
        generate_account_managed_policy_resource_files_semaphore = NoqSemaphore(
            generate_account_managed_policy_resource_files, 25
        )
        account_managed_policies = (
            await generate_account_managed_policy_resource_files_semaphore.process(
                [
                    {"exe_message": exe_message, "aws_account": aws_account}
                    for aws_account in aws_account_map.values()
                ]
            )
        )

    # Upsert Managed Policies
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

    log.info(
        "Finished retrieving managed policy details",
        accounts=list(aws_account_map.keys()),
    )

    account_managed_policy_output = json.dumps(account_managed_policies)
    with open(
        exe_message.get_file_path(*RESOURCE_DIR, file_name_and_extension="output.json"),
        "w",
    ) as f:
        f.write(account_managed_policy_output)


async def generate_aws_managed_policy_templates(
    exe_message: ExecutionMessage,
    config: AWSConfig,
    base_output_dir: str,
    iam_template_map: dict,
    detect_messages: list[ManagedPolicyMessageDetails] = None,
):
    aws_account_map = await get_aws_account_map(config)
    existing_template_map = iam_template_map.get(AWS_MANAGED_POLICY_TEMPLATE_TYPE, {})
    resource_dir = get_template_dir(base_output_dir)
    account_managed_policies = await exe_message.get_sub_exe_files(
        *RESOURCE_DIR, file_name_and_extension="output.json", flatten_results=True
    )

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

    log.debug("Writing templated managed policies")
    all_resource_ids = set()
    for policy_name, policy_refs in grouped_managed_policy_map.items():
        resource_template = await create_templated_managed_policy(
            aws_account_map,
            policy_name,
            policy_refs,
            resource_dir,
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

    log.info("Finished templated managed policy generation")
