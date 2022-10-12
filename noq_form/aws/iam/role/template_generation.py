import os
import pathlib
from typing import Union

import aiofiles
import botocore

from noq_form.aws.iam.role.models import MultiAccountRoleTemplate
from noq_form.aws.iam.role.utils import (
    get_role_inline_policies,
    get_role_managed_policies,
    list_roles,
)
from noq_form.config.models import AccountConfig, Config
from noq_form.core import noq_json as json
from noq_form.core.logger import log
from noq_form.core.template_generation import (
    group_dict_attribute,
    group_int_attribute,
    group_str_attribute,
    set_included_accounts_for_grouped_attribute,
)
from noq_form.core.utils import NoqSemaphore, normalize_boto3_resp

ROLE_RESPONSE_DIR = pathlib.Path.home().joinpath(
    ".noqform", "resources", "aws", "roles"
)
ROLE_REPO_DIR = pathlib.Path.cwd().joinpath("resources", "aws", "roles")


def get_templated_role_file_path(role_name: str):
    os.makedirs(ROLE_REPO_DIR, exist_ok=True)
    file_name = (
        role_name.replace("{{", "")
        .replace("}}_", "_")
        .replace("}}", "_")
        .replace(".", "_")
        .lower()
    )
    return str(os.path.join(ROLE_REPO_DIR, f"{file_name}.yaml"))


def get_account_role_resource_dir(account_id: str) -> str:
    account_role_response_dir = os.path.join(ROLE_RESPONSE_DIR, account_id)
    os.makedirs(account_role_response_dir, exist_ok=True)
    return account_role_response_dir


async def role_resource_file_upsert(
    file_path: Union[str | pathlib.Path],
    content_as_dict: dict,
    replace_file: bool = False,
):
    if not replace_file and os.path.exists(file_path):
        async with aiofiles.open(file_path, mode="r") as f:
            content_dict = json.loads(await f.read())
            content_as_dict = {**content_dict, **content_as_dict}

    async with aiofiles.open(file_path, mode="w") as f:
        await f.write(json.dumps(content_as_dict, indent=2))


async def generate_account_role_resource_files(account_config: AccountConfig) -> dict:
    account_role_response_dir = get_account_role_resource_dir(account_config.account_id)
    role_resource_file_upsert_semaphore = NoqSemaphore(role_resource_file_upsert, 10)
    messages = []

    response = dict(account_id=account_config.account_id, roles=[])
    iam_client = account_config.get_boto3_session().client(
        "iam", config=botocore.client.Config(max_pool_connections=50)
    )
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


async def set_role_resource_inline_policies(
    role_name: str, role_resource_path: str, account_config: AccountConfig
):
    iam_client = account_config.get_boto3_session().client(
        "iam", config=botocore.client.Config(max_pool_connections=50)
    )
    role_inline_policies = await get_role_inline_policies(role_name, iam_client)
    for k in role_inline_policies.keys():
        role_inline_policies[k]["policy_name"] = k

    role_inline_policies = list(role_inline_policies.values())
    await role_resource_file_upsert(
        role_resource_path, {"InlinePolicies": role_inline_policies}, False
    )


async def set_role_resource_managed_policies(
    role_name: str, role_resource_path: str, account_config: AccountConfig
):
    iam_client = account_config.get_boto3_session().client(
        "iam", config=botocore.client.Config(max_pool_connections=50)
    )
    role_managed_policies = await get_role_managed_policies(role_name, iam_client)
    await role_resource_file_upsert(
        role_resource_path, {"ManagedPolicies": role_managed_policies}, False
    )


