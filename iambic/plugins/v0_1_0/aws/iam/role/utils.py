from __future__ import annotations

import asyncio
import json
from itertools import chain
from typing import Union

from deepdiff import DeepDiff

from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.core.utils import aio_wrapper, plugin_apply_wrapper
from iambic.plugins.v0_1_0.aws.models import AWSAccount
from iambic.plugins.v0_1_0.aws.utils import boto_crud_call, paginated_search


async def get_role_inline_policy_names(role_name: str, iam_client):
    return await paginated_search(
        iam_client.list_role_policies, "PolicyNames", RoleName=role_name
    )


async def get_role_instance_profiles(role_name: str, iam_client):
    return await paginated_search(
        iam_client.list_instance_profiles_for_role,
        "InstanceProfiles",
        RoleName=role_name,
    )


async def list_roles(iam_client):
    # role_details_list is missing MaxSessionDuration, see https://docs.aws.amazon.com/IAM/latest/APIReference/API_RoleDetail.html
    role_details_list = await paginated_search(
        iam_client.get_account_authorization_details, "RoleDetailList", Filter=["Role"]
    )
    role_name_to_role_details = {
        role_details["RoleName"]: role_details for role_details in role_details_list
    }

    # roles_list is missing PermissionBoundary, see https://github.com/awsdocs/iam-user-guide/issues/81
    role_list = await paginated_search(iam_client.list_roles, "Roles")

    # glue the missing info to roles_list
    for role in role_list:
        role_name = role["RoleName"]
        if (
            role_name in role_name_to_role_details
            and "PermissionsBoundary" in role_name_to_role_details[role_name]
        ):
            role["PermissionsBoundary"] = role_name_to_role_details[role_name][
                "PermissionsBoundary"
            ]

    return role_list


async def list_role_tags(role_name: str, iam_client):
    return await paginated_search(iam_client.list_role_tags, "Tags", RoleName=role_name)


async def get_role_policy(role_name: str, policy_name: str, iam_client):
    return await boto_crud_call(
        iam_client.get_role_policy, RoleName=role_name, PolicyName=policy_name
    )


async def get_role_inline_policies(
    role_name: str, iam_client, as_dict: bool = True
) -> Union[list, dict]:
    policy_names = await get_role_inline_policy_names(role_name, iam_client)
    policies = await asyncio.gather(
        *[
            get_role_policy(role_name, policy_name, iam_client)
            for policy_name in policy_names
        ]
    )
    if as_dict:
        return {policy["PolicyName"]: policy["PolicyDocument"] for policy in policies}
    else:
        return [
            {"PolicyName": policy["PolicyName"], **policy["PolicyDocument"]}
            for policy in policies
        ]


async def get_role_managed_policies(role_name: str, iam_client) -> list[dict[str, str]]:
    marker: dict[str, str] = {}
    policies = []

    while True:
        response = await boto_crud_call(
            iam_client.list_attached_role_policies, RoleName=role_name, **marker
        )
        policies.extend(response["AttachedPolicies"])

        if response["IsTruncated"]:
            marker["Marker"] = response["Marker"]
        else:
            break

    return policies


async def get_role(role_name: str, iam_client, include_policies: bool = True) -> dict:
    try:
        current_role = (await boto_crud_call(iam_client.get_role, RoleName=role_name))[
            "Role"
        ]
        if include_policies:
            current_role["ManagedPolicies"] = await get_role_managed_policies(
                role_name, iam_client
            )
            current_role["InlinePolicies"] = await get_role_inline_policies(
                role_name, iam_client, as_dict=False
            )
    except iam_client.exceptions.NoSuchEntityException:
        current_role = {}

    return current_role


async def get_role_across_accounts(
    aws_accounts: list[AWSAccount], role_name: str, include_policies: bool = True
) -> dict:
    async def get_role_for_account(aws_account: AWSAccount):
        iam_client = await aws_account.get_boto3_client("iam")
        return {
            aws_account.account_id: await get_role(
                role_name, iam_client, include_policies
            )
        }

    account_on_roles = await asyncio.gather(
        *[get_role_for_account(aws_account) for aws_account in aws_accounts]
    )
    return {
        account_id: role
        for resp in account_on_roles
        for account_id, role in resp.items()
    }


