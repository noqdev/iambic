import os
import pathlib

import aiofiles

from iambic.aws.iam.role.models import RoleTemplate
from iambic.aws.iam.role.utils import (
    get_role_inline_policies,
    get_role_managed_policies,
    list_role_tags,
    list_roles,
)
from iambic.config.models import AccountConfig, Config
from iambic.core import noq_json as json
from iambic.core.logger import log
from iambic.core.template_generation import (
    base_group_dict_attribute,
    base_group_str_attribute,
    group_dict_attribute,
    group_int_or_str_attribute,
    set_included_accounts_for_grouped_attribute,
)
from iambic.core.utils import (
    NoqSemaphore,
    get_account_config_map,
    normalize_boto3_resp,
    resource_file_upsert,
)

ROLE_RESPONSE_DIR = pathlib.Path.home().joinpath(
    ".noqform", "resources", "aws", "roles"
)


def get_role_dir(base_dir: str) -> str:
    repo_dir = os.path.join(base_dir, "resources", "aws", "roles")
    os.makedirs(repo_dir, exist_ok=True)
    return str(repo_dir)


def get_templated_role_file_path(role_dir: str, role_name: str):
    file_name = (
        role_name.replace("{{", "")
        .replace("}}_", "_")
        .replace("}}", "_")
        .replace(".", "_")
        .lower()
    )
    return str(os.path.join(role_dir, f"{file_name}.yaml"))


def get_account_role_resource_dir(account_id: str) -> str:
    account_role_response_dir = os.path.join(ROLE_RESPONSE_DIR, account_id)
    os.makedirs(account_role_response_dir, exist_ok=True)
    return account_role_response_dir


async def generate_account_role_resource_files(account_config: AccountConfig) -> dict:
    account_role_response_dir = get_account_role_resource_dir(account_config.account_id)
    role_resource_file_upsert_semaphore = NoqSemaphore(resource_file_upsert, 10)
    messages = []

    response = dict(account_id=account_config.account_id, roles=[])
    iam_client = account_config.get_boto3_client("iam")
    account_roles = await list_roles(iam_client)

    log.info(
        "Retrieved AWS IAM Roles.",
        account_id=account_config.account_id,
        account_name=account_config.account_name,
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
                "account_id": account_config.account_id,
            }
        )
        messages.append(
            dict(file_path=role_path, content_as_dict=account_role, replace_file=True)
        )

    await role_resource_file_upsert_semaphore.process(messages)
    log.info(
        "Finished caching AWS IAM Roles.",
        account_id=account_config.account_id,
        role_count=len(account_roles),
    )

    return response


async def set_role_resource_tags(
    role_name: str, role_resource_path: str, account_config: AccountConfig
):
    iam_client = account_config.get_boto3_client("iam")
    role_tags = await list_role_tags(role_name, iam_client)
    await resource_file_upsert(role_resource_path, {"Tags": role_tags}, False)


async def set_role_resource_inline_policies(
    role_name: str, role_resource_path: str, account_config: AccountConfig
):
    iam_client = account_config.get_boto3_client("iam")
    role_inline_policies = await get_role_inline_policies(role_name, iam_client)
    for k in role_inline_policies.keys():
        role_inline_policies[k]["policy_name"] = k

    role_inline_policies = list(role_inline_policies.values())
    await resource_file_upsert(
        role_resource_path, {"InlinePolicies": role_inline_policies}, False
    )


async def set_role_resource_managed_policies(
    role_name: str, role_resource_path: str, account_config: AccountConfig
):
    iam_client = account_config.get_boto3_client("iam")
    role_managed_policies = await get_role_managed_policies(role_name, iam_client)
    await resource_file_upsert(
        role_resource_path, {"ManagedPolicies": role_managed_policies}, False
    )