async def set_templated_role_attributes(
    account_configs: list[AccountConfig], role_name: str, role_refs: list[dict]
):
    account_id_map = {
        account_config.account_id: account_config for account_config in account_configs
    }
    account_id_to_role_map = {}
    num_of_accounts = len(role_refs)
    for role_ref in role_refs:
        async with aiofiles.open(role_ref["path"], mode="r") as f:
            content_dict = json.loads(await f.read())
            account_id_to_role_map[role_ref["account_id"]] = normalize_boto3_resp(
                content_dict
            )

    account_resources = list()
    description_resources = list()
    managed_policy_resources = list()
    assume_role_policy_document_resources = list()
    inline_policy_document_resources = list()
    tag_resources = list()
    max_session_duration_resources = dict()
    for account_id, role_dict in account_id_to_role_map.items():
        account_resources.append(
            {
                "account_id": account_id,
                "resources": [{"resource_val": role_dict["path"]}],
            }
        )
        managed_policy_resources.append(
            {
                "account_id": account_id,
                "resources": [
                    {"resource_val": mp["policy_arn"]}
                    for mp in role_dict.get("managed_policies", [])
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
        max_session_duration_resources[account_id] = role_dict["max_session_duration"]

        if inline_policies := role_dict.get("inline_policies"):
            inline_policy_document_resources.append(
                {
                    "account_id": account_id,
                    "resources": [{"resource_val": inline_policies}],
                }
            )

        if tags := role_dict.get("tags"):
            tag_resources.append(
                {"account_id": account_id, "resources": [{"resource_val": tags}]}
            )

        if description := role_dict.get("description"):
            description_resources.append(
                {"account_id": account_id, "resources": [{"resource_val": description}]}
            )

    description = None
    inline_policies = []
    tags = []
    assume_role_policy_documents = await group_dict_attribute(
        account_configs, assume_role_policy_document_resources
    )
    assume_role_policy_documents = await set_included_accounts_for_grouped_attribute(
        account_configs, num_of_accounts, assume_role_policy_documents
    )
    if len(assume_role_policy_documents) == 1:
        assume_role_policy_documents = assume_role_policy_documents[0]

    paths = await group_str_attribute(account_configs, account_resources)
    max_session_duration = group_int_attribute(max_session_duration_resources)
    if not isinstance(max_session_duration, int):
        max_session_duration_dicts = []
        for msd, account_ids in max_session_duration.items():
            max_session_duration_dicts.append(
                {"included_accounts": account_ids, "max_session_duration": msd}
            )
        max_session_duration = max_session_duration_dicts

    # managed_policies = await group_str_attribute(
    #     account_configs, managed_policy_resources
    # )
    # managed_policies = await set_included_accounts_for_grouped_attribute(account_configs, num_of_accounts, managed_policies)

    if description_resources:
        description = await group_str_attribute(account_configs, description_resources)
        # if not isinstance(description, str):
        #     description_keys = await set_included_accounts_for_grouped_attribute(account_configs, num_of_accounts, description)

    if tag_resources:
        tags = await group_dict_attribute(account_configs, tag_resources)
        tags = await set_included_accounts_for_grouped_attribute(
            account_configs, num_of_accounts, tags
        )

    if inline_policy_document_resources:
        inline_policies = []
        inline_policy_vals = await group_dict_attribute(
            account_configs, inline_policy_document_resources
        )
        inline_policy_vals = await set_included_accounts_for_grouped_attribute(
            account_configs, num_of_accounts, inline_policy_vals
        )
        for inline_policy_val in inline_policy_vals:
            for policy_statement in inline_policy_val["resource_val"]:
                inline_policies.append(
                    {
                        "included_accounts": inline_policy_val["included_accounts"],
                        **policy_statement,
                    }
                )
    if len(role_refs) == len(account_configs):
        included_accounts = ["*"]
    else:
        included_accounts = [
            account_id_map[role_ref["account_id"]].account_name
            for role_ref in role_refs
        ]

    role = MultiAccountRoleTemplate(
        file_path=get_templated_role_file_path(role_name),
        path=paths,
        included_accounts=included_accounts,
        role_name=role_name,
        description=description,
        max_session_duration=max_session_duration,
        tags=tags,
        inline_policies=inline_policies,
        assume_role_policy_documents=assume_role_policy_documents,
    )
    role.write()


async def generate_aws_role_templates(configs: list[Config]):
    account_configs = []
    observed_account_ids = (
        set()
    )  # Ensure uniqueness on account_id in multi-config environment
    for config in configs:
        config.set_account_defaults()
        account_configs.extend(
            account_config
            for account_config in config.accounts
            if account_config.account_id not in observed_account_ids
        )
        observed_account_ids = set(
            [account_config.account_id for account_config in account_configs]
        )

    account_id_map = {
        account_config.account_id: account_config for account_config in account_configs
    }
    generate_account_role_resource_files_semaphore = NoqSemaphore(
        generate_account_role_resource_files, 5
    )
    set_role_resource_inline_policies_semaphore = NoqSemaphore(
        set_role_resource_inline_policies, 20
    )
    set_role_resource_managed_policies_semaphore = NoqSemaphore(
        set_role_resource_managed_policies, 30
    )
    log.info(
        "Beginning to retrieve AWS IAM Roles.", accounts=list(account_id_map.keys())
    )

    account_roles = await generate_account_role_resource_files_semaphore.process(
        [{"account_config": account_config} for account_config in config.accounts]
    )

    messages = []
    for account_role in account_roles:
        account_config = account_id_map[account_role["account_id"]]
        for role in account_role["roles"]:
            messages.append(
                {
                    "role_name": role["name"],
                    "role_resource_path": role["path"],
                    "account_config": account_config,
                }
            )

    log.info("Setting inline policies for roles")
    await set_role_resource_inline_policies_semaphore.process(messages)
    log.info("Setting managed policies for roles")
    await set_role_resource_managed_policies_semaphore.process(messages)
    log.info("Finished retrieving roles and policies")

    # Really only using this for testing so we don't have to retrieve everything all the time.
    account_role_output = json.dumps(account_roles)
    with open("account_role_output.json", "w") as f:
        f.write(account_role_output)

    # with open("account_role_output.json") as f:
    #     account_roles = json.loads(f.read())

    log.info("Grouping similar roles")

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

    grouped_role_map = await group_str_attribute(account_configs, account_roles)

    log.info("Writing templated roles")
    for role_name, role_refs in grouped_role_map.items():
        await set_templated_role_attributes(account_configs, role_name, role_refs)