async def apply_role_tags(
    role_name: str,
    iam_client,
    template_tags: list[dict],
    existing_tags: list[dict],
    log_params: dict,
) -> list[ProposedChange]:
    existing_tag_map = {tag["Key"]: tag.get("Value") for tag in existing_tags}
    template_tag_map = {tag["Key"]: tag.get("Value") for tag in template_tags}
    tags_to_apply = [
        tag
        for tag in template_tags
        if tag.get("Value", "")
        != existing_tag_map.get(
            tag["Key"], None
        )  # existing_tag_map default cannot be "", because "" is an valid value for a tag
    ]
    tasks = []
    response = []

    if tags_to_remove := [
        tag["Key"] for tag in existing_tags if tag["Key"] not in template_tag_map.keys()
    ]:
        log_str = "Stale tags discovered."
        if ctx.execute:
            log_str = f"{log_str} Removing tags..."

            async def untag_role():
                exceptions = []
                try:
                    await boto_crud_call(
                        iam_client.untag_role,
                        RoleName=role_name,
                        TagKeys=tags_to_remove,
                    )
                except Exception as e:
                    exceptions.append(str(e))
                return [
                    ProposedChange(
                        change_type=ProposedChangeType.DETACH,
                        attribute="tags",
                        resource_type="aws:iam:role",
                        resource_id=role_name,
                        change_summary={"TagKeys": tags_to_remove},
                        exceptions_seen=exceptions,
                    )
                ]

            tasks.append(untag_role())
        else:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.DETACH,
                    attribute="tags",
                    resource_type="aws:iam:role",
                    resource_id=role_name,
                    change_summary={"TagKeys": tags_to_remove},
                )
            )

        log.debug(log_str, tags=tags_to_remove, **log_params)

    if tags_to_apply:
        log_str = "New tags discovered in AWS."

        if ctx.execute:
            log_str = f"{log_str} Adding tags..."

            async def tag_role():
                exceptions = []
                response = []
                try:
                    await boto_crud_call(
                        iam_client.tag_role, RoleName=role_name, Tags=tags_to_apply
                    )
                except Exception as e:
                    exceptions.append(str(e))
                for tag in tags_to_apply:
                    response.append(
                        ProposedChange(
                            change_type=ProposedChangeType.ATTACH,
                            attribute="tags",
                            resource_type="aws:iam:role",
                            resource_id=role_name,
                            new_value=tag,
                            exceptions_seen=exceptions,
                        )
                    )
                return response

            tasks.append(tag_role())
        else:
            for tag in tags_to_apply:
                response.append(
                    ProposedChange(
                        change_type=ProposedChangeType.ATTACH,
                        attribute="tags",
                        resource_type="aws:iam:role",
                        resource_id=role_name,
                        new_value=tag,
                    )
                )
        log.debug(log_str, tags=tags_to_apply, **log_params)

    if tasks:
        results: list[list[ProposedChange]] = await asyncio.gather(
            *tasks, return_exceptions=True
        )
        for r in results:
            response.extend(r)

    return response


