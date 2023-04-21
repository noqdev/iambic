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


async def get_user_inline_policy_names(user_name: str, iam_client):
    return await paginated_search(
        iam_client.list_user_policies, "PolicyNames", UserName=user_name
    )


async def list_users(iam_client):
    # user_details_list is missing MaxSessionDuration, see https://docs.aws.amazon.com/IAM/latest/APIReference/API_RoleDetail.html
    return await paginated_search(
        iam_client.get_account_authorization_details, "UserDetailList", Filter=["User"]
    )


async def list_user_tags(user_name: str, iam_client):
    return await paginated_search(iam_client.list_user_tags, "Tags", UserName=user_name)


async def get_user_policy(user_name: str, policy_name: str, iam_client):
    return await boto_crud_call(
        iam_client.get_user_policy, UserName=user_name, PolicyName=policy_name
    )


async def get_user_groups(
    user_name: str, iam_client, as_dict: bool = True
) -> Union[list, dict]:
    groups = await paginated_search(
        iam_client.list_groups_for_user, "Groups", UserName=user_name
    )
    if as_dict:
        return {group["GroupName"]: group for group in groups}
    else:
        return [{"GroupName": group["GroupName"]} for group in groups]


async def get_user_inline_policies(
    user_name: str, iam_client, as_dict: bool = True
) -> Union[list, dict]:
    policy_names = await get_user_inline_policy_names(user_name, iam_client)
    policies = await asyncio.gather(
        *[
            get_user_policy(user_name, policy_name, iam_client)
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


async def get_user_managed_policies(user_name: str, iam_client) -> list[dict[str, str]]:
    marker: dict[str, str] = {}
    policies = []

    while True:
        # TODO: Figure out why attached managed policies are not shown
        response = await boto_crud_call(
            iam_client.list_attached_user_policies, UserName=user_name, **marker
        )
        policies.extend(response["AttachedPolicies"])

        if response["IsTruncated"]:
            marker["Marker"] = response["Marker"]
        else:
            break

    return policies


async def get_user(user_name: str, iam_client, include_policies: bool = True) -> dict:
    try:
        current_user = (await boto_crud_call(iam_client.get_user, UserName=user_name))[
            "User"
        ]
        if include_policies:
            current_user["ManagedPolicies"] = await get_user_managed_policies(
                user_name, iam_client
            )
            current_user["InlinePolicies"] = await get_user_inline_policies(
                user_name, iam_client, as_dict=False
            )
            current_user["Groups"] = await get_user_groups(
                user_name, iam_client, as_dict=False
            )
    except iam_client.exceptions.NoSuchEntityException:
        current_user = {}

    return current_user


async def get_user_across_accounts(
    aws_accounts: list[AWSAccount], user_name: str, include_policies: bool = True
) -> dict:
    async def get_user_for_account(aws_account: AWSAccount):
        iam_client = await aws_account.get_boto3_client("iam")
        return {
            aws_account.account_id: await get_user(
                user_name, iam_client, include_policies
            )
        }

    account_on_users = await asyncio.gather(
        *[get_user_for_account(aws_account) for aws_account in aws_accounts]
    )
    return {
        account_id: user
        for resp in account_on_users
        for account_id, user in resp.items()
    }


async def apply_user_tags(
    user_name: str,
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
        if tag.get("Value") != existing_tag_map.get(tag["Key"])
    ]
    tasks = []
    response = []

    if tags_to_remove := [
        tag["Key"] for tag in existing_tags if not template_tag_map.get(tag["Key"])
    ]:
        log_str = "Stale tags discovered."

        proposed_changes = [
            ProposedChange(
                change_type=ProposedChangeType.DETACH,
                resource_type="aws:iam:user",
                resource_id=user_name,
                attribute="tags",
                change_summary={"TagKeys": tags_to_remove},
            )
        ]

        response.extend(proposed_changes)

        if ctx.execute:
            log_str = f"{log_str} Removing tags..."

            apply_awaitable = boto_crud_call(
                iam_client.untag_user,
                UserName=user_name,
                TagKeys=tags_to_remove,
            )
            tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))

        log.debug(log_str, tags=tags_to_remove, **log_params)

    if tags_to_apply:
        log_str = "New tags discovered in AWS."

        proposed_changes = [
            ProposedChange(
                change_type=ProposedChangeType.ATTACH,
                resource_type="aws:iam:user",
                resource_id=user_name,
                attribute="tags",
                new_value=tag,
                current_value=existing_tag_map.get(tag["Key"]),
            )
            for tag in tags_to_apply
        ]
        response.extend(proposed_changes)
        if ctx.execute:
            log_str = f"{log_str} Adding tags..."
            apply_awaitable = boto_crud_call(
                iam_client.tag_user, UserName=user_name, Tags=tags_to_apply
            )
            tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))

        log.debug(log_str, tags=tags_to_apply, **log_params)

    if tasks:
        results: list[list[ProposedChange]] = await asyncio.gather(*tasks)
        return list(chain.from_iterable(results))
    else:
        return response


