from __future__ import annotations

import asyncio
import itertools
import os
from collections import defaultdict
from typing import TYPE_CHECKING, Union

import aiofiles

from iambic.core import noq_json as json
from iambic.core.logger import log
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import (
    create_or_update_template,
    delete_orphaned_templates,
)
from iambic.core.utils import NoqSemaphore, normalize_dict_keys, resource_file_upsert
from iambic.plugins.v0_1_0.aws.event_bridge.models import PermissionSetMessageDetails
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import (
    AWS_IDENTITY_CENTER_PERMISSION_SET_TEMPLATE_TYPE,
    AwsIdentityCenterPermissionSetTemplate,
    PermissionSetProperties,
)
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.utils import (
    enrich_permission_set_details,
    get_permission_set_details,
    get_permission_set_users_and_groups,
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

# TODO: Update all grouping functions to support org grouping once multiple orgs with IdentityCenter is functional
# TODO: Update partial import to support permission set only being deleted on a single org

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig

RESOURCE_DIR = ["identity_center", "permission_set"]


def get_template_dir(base_dir: str) -> str:
    repo_dir = os.path.join(base_dir, "resources", "aws", *RESOURCE_DIR)
    os.makedirs(repo_dir, exist_ok=True)
    return repo_dir


def get_templated_permission_set_file_path(
    permission_set_dir: str,
    permission_set_name: str,
):
    file_name = (
        permission_set_name.replace(" ", "")
        .replace("{{var.", "")
        .replace("{{", "")
        .replace("}}_", "_")
        .replace("}}", "_")
        .replace(".", "_")
        .lower()
    )
    return str(os.path.join(permission_set_dir, f"{file_name}.yaml"))


async def gather_permission_set_names(
    aws_accounts: list[AWSAccount],
    detect_messages: list[PermissionSetMessageDetails],
) -> list[str]:
    sso_admin_client_map = {
        aws_account.account_id: (
            await aws_account.get_boto3_client(
                "sso-admin",
                region_name=aws_account.identity_center_details.region.value,
            )
        )
        for aws_account in aws_accounts
    }

    permission_sets = await asyncio.gather(
        *[
            get_permission_set_details(
                sso_admin_client_map[message.account_id],
                message.instance_arn,
                message.permission_set_arn,
            )
            for message in detect_messages
        ]
    )

    return list(
        set(
            [
                permission_set["Name"]
                for permission_set in permission_sets
                if permission_set
            ]
        )
    )


async def generate_permission_set_resource_file(
    identity_center_client,
    account_id: str,
    instance_arn: str,
    permission_set: dict,
    user_map: dict,
    group_map: dict,
    account_resource_dir: str,
) -> dict:
    permission_set = await enrich_permission_set_details(
        identity_center_client, instance_arn, permission_set
    )
    permission_set["assignments"] = await get_permission_set_users_and_groups(
        identity_center_client,
        instance_arn,
        permission_set["PermissionSetArn"],
        user_map,
        group_map,
    )
    file_path = os.path.join(account_resource_dir, f'{permission_set["Name"]}.json')
    response = dict(
        account_id=account_id, permission_set=permission_set, file_path=file_path
    )
    await resource_file_upsert(file_path, permission_set)

    return response


def _sorted_and_clean_access_rules(unsorted_rules: list) -> list:
    # access_rules has no semantic ordering, we sort it explicitly to ensure the template
    # generation is deterministic.
    sorted_access_rules = sorted(
        unsorted_rules, key=lambda rule: rule["account_rule_key"]
    )
    for rule in sorted_access_rules:
        del rule["account_rule_key"]
    return sorted_access_rules


async def create_templated_permission_set(  # noqa: C901
    aws_account_map: dict[str, AWSAccount],
    permission_set_name: str,
    permission_set_refs: list[dict],
    permission_set_dir: str,
    existing_template_map: dict,
) -> Union[AwsIdentityCenterPermissionSetTemplate, None]:
    account_id_to_permissionn_set_map = {}
    num_of_accounts = len(permission_set_refs)
    for permission_set_ref in permission_set_refs:
        async with aiofiles.open(permission_set_ref["file_path"], mode="r") as f:
            content_dict = json.loads(await f.read())
            account_id_to_permissionn_set_map[
                permission_set_ref["account_id"]
            ] = normalize_dict_keys(content_dict)

    # calculate preference based on existing template
    prefer_templatized = calculate_import_preference(
        existing_template_map.get(permission_set_name)
    )

    # Generate the params used for attribute creation
    template_params = {"identifier": permission_set_name, "access_rules": []}
    template_properties = {"name": permission_set_name}
    description_resources = list()
    relay_state_resources = list()
    customer_managed_policy_ref_resources = list()
    managed_policy_resources = list()
    inline_policy_resources = list()
    permissions_boundary_resources = list()
    tag_resources = list()
    session_duration_resources = list()

    for account_id, permission_set_dict in account_id_to_permissionn_set_map.items():
        if session_duration := permission_set_dict.get("session_duration"):
            session_duration_resources.append(
                {
                    "account_id": account_id,
                    "resources": [{"resource_val": session_duration}],
                }
            )

        if managed_policies := permission_set_dict.get("attached_managed_policies"):
            managed_policy_resources.append(
                {
                    "account_id": account_id,
                    "resources": [
                        {"resource_val": {"arn": mp["arn"]}} for mp in managed_policies
                    ],
                }
            )

        if customer_managed_policy_refs := permission_set_dict.get(
            "customer_managed_policy_references"
        ):
            customer_managed_policy_ref_resources.append(
                {
                    "account_id": account_id,
                    "resources": [
                        {"resource_val": customer_managed_policy_ref}
                        for customer_managed_policy_ref in customer_managed_policy_refs
                    ],
                }
            )

        if permissions_boundary := permission_set_dict.get("permissions_boundary"):
            permissions_boundary_resources.append(
                {
                    "account_id": account_id,
                    "resources": [{"resource_val": permissions_boundary}],
                }
            )

        if tags := permission_set_dict.get("tags"):
            tag_resources.append(
                {
                    "account_id": account_id,
                    "resources": [{"resource_val": tag} for tag in tags],
                }
            )

        if description := permission_set_dict.get("description"):
            description_resources.append(
                {"account_id": account_id, "resources": [{"resource_val": description}]}
            )

        if inline_policy := permission_set_dict.get("inline_policy"):
            inline_policy_resources.append(
                {
                    "account_id": account_id,
                    "resources": [{"resource_val": inline_policy}],
                }
            )

        if relay_state := permission_set_dict.get("relay_state"):
            relay_state_resources.append(
                {"account_id": account_id, "resources": [{"resource_val": relay_state}]}
            )

        aws_account = aws_account_map[account_id]
        account_rules = {}
        for assignment_type in ["user", "group"]:
            for assignment_id, details in (
                permission_set_dict.get("assignments", {})
                .get(assignment_type, {})
                .items()
            ):
                accounts = sorted(details["accounts"])
                account_rule_key = "_".join(accounts)
                if not account_rules.get(account_rule_key):
                    if all(
                        account in accounts
                        for account in aws_account.identity_center_details.org_account_map.keys()
                    ):
                        accounts = ["*"]
                    else:
                        accounts = sorted(
                            [
                                aws_account.identity_center_details.org_account_map[
                                    nested_account_id
                                ]
                                for nested_account_id in details["accounts"]
                            ]
                        )
                    account_rules[account_rule_key] = {
                        "included_orgs": [aws_account.org_id],
                        "included_accounts": accounts,
                        "users": [],
                        "groups": [],
                        "account_rule_key": account_rule_key,  # this will be remove after sorting
                    }

                account_rules[account_rule_key][f"{assignment_type}s"].append(
                    details.get("user_name", details["display_name"])
                )

        if account_rules:
            template_params["access_rules"].extend(list(account_rules.values()))

    # access_rules has no semantic ordering, we sort it explicitly to ensure the template
    # generation is deterministic.
    template_params["access_rules"] = _sorted_and_clean_access_rules(
        template_params["access_rules"]
    )

    if len(permission_set_refs) != len(aws_account_map):
        template_params["included_orgs"] = [
            aws_account_map[permission_set["account_id"]].org_id
            for permission_set in permission_set_refs
        ]

    if session_duration_resources:
        template_properties["session_duration"] = await group_int_or_str_attribute(
            aws_account_map,
            num_of_accounts,
            session_duration_resources,
            "session_duration",
        )

    if permissions_boundary_resources:
        template_properties["permissions_boundary"] = await group_dict_attribute(
            aws_account_map,
            num_of_accounts,
            permissions_boundary_resources,
            prefer_templatized=prefer_templatized,
        )

    if description_resources:
        template_properties["description"] = await group_int_or_str_attribute(
            aws_account_map, num_of_accounts, description_resources, "description"
        )

    if managed_policy_resources:
        template_properties["managed_policies"] = await group_dict_attribute(
            aws_account_map,
            num_of_accounts,
            managed_policy_resources,
            False,
            prefer_templatized=prefer_templatized,
        )

    if customer_managed_policy_ref_resources:
        template_properties[
            "customer_managed_policy_references"
        ] = await group_dict_attribute(
            aws_account_map,
            num_of_accounts,
            customer_managed_policy_ref_resources,
            False,
            prefer_templatized=prefer_templatized,
        )

    if tag_resources:
        template_properties["tags"] = await group_dict_attribute(
            aws_account_map,
            num_of_accounts,
            tag_resources,
            False,
            prefer_templatized=prefer_templatized,
        )

    if inline_policy_resources:
        template_properties["inline_policy"] = json.loads(
            await group_int_or_str_attribute(  # hm... other (role, user) inline policies use group_dict_attribute, not sure the reason
                aws_account_map,
                num_of_accounts,
                inline_policy_resources,
                "inline_policy",
            )
        )

    if relay_state_resources:
        template_properties["relay_state"] = await group_int_or_str_attribute(
            aws_account_map, num_of_accounts, relay_state_resources, "relay_state"
        )

    file_path = get_templated_permission_set_file_path(
        permission_set_dir, permission_set_name
    )
    return create_or_update_template(
        file_path,
        existing_template_map,
        permission_set_name,
        AwsIdentityCenterPermissionSetTemplate,
        template_params,
        PermissionSetProperties(**template_properties),
        list(aws_account_map.values()),
    )


async def collect_aws_permission_sets(
    exe_message: ExecutionMessage,
    config: AWSConfig,
    identity_center_template_map: dict,
    detect_messages: list[PermissionSetMessageDetails] = None,
):
    resource_dir = exe_message.get_directory(*RESOURCE_DIR)
    aws_account_map = await get_aws_account_map(config)
    if exe_message.provider_id:
        aws_account_map = {
            exe_message.provider_id: aws_account_map[exe_message.provider_id]
        }

    if detect_messages:
        detect_messages = [
            msg
            for msg in detect_messages
            if isinstance(msg, PermissionSetMessageDetails)
        ]
        if not detect_messages:
            return

    identity_center_accounts = []
    if config.accounts:
        identity_center_accounts.extend(
            [account for account in config.accounts if account.identity_center_details]
        )

    if not identity_center_accounts:
        return

    log.info("Generating AWS Identity Center Permission Set templates.")
    log.info(
        "Beginning to retrieve AWS Identity Center Permission Sets.",
        org_accounts=list(aws_account_map.keys()),
    )

    await asyncio.gather(
        *[account.set_identity_center_details() for account in identity_center_accounts]
    )

    messages = []
    permission_set_names = []
    if detect_messages:
        permission_sets_in_aws = set(
            list(
                itertools.chain.from_iterable(
                    [
                        aws_account.identity_center_details.permission_set_map.keys()
                        for aws_account in identity_center_accounts
                    ]
                )
            )
        )

        permission_set_names = await gather_permission_set_names(
            identity_center_accounts,
            detect_messages,
        )
        permission_set_names = [
            name for name in permission_set_names if name in permission_sets_in_aws
        ]

    # Upsert permission sets
    for aws_account in aws_account_map.values():
        if not aws_account.identity_center_details:
            continue

        instance_arn = aws_account.identity_center_details.instance_arn
        identity_center_client = await aws_account.get_boto3_client(
            "sso-admin", region_name=aws_account.identity_center_details.region_name
        )

        if permission_set_names:
            for name in permission_set_names:
                if permission_set := aws_account.identity_center_details.permission_set_map.get(
                    name
                ):
                    messages.append(
                        dict(
                            account_id=aws_account.account_id,
                            identity_center_client=identity_center_client,
                            instance_arn=instance_arn,
                            permission_set=permission_set,
                            user_map=aws_account.identity_center_details.user_map,
                            group_map=aws_account.identity_center_details.group_map,
                            account_resource_dir=resource_dir,
                        )
                    )
        else:
            for (
                permission_set
            ) in aws_account.identity_center_details.permission_set_map.values():
                messages.append(
                    dict(
                        account_id=aws_account.account_id,
                        identity_center_client=identity_center_client,
                        instance_arn=instance_arn,
                        permission_set=permission_set,
                        user_map=aws_account.identity_center_details.user_map,
                        group_map=aws_account.identity_center_details.group_map,
                        account_resource_dir=resource_dir,
                    )
                )

    log.info(
        "Beginning to enrich AWS IAM Identity Center Permission Sets.",
        org_accounts=list(aws_account_map.keys()),
        permission_set_count=len(messages),
    )
    generate_permission_set_resource_file_semaphore = NoqSemaphore(
        generate_permission_set_resource_file, 30
    )
    all_permission_sets = await generate_permission_set_resource_file_semaphore.process(
        messages
    )

    log.info(
        "Finished enriching AWS IAM Identity Center Permission Sets.",
        org_accounts=list(aws_account_map.keys()),
        permission_set_count=len(messages),
    )

    all_permission_sets_output = json.dumps(all_permission_sets)
    with open(
        exe_message.get_file_path(*RESOURCE_DIR, file_name_and_extension="output.json"),
        "w",
    ) as f:
        f.write(all_permission_sets_output)


async def generate_aws_permission_set_templates(
    exe_message: ExecutionMessage,
    config: AWSConfig,
    base_output_dir: str,
    identity_center_template_map: dict,
    detect_messages: list[PermissionSetMessageDetails] = None,
):
    resource_dir = get_template_dir(base_output_dir)
    aws_account_map = await get_aws_account_map(config)
    existing_template_map = identity_center_template_map.get(
        AWS_IDENTITY_CENTER_PERMISSION_SET_TEMPLATE_TYPE, {}
    )

    all_permission_sets = await exe_message.get_sub_exe_files(
        *RESOURCE_DIR, file_name_and_extension="output.json", flatten_results=True
    )

    permission_sets_grouped_by_account = defaultdict(list)
    # list[dict(account_id:str, resources=list[dict(resource_val: str, **)])]

    for elem in range(len(all_permission_sets)):
        account_id = all_permission_sets[elem].pop("account_id")
        all_permission_sets[elem]["resource_val"] = all_permission_sets[elem][
            "permission_set"
        ]["Name"]
        permission_sets_grouped_by_account[account_id].append(all_permission_sets[elem])

    all_permission_sets = [
        dict(account_id=account_id, resources=permission_sets)
        for account_id, permission_sets in permission_sets_grouped_by_account.items()
    ]

    grouped_permission_set_map = await base_group_str_attribute(
        aws_account_map, all_permission_sets
    )

    log.info(
        "Writing templated AWS Identity Center Permission Set.",
        unique_identities=len(grouped_permission_set_map),
    )
    all_resource_ids = set()
    for name, refs in grouped_permission_set_map.items():
        resource_template = await create_templated_permission_set(
            aws_account_map,
            name,
            refs,
            resource_dir,
            existing_template_map,
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

    log.info("Finished templated AWS Identity Center Permission Set generation")
