from __future__ import annotations

import asyncio
import json
from itertools import chain
from typing import TYPE_CHECKING, Union

from deepdiff import DeepDiff

from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.core.utils import aio_wrapper, plugin_apply_wrapper
from iambic.plugins.v0_1_0.aws.utils import boto_crud_call, paginated_search

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.aws.models import AWSAccount


async def get_group_inline_policy_names(group_name: str, iam_client):
    return await paginated_search(
        iam_client.list_group_policies, "PolicyNames", GroupName=group_name
    )


async def list_groups(iam_client):
    return await paginated_search(iam_client.list_groups, "Groups")


async def list_users_in_group(group_name: str, iam_client):
    return await paginated_search(iam_client.get_group, "Users", GroupName=group_name)


async def get_group_policy(group_name: str, policy_name: str, iam_client):
    return await boto_crud_call(
        iam_client.get_group_policy, GroupName=group_name, PolicyName=policy_name
    )


async def get_group_inline_policies(
    group_name: str, iam_client, as_dict: bool = True
) -> Union[list, dict]:
    policy_names = await get_group_inline_policy_names(group_name, iam_client)
    policies = await asyncio.gather(
        *[
            get_group_policy(group_name, policy_name, iam_client)
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


async def get_group_managed_policies(
    group_name: str, iam_client
) -> list[dict[str, str]]:
    marker: dict[str, str] = {}
    policies = []

    while True:
        response = await boto_crud_call(
            iam_client.list_attached_group_policies, GroupName=group_name, **marker
        )
        policies.extend(response["AttachedPolicies"])

        if response["IsTruncated"]:
            marker["Marker"] = response["Marker"]
        else:
            break

    return policies


async def get_group(group_name: str, iam_client, include_policies: bool = True) -> dict:
    try:
        current_group = (
            await boto_crud_call(iam_client.get_group, GroupName=group_name)
        )["Group"]
        if include_policies:
            current_group["ManagedPolicies"] = await get_group_managed_policies(
                group_name, iam_client
            )
            current_group["InlinePolicies"] = await get_group_inline_policies(
                group_name, iam_client, as_dict=False
            )
    except iam_client.exceptions.NoSuchEntityException:
        current_group = {}

    return current_group


async def get_group_across_accounts(
    aws_accounts: list[AWSAccount], group_name: str, include_policies: bool = True
) -> dict:
    async def get_group_for_account(aws_account: AWSAccount):
        iam_client = await aws_account.get_boto3_client("iam")
        return {
            aws_account.account_id: await get_group(
                group_name, iam_client, include_policies
            )
        }

    account_on_groups = await asyncio.gather(
        *[get_group_for_account(aws_account) for aws_account in aws_accounts]
    )
    return {
        account_id: group
        for resp in account_on_groups
        for account_id, group in resp.items()
    }


async def apply_group_managed_policies(
    group_name,
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
            response.extend(proposed_changes)
            if ctx.execute:
                apply_awaitable = boto_crud_call(
                    iam_client.attach_group_policy,
                    GroupName=group_name,
                    PolicyArn=policy_arn,
                )
                tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
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
            response.extend(proposed_changes)
            if ctx.execute:
                apply_awaitable = boto_crud_call(
                    iam_client.detach_group_policy,
                    GroupName=group_name,
                    PolicyArn=policy_arn,
                )
                tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
        log.debug(log_str, managed_policies=existing_managed_policies, **log_params)

    if tasks:
        results: list[list[ProposedChange]] = await asyncio.gather(*tasks)
        return list(chain.from_iterable(results))
    else:
        return response


async def apply_group_inline_policies(
    group_name,
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
                    iam_client.delete_group_policy,
                    GroupName=group_name,
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
                    iam_client.put_group_policy,
                    GroupName=group_name,
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


async def delete_iam_group(group_name: str, iam_client, log_params: dict):
    tasks = []
    # Remove users from group
    attached_users = await list_users_in_group(group_name, iam_client)
    if attached_users:
        attached_users = [attached_user["UserName"] for attached_user in attached_users]
        log.debug(
            "Removing users from group.", attached_users=attached_users, **log_params
        )
        for attached_user in attached_users:
            tasks.append(
                boto_crud_call(
                    iam_client.remove_user_from_group,
                    GroupName=group_name,
                    UserName=attached_user,
                )
            )
        await asyncio.gather(*tasks)

    tasks = []
    # Detach managed policies
    managed_policies = await get_group_managed_policies(group_name, iam_client)
    if managed_policies:
        managed_policies = [policy["PolicyArn"] for policy in managed_policies]
        log.debug(
            "Detaching managed policies.",
            managed_policies=managed_policies,
            **log_params,
        )
        for policy in managed_policies:
            tasks.append(
                boto_crud_call(
                    iam_client.detach_group_policy,
                    GroupName=group_name,
                    PolicyArn=policy,
                )
            )

    # Delete inline policies
    inline_policies = await get_group_inline_policies(group_name, iam_client)
    if inline_policies:
        inline_policies = list(inline_policies.keys())
        log.debug(
            "Deleting inline policies.", managed_policies=inline_policies, **log_params
        )
        for policy_name in inline_policies:
            tasks.append(
                boto_crud_call(
                    iam_client.delete_group_policy,
                    GroupName=group_name,
                    PolicyName=policy_name,
                )
            )

    if managed_policies or inline_policies:
        # Actually perform the deletion of Managed & Inline policies
        await asyncio.gather(*tasks)

    # Now that everything has been removed from the group, delete the group itself
    await boto_crud_call(iam_client.delete_group, GroupName=group_name)
