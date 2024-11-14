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
from iambic.plugins.v0_1_0.aws.event_bridge.models import RoleMessageDetails
from iambic.plugins.v0_1_0.aws.iam.policy.models import AssumeRolePolicyDocument
from iambic.plugins.v0_1_0.aws.iam.role.models import (
    AWS_IAM_ROLE_TEMPLATE_TYPE,
    AwsIamRoleTemplate,
    RoleProperties,
)
from iambic.plugins.v0_1_0.aws.iam.role.utils import (
    get_role,
    get_role_inline_policies,
    get_role_managed_policies,
    list_role_tags,
    list_roles,
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

RESOURCE_DIR = ["iam", "role"]


def get_response_dir(exe_message: ExecutionMessage, aws_account: AWSAccount) -> str:
    if exe_message.provider_id:
        return exe_message.get_directory(*RESOURCE_DIR)
    else:
        return exe_message.get_directory(aws_account.account_id, *RESOURCE_DIR)


def get_template_dir(base_dir: str) -> str:
    return str(os.path.join(base_dir, "resources", "aws", *RESOURCE_DIR))


def get_templated_role_file_path(
    role_dir: str,
    role_name: str,
    included_accounts: list[str],
    role_path: str = None,
) -> str:
    if included_accounts is not None and len(included_accounts) > 1:
        separator = "multi_account"
    elif included_accounts == ["*"] or included_accounts is None:
        separator = "all_accounts"
    else:
        separator = included_accounts[0]

    file_name = (
        role_name.replace(" ", "")
        .replace("{{var.", "")
        .replace("{{", "")
        .replace("}}_", "_")
        .replace("}}", "_")
        .replace(".", "_")
        .lower()
    )

    # stitch desired location together
    os_paths = [role_dir, separator]
    # using path components from path attribute
    if role_path and "{{" not in role_path:
        role_path_components = role_path.split("/")
        # get rid of empty component
        role_path_components = [
            component for component in role_path_components if component
        ]
        os_paths.extend(role_path_components)
    os_paths.append(f"{file_name}.yaml")

    return str(os.path.join(*os_paths))


async def generate_account_role_resource_files(
    exe_message: ExecutionMessage,
    aws_account: AWSAccount,
) -> dict:
    account_resource_dir = get_response_dir(exe_message, aws_account)
    role_resource_file_upsert_semaphore = NoqSemaphore(resource_file_upsert, 10)
    messages = []

    response = dict(account_id=aws_account.account_id, roles=[])
    iam_client = await aws_account.get_boto3_client("iam")
    account_roles = await list_roles(iam_client)

    log.debug(
        "Retrieved AWS IAM Roles.",
        account_id=aws_account.account_id,
        account_name=aws_account.account_name,
        role_count=len(account_roles),
    )

    for account_role in account_roles:
        role_path = os.path.join(
            account_resource_dir, f'{account_role["RoleName"]}.json'
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
    log.debug(
        "Finished caching AWS IAM Roles.",
        account_id=aws_account.account_id,
        role_count=len(account_roles),
    )

    return response


async def generate_role_resource_file_for_all_accounts(
    exe_message: ExecutionMessage,
    role_name: str,
    aws_account_map: dict[str, AWSAccount],
    updated_account_ids: list[str],
    iambic_template: Optional[AwsIamRoleTemplate],
) -> list:
    async def get_role_for_account(aws_account: AWSAccount):
        iam_client = await aws_account.get_boto3_client("iam")
        account_role_name = get_rendered_template_str_value(role_name, aws_account)
        role = await get_role(account_role_name, iam_client)
        if "PermissionsBoundary" in role:
            role["PermissionsBoundary"]["PolicyArn"] = role["PermissionsBoundary"].pop(
                "PermissionsBoundaryArn"
            )
        return {aws_account.account_id: role}

    account_resource_dir_map = {
        aws_account.account_id: get_response_dir(exe_message, aws_account)
        for aws_account in aws_account_map.values()
    }
    role_resource_file_upsert_semaphore = NoqSemaphore(resource_file_upsert, 10)
    messages = []
    response = []

    role_across_accounts = generate_template_output(
        updated_account_ids, aws_account_map, iambic_template
    )
    updated_account_roles = await asyncio.gather(
        *[
            get_role_for_account(aws_account_map[account_id])
            for account_id in updated_account_ids
        ]
    )
    for updated_account_role in updated_account_roles:
        role_across_accounts.update(updated_account_role)
    role_across_accounts = {k: v for k, v in role_across_accounts.items() if v}

    log.debug(
        "Retrieved AWS IAM Role for all accounts.",
        role_name=role_name,
        total_accounts=len(role_across_accounts),
    )

    for account_id, account_role in role_across_accounts.items():
        role_path = os.path.join(
            account_resource_dir_map[account_id],
            f'{account_role["RoleName"]}.json',
        )
        response.append(
            {
                "path": role_path,
                "name": account_role["RoleName"],
                "account_id": account_id,
            }
        )
        messages.append(
            dict(file_path=role_path, content_as_dict=account_role, replace_file=True)
        )

    await role_resource_file_upsert_semaphore.process(messages)
    log.debug(
        "Finished caching AWS IAM Role for all accounts.",
        role_name=role_name,
        total_accounts=len(role_across_accounts),
    )

    return response


async def set_role_resource_tags(
    role_name: str, role_resource_path: str, aws_account: AWSAccount
):
    iam_client = await aws_account.get_boto3_client("iam")
    role_tags = await list_role_tags(role_name, iam_client)
    await resource_file_upsert(role_resource_path, {"Tags": role_tags}, False)


async def set_role_resource_inline_policies(
    role_name: str, role_resource_path: str, aws_account: AWSAccount
):
    iam_client = await aws_account.get_boto3_client("iam")
    role_inline_policies = await get_role_inline_policies(role_name, iam_client)
    for k in role_inline_policies.keys():
        role_inline_policies[k]["policy_name"] = k

    role_inline_policies = list(role_inline_policies.values())
    await resource_file_upsert(
        role_resource_path, {"InlinePolicies": role_inline_policies}, False
    )


async def set_role_resource_managed_policies(
    role_name: str, role_resource_path: str, aws_account: AWSAccount
):
    iam_client = await aws_account.get_boto3_client("iam")
    role_managed_policies = await get_role_managed_policies(role_name, iam_client)
    await resource_file_upsert(
        role_resource_path, {"ManagedPolicies": role_managed_policies}, False
    )


async def _account_id_to_role_map(role_refs):
    account_id_to_role_map = {}
    for role_ref in role_refs:
        async with aiofiles.open(role_ref["path"], mode="r") as f:
            content_dict = json.loads(await f.read())

            # handle strange unstable response with deleted principals
            assume_role_policy_document = content_dict.get(
                "AssumeRolePolicyDocument", None
            )
            if assume_role_policy_document:
                policy_document = AssumeRolePolicyDocument.parse_obj(
                    normalize_dict_keys(assume_role_policy_document)
                )
                content_dict["AssumeRolePolicyDocument"] = json.loads(
                    policy_document.json(
                        exclude_unset=True, exclude_defaults=True, exclude_none=True
                    )
                )

            account_id_to_role_map[role_ref["account_id"]] = normalize_dict_keys(
                content_dict
            )
    return account_id_to_role_map


async def create_templated_role(  # noqa: C901
    aws_account_map: dict[str, AWSAccount],
    role_name: str,
    role_refs: list[dict],
    role_dir: str,
    existing_template_map: dict,
    config: AWSConfig,
) -> Optional[AwsIamRoleTemplate]:
    account_id_to_role_map = await _account_id_to_role_map(role_refs)
    num_of_accounts = len(role_refs)
    import_actions = set()

    min_accounts_required_for_wildcard_included_accounts = (
        config.min_accounts_required_for_wildcard_included_accounts
    )

    # calculate preference based on existing template
    prefer_templatized = calculate_import_preference(
        existing_template_map.get(role_name)
    )

    # Generate the params used for attribute creation
    role_template_params = {"identifier": role_name}
    role_template_properties = {"role_name": role_name}
    path_resources = list()
    description_resources = list()
    managed_policy_resources = list()
    assume_role_policy_document_resources = list()
    inline_policy_document_resources = list()
    permissions_boundary_resources = list()
    tag_resources = list()
    max_session_duration_resources = dict()
    for account_id, role_dict in account_id_to_role_map.items():
        import_actions.update(
            await process_import_rules(
                config,
                AWS_IAM_ROLE_TEMPLATE_TYPE,
                role_name,
                role_dict.get("tags", []),
                role_dict,
            )
        )

        max_session_duration_resources[account_id] = role_dict["max_session_duration"]
        path_resources.append(
            {
                "account_id": account_id,
                "resources": [{"resource_val": role_dict["path"]}],
            }
        )
        assume_role_policy_document_resources.append(
            {
                "account_id": account_id,
                "resources": [
                    {"resource_val": role_dict["assume_role_policy_document"]}
                ],
            }
        )

        if managed_policies := role_dict.get("managed_policies"):
            managed_policy_resources.append(
                {
                    "account_id": account_id,
                    "resources": [{"resource_val": mp} for mp in managed_policies],
                }
            )

        if permissions_boundary := role_dict.get("permissions_boundary"):
            permissions_boundary_resources.append(
                {
                    "account_id": account_id,
                    "resources": [{"resource_val": permissions_boundary}],
                }
            )

        if inline_policies := role_dict.get("inline_policies"):
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

        if tags := role_dict.get("tags"):
            tag_resources.append(
                {
                    "account_id": account_id,
                    "resources": [{"resource_val": tag} for tag in tags],
                }
            )

        if description := role_dict.get("description"):
            description_resources.append(
                {"account_id": account_id, "resources": [{"resource_val": description}]}
            )
    for action in import_actions:
        if action.value == "set_import_only":
            role_template_params["iambic_managed"] = "import_only"
        if action.value == "ignore":
            return None
    if (
        len(role_refs) != len(aws_account_map)
        or len(aws_account_map) <= min_accounts_required_for_wildcard_included_accounts
    ):
        role_template_params["included_accounts"] = [
            aws_account_map[role_ref["account_id"]].account_name
            for role_ref in role_refs
        ]
    else:
        role_template_params["included_accounts"] = ["*"]

    path = await group_int_or_str_attribute(
        aws_account_map, num_of_accounts, path_resources, "path"
    )
    if path != "/":
        role_template_properties["path"] = path

    max_session_duration = await group_int_or_str_attribute(
        aws_account_map,
        num_of_accounts,
        max_session_duration_resources,
        "max_session_duration",
    )
    if max_session_duration != 3600:
        role_template_properties["max_session_duration"] = max_session_duration

    if assume_role_policy_document_resources:
        role_template_properties[
            "assume_role_policy_document"
        ] = await group_dict_attribute(
            aws_account_map,
            num_of_accounts,
            assume_role_policy_document_resources,
            prefer_templatized=prefer_templatized,
        )

    if permissions_boundary_resources:
        role_template_properties["permissions_boundary"] = await group_dict_attribute(
            aws_account_map,
            num_of_accounts,
            permissions_boundary_resources,
            prefer_templatized=prefer_templatized,
        )

    if description_resources:
        role_template_properties["description"] = await group_int_or_str_attribute(
            aws_account_map, num_of_accounts, description_resources, "description"
        )

    if managed_policy_resources:
        role_template_properties["managed_policies"] = await group_dict_attribute(
            aws_account_map,
            num_of_accounts,
            managed_policy_resources,
            False,
            prefer_templatized=prefer_templatized,
        )

    if inline_policy_document_resources:
        role_template_properties["inline_policies"] = await group_dict_attribute(
            aws_account_map,
            num_of_accounts,
            inline_policy_document_resources,
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

        role_template_properties["tags"] = tags

    file_path = get_templated_role_file_path(
        role_dir,
        role_name,
        role_template_params.get("included_accounts"),
        role_path=path if isinstance(path, str) else None,
    )
    try:
        return create_or_update_template(
            file_path,
            existing_template_map,
            role_name,
            AwsIamRoleTemplate,
            role_template_params,
            RoleProperties(**role_template_properties),
            list(aws_account_map.values()),
        )
    except Exception as e:
        log_params = {
            "role_name": role_name,
            "role_template_params": role_template_params,
        }
        log.error(
            "Not able to create_or_update_template",
            **log_params,
        )
        raise e


async def collect_aws_roles(
    exe_message: ExecutionMessage,
    config: AWSConfig,
    iam_template_map: dict,
    detect_messages: list[RoleMessageDetails] = None,
):
    aws_account_map = await get_aws_account_map(config)
    if exe_message.provider_id:
        aws_account_map = {
            exe_message.provider_id: aws_account_map[exe_message.provider_id]
        }

    existing_template_map = iam_template_map.get(AWS_IAM_ROLE_TEMPLATE_TYPE, {})
    set_role_resource_inline_policies_semaphore = NoqSemaphore(
        set_role_resource_inline_policies, 20
    )
    set_role_resource_managed_policies_semaphore = NoqSemaphore(
        set_role_resource_managed_policies, 30
    )
    set_role_resource_tags_semaphore = NoqSemaphore(set_role_resource_tags, 45)

    log.info(
        "Generating AWS role templates. Beginning to retrieve AWS IAM Roles.",
        accounts=list(aws_account_map.keys()),
    )

    if detect_messages:
        generate_role_resource_file_for_all_accounts_semaphore = NoqSemaphore(
            generate_role_resource_file_for_all_accounts, 45
        )
        grouped_detect_messages = group_detect_messages("role_name", detect_messages)
        tasks = [
            {
                "exe_message": exe_message,
                "aws_account_map": aws_account_map,
                "role_name": role_name,
                "updated_account_ids": [
                    message.account_id for message in role_messages
                ],
                "iambic_template": existing_template_map.get(role_name),
            }
            for role_name, role_messages in grouped_detect_messages.items()
        ]

        # Remove deleted or mark templates for update
        deleted_roles = [role for role in detect_messages if role.delete]
        if deleted_roles:
            for role in deleted_roles:
                role_account = aws_account_map.get(role.account_id)
                if existing_template := existing_template_map.get(role.role_name):
                    if len(existing_template.included_accounts) == 1 and (
                        existing_template.included_accounts[0]
                        == role_account.account_name
                        or existing_template.included_accounts[0]
                        == role_account.account_id
                    ):
                        # It's the only account for the template so delete it
                        existing_template.delete()

        account_role_list = (
            await generate_role_resource_file_for_all_accounts_semaphore.process(tasks)
        )
        account_role_list = list(itertools.chain.from_iterable(account_role_list))
        account_role_map = defaultdict(list)
        for account_role in account_role_list:
            account_role_map[account_role["account_id"]].append(account_role)
        account_roles = [
            dict(account_id=account_id, roles=roles)
            for account_id, roles in account_role_map.items()
        ]
    elif exe_message.provider_id:
        aws_account = aws_account_map[exe_message.provider_id]
        account_roles = [
            (await generate_account_role_resource_files(exe_message, aws_account))
        ]
    else:
        generate_account_role_resource_files_semaphore = NoqSemaphore(
            generate_account_role_resource_files, 5
        )
        account_roles = await generate_account_role_resource_files_semaphore.process(
            [
                {"aws_account": aws_account, "exe_message": exe_message}
                for aws_account in aws_account_map.values()
            ]
        )

    messages = []
    # Upsert roles
    for account_role in account_roles:
        for role in account_role["roles"]:
            messages.append(
                {
                    "role_name": role["name"],
                    "role_resource_path": role["path"],
                    "aws_account": aws_account_map[account_role["account_id"]],
                }
            )

    if not detect_messages:
        log.info(
            "Setting inline policies in role templates",
            accounts=list(aws_account_map.keys()),
        )
        await set_role_resource_inline_policies_semaphore.process(messages)
        log.info(
            "Setting managed policies in role templates",
            accounts=list(aws_account_map.keys()),
        )
        await set_role_resource_managed_policies_semaphore.process(messages)
        log.info(
            "Setting tags in role templates", accounts=list(aws_account_map.keys())
        )
        await set_role_resource_tags_semaphore.process(messages)
        log.info(
            "Finished retrieving role details", accounts=list(aws_account_map.keys())
        )

    account_role_output = json.dumps(account_roles)
    with open(
        exe_message.get_file_path(*RESOURCE_DIR, file_name_and_extension="output.json"),
        "w",
    ) as f:
        f.write(account_role_output)


async def generate_aws_role_templates(
    exe_message: ExecutionMessage,
    config: AWSConfig,
    base_output_dir: str,
    iam_template_map: dict,
    detect_messages: list[RoleMessageDetails] = None,
):
    role_dir = get_template_dir(base_output_dir)
    aws_account_map = await get_aws_account_map(config)
    existing_template_map = iam_template_map.get(AWS_IAM_ROLE_TEMPLATE_TYPE, {})
    account_roles = await exe_message.get_sub_exe_files(
        *RESOURCE_DIR, file_name_and_extension="output.json", flatten_results=True
    )

    if detect_messages:
        detect_messages = [
            msg for msg in detect_messages if isinstance(msg, RoleMessageDetails)
        ]
        if not detect_messages:
            return

    log.info("Grouping roles")
    # Move everything to required structure
    for account_role_elem in range(len(account_roles)):
        for role_elem in range(len(account_roles[account_role_elem]["roles"])):
            role_name = account_roles[account_role_elem]["roles"][role_elem].pop("name")
            account_roles[account_role_elem]["roles"][role_elem][
                "resource_val"
            ] = role_name

        account_roles[account_role_elem]["resources"] = account_roles[
            account_role_elem
        ].pop("roles", [])

    grouped_role_map = await base_group_str_attribute(aws_account_map, account_roles)

    log.info("Writing templated roles")
    all_resource_ids = set()
    for role_name, role_refs in grouped_role_map.items():
        resource_template = await create_templated_role(
            aws_account_map,
            role_name,
            role_refs,
            role_dir,
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

    log.info("Finished templated role generation")