async def update_assume_role_policy(
    role_name,
    iam_client,
    template_policy_document: dict,
    existing_policy_document: str,
    log_params: dict,
) -> list[ProposedChange]:
    response = []
    policy_drift = None

    if existing_policy_document:
        if isinstance(existing_policy_document, str):
            existing_policy_document = json.loads(existing_policy_document)

        policy_drift = await aio_wrapper(
            DeepDiff,
            existing_policy_document,
            template_policy_document,
            report_repetition=True,
            ignore_order=True,
        )

        # DeepDiff will return type changes as actual type functions and not strings,
        # and this will cause json serialization to fail later on when we process
        # the proposed changes. We force type changes to strings here.
        policy_drift = json.loads(policy_drift.to_json())

    if not existing_policy_document or bool(policy_drift):
        log_str = "Changes to the AssumeRolePolicyDocument discovered."
        if policy_drift:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.UPDATE,
                    attribute="assume_role_policy_document",
                    resource_type="aws:iam:role",
                    resource_id=role_name,
                    change_summary=policy_drift,
                    current_value=existing_policy_document,
                    new_value=template_policy_document,
                )
            )
        else:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.CREATE,
                    attribute="assume_role_policy_document",
                    resource_type="aws:iam:role",
                    resource_id=role_name,
                    new_value=template_policy_document,
                )
            )

        if ctx.execute:
            boto_action = "Creating" if existing_policy_document else "Updating"
            log_str = f"{log_str} {boto_action} AssumeRolePolicyDocument..."
            await boto_crud_call(
                iam_client.update_assume_role_policy,
                RoleName=role_name,
                PolicyDocument=json.dumps(template_policy_document),
            )
        log.debug(log_str, **log_params)

    return response


async def apply_role_managed_policies(
    role_name,
    iam_client,
    template_policies: list[dict],
    existing_policies: list[dict],
    log_params: dict,
) -> list[ProposedChange]:
    tasks = []
    response = []
    template_policies = [policy["PolicyArn"] for policy in template_policies]
    existing_managed_policies = [policy["PolicyArn"] for policy in existing_policies]

    # Create new managed policies
    new_managed_policies = [
        policy_arn
        for policy_arn in template_policies
        if policy_arn not in existing_managed_policies
    ]
    if new_managed_policies:
        log_str = "New managed policies discovered."
        if ctx.execute:
            log_str = f"{log_str} Attaching managed policies..."
            for policy_arn in new_managed_policies:
                proposed_changes = [
                    ProposedChange(
                        change_type=ProposedChangeType.ATTACH,
                        resource_type="aws:policy_document",
                        resource_id=policy_arn,
                        attribute="managed_policies",
                    )
                ]
                apply_awaitable = boto_crud_call(
                    iam_client.attach_role_policy,
                    RoleName=role_name,
                    PolicyArn=policy_arn,
                )
                tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
        else:
            response.extend(
                [
                    ProposedChange(
                        change_type=ProposedChangeType.ATTACH,
                        resource_type="aws:policy_document",
                        resource_id=policy_arn,
                        attribute="managed_policies",
                    )
                    for policy_arn in new_managed_policies
                ]
            )

        log.debug(log_str, managed_policies=new_managed_policies, **log_params)

    # Delete existing managed policies not in template
    existing_managed_policies = [
        policy_arn
        for policy_arn in existing_managed_policies
        if policy_arn not in template_policies
    ]
    if existing_managed_policies:
        log_str = "Stale managed policies discovered."

        if ctx.execute:
            log_str = f"{log_str} Detaching managed policies..."
            for policy_arn in existing_managed_policies:
                proposed_changes = [
                    ProposedChange(
                        change_type=ProposedChangeType.DETACH,
                        resource_type="aws:policy_document",
                        resource_id=policy_arn,
                        attribute="managed_policies",
                    )
                ]
                apply_awaitable = boto_crud_call(
                    iam_client.detach_role_policy,
                    RoleName=role_name,
                    PolicyArn=policy_arn,
                )
                tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
        else:
            response.extend(
                [
                    ProposedChange(
                        change_type=ProposedChangeType.DETACH,
                        resource_type="aws:policy_document",
                        resource_id=policy_arn,
                        attribute="managed_policies",
                    )
                    for policy_arn in existing_managed_policies
                ]
            )
        log.debug(log_str, managed_policies=existing_managed_policies, **log_params)

    if tasks:
        results: list[list[ProposedChange]] = await asyncio.gather(*tasks)
        return list(chain.from_iterable(results))

    return response