async def create_templated_role(  # noqa: C901
    global_config: Config,
    account_config_map: dict[str, AccountConfig],
    role_name: str,
    role_refs: list[dict],
    role_dir: str,
):
    account_id_to_role_map = {}
    num_of_accounts = len(role_refs)
    for role_ref in role_refs:
        async with aiofiles.open(role_ref["path"], mode="r") as f:
            content_dict = json.loads(await f.read())
            account_id_to_role_map[role_ref["account_id"]] = normalize_boto3_resp(
                content_dict
            )

    # Generate the params used for attribute creation
    role_template_params = {"role_name": role_name}
    path_resources = list()
    description_resources = list()
    managed_policy_resources = list()
    assume_role_policy_document_resources = list()
    inline_policy_document_resources = list()
    permissions_boundary_resources = list()
    tag_resources = list()
    max_session_duration_resources = dict()
    for account_id, role_dict in account_id_to_role_map.items():
        path_resources.append(
            {
                "account_id": account_id,
                "resources": [{"resource_val": role_dict["path"]}],
            }
        )
        managed_policy_resources.append(
            {
                "account_id": account_id,
                "resources": [
                    {"resource_val": mp} for mp in role_dict.get("managed_policies", [])
                ],
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

        if permissions_boundary := role_dict.get("permissions_boundary"):
            permissions_boundary_resources.append(
                {
                    "account_id": account_id,
                    "resources": [{"resource_val": permissions_boundary}],
                }
            )

        max_session_duration_resources[account_id] = role_dict["max_session_duration"]

        if inline_policies := role_dict.get("inline_policies"):
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

    if len(role_refs) != len(account_config_map):
        role_template_params["included_accounts"] = [
            account_config_map[role_ref["account_id"]].account_name
            for role_ref in role_refs
        ]

    path = await group_int_or_str_attribute(
        account_config_map, num_of_accounts, path_resources, "path"
    )
    if path != "/":
        role_template_params["path"] = path

    max_session_duration = await group_int_or_str_attribute(
        account_config_map,
        num_of_accounts,
        max_session_duration_resources,
        "max_session_duration",
    )
    if max_session_duration != 3600:
        role_template_params["max_session_duration"] = max_session_duration

    if assume_role_policy_document_resources:
        role_template_params[
            "assume_role_policy_document"
        ] = await group_dict_attribute(
            account_config_map, num_of_accounts, assume_role_policy_document_resources
        )

    if permissions_boundary_resources:
        role_template_params["permissions_boundary"] = await group_dict_attribute(
            account_config_map, num_of_accounts, permissions_boundary_resources
        )

    if description_resources:
        role_template_params["description"] = await group_int_or_str_attribute(
            account_config_map, num_of_accounts, description_resources, "description"
        )

    if managed_policy_resources:
        role_template_params["managed_policies"] = await group_dict_attribute(
            account_config_map, num_of_accounts, managed_policy_resources, False
        )

    if inline_policy_document_resources:
        role_template_params["inline_policies"] = await group_dict_attribute(
            account_config_map, num_of_accounts, inline_policy_document_resources, False
        )

    if tag_resources:
        tags = []
        role_access = []
        tag_lists = await base_group_dict_attribute(account_config_map, tag_resources)
        for tag_val in tag_lists:
            included_accounts = tag_val["included_accounts"]
            tag = tag_val["resource_val"]
            if tag["key"] == global_config.role_access_tag and tag["value"]:
                role_access.append(
                    {
                        "included_accounts": included_accounts,
                        "groups": tag["value"].split(":"),
                    }
                )
            elif tag["value"]:
                tags.append({"included_accounts": included_accounts, **tag})

        if tags:
            role_template_params[
                "tags"
            ] = await set_included_accounts_for_grouped_attribute(
                account_config_map, num_of_accounts, tags
            )
            for elem in range(len(role_template_params["tags"])):
                if role_template_params["tags"][elem]["included_accounts"] == ["*"]:
                    role_template_params["tags"][elem].pop("included_accounts")

        if role_access:
            role_template_params[
                "role_access"
            ] = await set_included_accounts_for_grouped_attribute(
                account_config_map, num_of_accounts, role_access
            )
            for elem in range(len(role_template_params["role_access"])):
                if role_template_params["role_access"][elem]["included_accounts"] == [
                    "*"
                ]:
                    role_template_params["role_access"][elem].pop("included_accounts")

    try:
        role = RoleTemplate(
            file_path=get_templated_role_file_path(role_dir, role_name),
            **role_template_params,
        )
        role.write()
    except Exception as err:
        log.info(str(err), role_params=role_template_params)


async def generate_aws_role_templates(configs: list[Config], base_output_dir: str):
    account_config_map = get_account_config_map(configs)
    generate_account_role_resource_files_semaphore = NoqSemaphore(
        generate_account_role_resource_files, 5
    )
    set_role_resource_inline_policies_semaphore = NoqSemaphore(
        set_role_resource_inline_policies, 20
    )
    set_role_resource_managed_policies_semaphore = NoqSemaphore(
        set_role_resource_managed_policies, 30
    )
    set_role_resource_tags_semaphore = NoqSemaphore(set_role_resource_tags, 75)
    role_dir = get_role_dir(base_output_dir)

    log.info("Generating AWS role templates.")
    log.info(
        "Beginning to retrieve AWS IAM Roles.", accounts=list(account_config_map.keys())
    )

    account_roles = await generate_account_role_resource_files_semaphore.process(
        [
            {"account_config": account_config}
            for account_config in account_config_map.values()
        ]
    )
    messages = []
    for account_role in account_roles:
        for role in account_role["roles"]:
            messages.append(
                {
                    "role_name": role["name"],
                    "role_resource_path": role["path"],
                    "account_config": account_config_map[account_role["account_id"]],
                }
            )

    log.info("Setting inline policies for roles")
    await set_role_resource_inline_policies_semaphore.process(messages)
    log.info("Setting managed policies for roles")
    await set_role_resource_managed_policies_semaphore.process(messages)
    log.info("Setting tags for roles")
    await set_role_resource_tags_semaphore.process(messages)
    log.info("Finished retrieving role details")

    # Use these for testing `create_templated_role`
    # account_role_output = json.dumps(account_roles)
    # with open("account_role_output.json", "w") as f:
    #     f.write(account_role_output)
    # with open("account_role_output.json") as f:
    #     account_roles = json.loads(f.read())

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

    grouped_role_map = await base_group_str_attribute(account_config_map, account_roles)

    log.info("Writing templated roles")
    for role_name, role_refs in grouped_role_map.items():
        await create_templated_role(
            configs[0], account_config_map, role_name, role_refs, role_dir
        )

    log.info("Finished templated role generation")