async def apply_user_permission_boundary(
    user_name,
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
                resource_type="aws:policy_document",
                resource_id=template_boundary_policy_arn,
                attribute="permission_boundary",
            )
        ]
        response.extend(proposed_changes)

        if ctx.execute:
            log_str = f"{log_str} Attaching permission boundary..."

            tasks = [
                plugin_apply_wrapper(
                    boto_crud_call(
                        iam_client.put_user_permissions_boundary,
                        UserName=user_name,
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
                            iam_client.delete_user_permissions_boundary,
                            UserName=user_name,
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


async def apply_user_managed_policies(
    user_name,
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

        proposed_changes = [
            ProposedChange(
                change_type=ProposedChangeType.ATTACH,
                resource_type="aws:policy_document",
                resource_id=policy_arn,
                attribute="managed_policies",
            )
            for policy_arn in new_managed_policies
        ]
        response.extend(proposed_changes)

        if ctx.execute:
            log_str = f"{log_str} Attaching managed policies..."

            tasks = [
                plugin_apply_wrapper(
                    boto_crud_call(
                        iam_client.attach_user_policy,
                        UserName=user_name,
                        PolicyArn=policy_arn,
                    ),
                    [
                        ProposedChange(
                            change_type=ProposedChangeType.ATTACH,
                            resource_type="aws:policy_document",
                            resource_id=policy_arn,
                            attribute="managed_policies",
                        )
                    ],
                )
                for policy_arn in new_managed_policies
            ]

        log.debug(log_str, managed_policies=new_managed_policies, **log_params)

    # Delete existing managed policies not in template
    existing_managed_policies = [
        policy_arn
        for policy_arn in existing_managed_policies
        if policy_arn not in template_policies
    ]
    if existing_managed_policies:
        log_str = "Stale managed policies discovered."

        proposed_changes = [
            ProposedChange(
                change_type=ProposedChangeType.DETACH,
                resource_type="aws:policy_document",
                resource_id=policy_arn,
                attribute="managed_policies",
            )
            for policy_arn in existing_managed_policies
        ]
        response.extend(proposed_changes)

        if ctx.execute:
            log_str = f"{log_str} Detaching managed policies..."

            tasks.extend(
                [
                    plugin_apply_wrapper(
                        boto_crud_call(
                            iam_client.detach_user_policy,
                            UserName=user_name,
                            PolicyArn=policy_arn,
                        ),
                        [
                            ProposedChange(
                                change_type=ProposedChangeType.DETACH,
                                resource_type="aws:policy_document",
                                resource_id=policy_arn,
                                attribute="managed_policies",
                            )
                        ],
                    )
                    for policy_arn in existing_managed_policies
                ]
            )

        log.debug(log_str, managed_policies=existing_managed_policies, **log_params)

    if tasks:
        results: list[list[ProposedChange]] = await asyncio.gather(*tasks)
        return list(chain.from_iterable(results))
    else:
        return response


async def apply_user_inline_policies(
    user_name,
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
                    iam_client.delete_user_policy,
                    UserName=user_name,
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
                    iam_client.put_user_policy,
                    UserName=user_name,
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


async def apply_user_groups(
    user_name,
    iam_client,
    template_groups: list[dict],
    existing_groups: list[dict],
    log_params: dict,
) -> list[ProposedChange]:
    tasks = []
    response = []
    template_groups = [group["GroupName"] for group in template_groups]
    existing_groups = [group["GroupName"] for group in existing_groups]

    # Create new groups
    for group in template_groups:
        if group not in existing_groups:
            log_str = "New groups discovered."
            proposed_changes = [
                ProposedChange(
                    change_type=ProposedChangeType.CREATE,
                    resource_type="aws:iam:group",
                    resource_id=group,
                    attribute="groups",
                )
            ]
            response.extend(proposed_changes)
            if ctx.execute:
                log_str = f"{log_str} Adding user to group..."
                apply_awaitable = boto_crud_call(
                    iam_client.add_user_to_group,
                    GroupName=group,
                    UserName=user_name,
                )
                tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))

            log.debug(log_str, group_name=group, **log_params)

    # Remove stale groups
    for group in existing_groups:
        if group not in template_groups:
            log_str = "Stale groups discovered."
            proposed_changes = [
                ProposedChange(
                    change_type=ProposedChangeType.DELETE,
                    resource_type="aws:iam:group",
                    resource_id=group,
                    attribute="groups",
                )
            ]
            response.extend(proposed_changes)
            if ctx.execute:
                log_str = f"{log_str} Removing user from group..."
                apply_awaitable = boto_crud_call(
                    iam_client.remove_user_from_group,
                    GroupName=group,
                    UserName=user_name,
                )
                tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))

            log.debug(log_str, group_name=group, **log_params)

    if tasks:
        results: list[list[ProposedChange]] = await asyncio.gather(*tasks)
        return list(chain.from_iterable(results))
    else:
        return response


async def delete_iam_user(user_name: str, iam_client, log_params: dict):
    tasks = []
    # Detach managed policies
    managed_policies = await get_user_managed_policies(user_name, iam_client)
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
                    iam_client.detach_user_policy, UserName=user_name, PolicyArn=policy
                )
            )

    # Delete inline policies
    inline_policies = await get_user_inline_policies(user_name, iam_client)
    if inline_policies:
        inline_policies = list(inline_policies.keys())
        log.debug(
            "Deleting inline policies.", managed_policies=inline_policies, **log_params
        )
        for policy_name in inline_policies:
            tasks.append(
                boto_crud_call(
                    iam_client.delete_user_policy,
                    UserName=user_name,
                    PolicyName=policy_name,
                )
            )

    # Remove groups
    user_groups = await get_user_groups(user_name, iam_client)
    if user_groups:
        user_groups = sorted(list(user_groups.keys()))
        log.debug("Removing user groups.", groups=user_groups, **log_params)
        for group in user_groups:
            tasks.append(
                boto_crud_call(
                    iam_client.remove_user_from_group,
                    UserName=user_name,
                    GroupName=group,
                )
            )

    # Actually perform the deletion of Managed & Inline policies
    await asyncio.gather(*tasks)
    # Now that everything has been removed from the user, delete the user itself
    await boto_crud_call(iam_client.delete_user, UserName=user_name)