async def apply_role_permission_boundary(
    role_name,
    iam_client,
    template_permission_boundary: dict,
    existing_permission_boundary: dict,
    log_params: dict,
) -> list[ProposedChange]:
    tasks = []
    response = []
    template_boundary_policy_arn = template_permission_boundary.get(
        "PolicyArn"
    )  # from serializing iambic template
    existing_boundary_policy_arn = existing_permission_boundary.get(
        "PermissionsBoundaryArn"
    )  # from boto response

    if template_boundary_policy_arn and (
        existing_boundary_policy_arn != template_boundary_policy_arn
    ):
        log_str = "New or updated permission boundary discovered."

        proposed_changes = [
            ProposedChange(
                change_type=ProposedChangeType.ATTACH,
                resource_id=template_boundary_policy_arn,
                resource_type="aws:policy_document",
                attribute="permission_boundary",
            )
        ]
        response.extend(proposed_changes)

        if ctx.execute:
            log_str = f"{log_str} Attaching permission boundary..."

            tasks = [
                plugin_apply_wrapper(
                    boto_crud_call(
                        iam_client.put_role_permissions_boundary,
                        RoleName=role_name,
                        PermissionsBoundary=template_boundary_policy_arn,
                    ),
                    proposed_changes,
                )
            ]

        log.debug(
            log_str, permission_boundary=template_boundary_policy_arn, **log_params
        )

    # Detach permission boundary not in template
    if template_boundary_policy_arn is None and (
        existing_boundary_policy_arn != template_boundary_policy_arn
    ):
        log_str = "Stale permission boundary discovered."

        proposed_changes = [
            ProposedChange(
                change_type=ProposedChangeType.DETACH,
                resource_type="aws:policy_document",
                resource_id=existing_boundary_policy_arn,
                attribute="permission_boundary",
            )
        ]
        response.extend(proposed_changes)

        if ctx.execute:
            log_str = f"{log_str} Detaching permission boundary..."

            tasks.extend(
                [
                    plugin_apply_wrapper(
                        boto_crud_call(
                            iam_client.delete_role_permissions_boundary,
                            RoleName=role_name,
                        ),
                        proposed_changes,
                    )
                ]
            )

        log.debug(
            log_str, permission_boundary=existing_boundary_policy_arn, **log_params
        )

    if tasks:
        results: list[list[ProposedChange]] = await asyncio.gather(*tasks)
        return list(chain.from_iterable(results))
    else:
        return response


async def apply_role_inline_policies(
    role_name,
    iam_client,
    template_policies: list[dict],
    existing_policies: list[dict],
    log_params: dict,
) -> list[ProposedChange]:
    apply_tasks = []
    delete_tasks = []
    plan_response = []
    template_policy_map = {
        policy["PolicyName"]: {k: v for k, v in policy.items() if k != "PolicyName"}
        for policy in template_policies
    }
    existing_policy_map = {
        policy["PolicyName"]: {k: v for k, v in policy.items() if k != "PolicyName"}
        for policy in existing_policies
    }

    for policy_name in existing_policy_map.keys():
        if not template_policy_map.get(policy_name):
            log_str = "Stale inline policies discovered."
            proposed_changes = [
                ProposedChange(
                    change_type=ProposedChangeType.DELETE,
                    resource_type="aws:policy_document",
                    resource_id=policy_name,
                    attribute="inline_policies",
                )
            ]
            plan_response.extend(proposed_changes)

            if ctx.execute:
                log_str = f"{log_str} Removing inline policy..."

                apply_awaitable = boto_crud_call(
                    iam_client.delete_role_policy,
                    RoleName=role_name,
                    PolicyName=policy_name,
                )
                delete_tasks.append(
                    plugin_apply_wrapper(apply_awaitable, proposed_changes)
                )
            log.debug(log_str, policy_name=policy_name, **log_params)

    for policy_name, policy_document in template_policy_map.items():
        existing_policy_doc = existing_policy_map.get(policy_name)
        policy_drift = None
        if existing_policy_doc:
            policy_drift = await aio_wrapper(
                DeepDiff,
                existing_policy_doc,
                policy_document,
                ignore_order=True,
                report_repetition=True,
            )

            # DeepDiff will return type changes as actual type functions and not strings,
            # and this will cause json serialization to fail later on when we process
            # the proposed changes. We force type changes to strings here.
            policy_drift = json.loads(policy_drift.to_json())

        if not existing_policy_doc or policy_drift:
            if policy_drift:
                log_params["policy_drift"] = policy_drift
                boto_action = "Updating"
                resource_existence = "Stale"
                proposed_changes = [
                    ProposedChange(
                        change_type=ProposedChangeType.UPDATE,
                        resource_type="aws:policy_document",
                        resource_id=policy_name,
                        attribute="inline_policies",
                        change_summary=policy_drift,
                        current_value=existing_policy_doc,
                        new_value=policy_document,
                    )
                ]
            else:
                boto_action = "Creating"
                resource_existence = "New"
                proposed_changes = [
                    ProposedChange(
                        change_type=ProposedChangeType.CREATE,
                        resource_type="aws:policy_document",
                        resource_id=policy_name,
                        attribute="inline_policies",
                        new_value=policy_document,
                    )
                ]
            plan_response.extend(proposed_changes)

            log_str = f"{resource_existence} inline policies discovered."
            if ctx.execute and policy_document:
                log_str = f"{log_str} {boto_action} inline policy..."
                apply_awaitable = boto_crud_call(
                    iam_client.put_role_policy,
                    RoleName=role_name,
                    PolicyName=policy_name,
                    PolicyDocument=json.dumps(policy_document),
                )
                apply_tasks.append(
                    plugin_apply_wrapper(apply_awaitable, proposed_changes)
                )

            log.debug(log_str, policy_name=policy_name, **log_params)

    if apply_tasks or delete_tasks:
        results: list[list[ProposedChange]] = []
        if delete_tasks:
            results.extend(await asyncio.gather(*delete_tasks))
            if apply_tasks:
                # Wait for the policy deletion to propagate before applying new policies
                # Otherwise a max policy limit error may be thrown
                await asyncio.sleep(3)

        if apply_tasks:
            results.extend(await asyncio.gather(*apply_tasks))

        return list(chain.from_iterable(results))
    else:
        return plan_response


async def delete_iam_role(role_name: str, iam_client, log_params: dict):
    instance_profiles = await get_role_instance_profiles(role_name, iam_client)

    tasks = []
    for instance_profile in instance_profiles:
        tasks.append(
            boto_crud_call(
                iam_client.remove_role_from_instance_profile,
                RoleName=role_name,
                InstanceProfileName=instance_profile["InstanceProfileName"],
            )
        )
    await asyncio.gather(*tasks)

    tasks = []
    for instance_profile in instance_profiles:
        tasks.append(
            boto_crud_call(
                iam_client.delete_instance_profile,
                InstanceProfileName=instance_profile["InstanceProfileName"],
            )
        )
    await asyncio.gather(*tasks)

    tasks = []
    # Detach managed policies
    managed_policies = await get_role_managed_policies(role_name, iam_client)
    managed_policies = [policy["PolicyArn"] for policy in managed_policies]
    log.debug(
        "Detaching managed policies.", managed_policies=managed_policies, **log_params
    )
    for policy in managed_policies:
        tasks.append(
            boto_crud_call(
                iam_client.detach_role_policy, RoleName=role_name, PolicyArn=policy
            )
        )

    # Delete inline policies
    inline_policies = await get_role_inline_policies(role_name, iam_client)
    inline_policies = list(inline_policies.keys())
    log.debug(
        "Deleting inline policies.", managed_policies=inline_policies, **log_params
    )
    for policy_name in inline_policies:
        tasks.append(
            boto_crud_call(
                iam_client.delete_role_policy,
                RoleName=role_name,
                PolicyName=policy_name,
            )
        )

    # Actually perform the deletion of Managed & Inline policies
    await asyncio.gather(*tasks)
    # Now that everything has been removed from the role, delete the role itself
    await boto_crud_call(iam_client.delete_role, RoleName=role_name)
