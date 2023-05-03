from __future__ import annotations

import asyncio
from itertools import chain

from botocore.exceptions import ClientError
from deepdiff import DeepDiff

from iambic.core import noq_json as json
from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.core.utils import aio_wrapper, async_batch_processor, plugin_apply_wrapper
from iambic.plugins.v0_1_0.aws.models import AWSAccount
from iambic.plugins.v0_1_0.aws.utils import boto_crud_call, legacy_paginated_search


async def get_permission_set_details(
    identity_center_client,
    instance_arn: str,
    permission_set_arn: str,
) -> dict:
    try:
        return (
            await boto_crud_call(
                identity_center_client.describe_permission_set,
                InstanceArn=instance_arn,
                PermissionSetArn=permission_set_arn,
            )
        ).get("PermissionSet", {})
    except identity_center_client.exceptions.ResourceNotFoundException:
        return {}
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFound":
            return {}
        else:
            raise


async def generate_permission_set_map(aws_accounts: list[AWSAccount], templates: list):
    """Generates the map of permission sets for AWS accounts that are referenced in at least 1 template

    :param aws_accounts:
    :param templates:
    :return:
    """
    from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import (
        AWS_IDENTITY_CENTER_PERMISSION_SET_TEMPLATE_TYPE,
    )

    org_include_set = set()
    include_all = False
    accounts_to_set_identity_center = []

    for template in templates:
        if template.template_type == AWS_IDENTITY_CENTER_PERMISSION_SET_TEMPLATE_TYPE:
            for org in template.included_orgs:
                if org == "*":
                    include_all = True
                    break
                org_include_set.add(org)

        if include_all:
            break

    for aws_account in aws_accounts:
        if (
            include_all or aws_account.org_id in org_include_set
        ) and aws_account.identity_center_details:
            accounts_to_set_identity_center.append(aws_account)

    await asyncio.gather(
        *[
            account.set_identity_center_details()
            for account in accounts_to_set_identity_center
        ]
    )


async def get_permission_set_users_and_groups(
    identity_center_client,
    instance_arn: str,
    permission_set_arn: str,
    user_map: dict,
    group_map: dict,
) -> dict:
    response = {
        "user": {k: dict(accounts=[], **v) for k, v in user_map.items()},
        "group": {k: dict(accounts=[], **v) for k, v in group_map.items()},
    }

    query_params = dict(InstanceArn=instance_arn, PermissionSetArn=permission_set_arn)
    instance_accounts = await legacy_paginated_search(
        identity_center_client.list_accounts_for_provisioned_permission_set,
        response_key="AccountIds",
        **query_params,
    )
    all_account_assignments = await async_batch_processor(
        [
            legacy_paginated_search(
                identity_center_client.list_account_assignments,
                response_key="AccountAssignments",
                AccountId=account_id,
                **query_params,
            )
            for account_id in instance_accounts
        ],
        15,
        1,
        return_exceptions=True,
    )

    for account_assignments in all_account_assignments:
        for aa in account_assignments:
            response[aa["PrincipalType"].lower()][aa["PrincipalId"]]["accounts"].append(
                aa["AccountId"]
            )

    response["user"] = {k: v for k, v in response["user"].items() if v["accounts"]}
    response["group"] = {k: v for k, v in response["group"].items() if v["accounts"]}
    return response


async def get_permission_set_users_and_groups_as_access_rules(
    identity_center_client,
    instance_arn: str,
    permission_set_arn: str,
    user_map: dict,
    group_map: dict,
    org_account_map: dict,
) -> list[dict]:
    name_map = {"user": "UserName", "group": "DisplayName"}
    permission_set_users_and_groups = await get_permission_set_users_and_groups(
        identity_center_client, instance_arn, permission_set_arn, user_map, group_map
    )
    response = []

    for assignment_type in ["user", "group"]:
        resource_type = assignment_type.upper()
        for assignment_id, assignment_details in permission_set_users_and_groups[
            assignment_type
        ].items():
            for account_id in assignment_details["accounts"]:
                response.append(
                    {
                        "account_id": account_id,
                        "resource_id": assignment_id,
                        "resource_type": resource_type,
                        "resource_name": assignment_details.get(
                            name_map[assignment_type]
                        ),
                        "account_name": f"{account_id} ({org_account_map[account_id]})",
                    }
                )

    return response


async def enrich_permission_set_details(
    identity_center_client, instance_arn: str, permission_set_details: dict
):
    permission_set_arn = permission_set_details["PermissionSetArn"]
    query_params = dict(InstanceArn=instance_arn, PermissionSetArn=permission_set_arn)
    tasks = [
        boto_crud_call(
            identity_center_client.get_inline_policy_for_permission_set, **query_params
        ),
        boto_crud_call(
            identity_center_client.get_permissions_boundary_for_permission_set,
            **query_params,
        ),
        legacy_paginated_search(
            identity_center_client.list_customer_managed_policy_references_in_permission_set,
            response_key="CustomerManagedPolicyReferences",
            retain_key=True,
            **query_params,
        ),
        legacy_paginated_search(
            identity_center_client.list_managed_policies_in_permission_set,
            response_key="AttachedManagedPolicies",
            retain_key=True,
            **query_params,
        ),
        legacy_paginated_search(
            identity_center_client.list_tags_for_resource,
            response_key="Tags",
            retain_key=True,
            InstanceArn=instance_arn,
            ResourceArn=permission_set_arn,
        ),
    ]
    permission_set_responses = await asyncio.gather(*tasks, return_exceptions=True)
    for permission_set_response in permission_set_responses:
        if isinstance(permission_set_response, Exception):
            continue

        for k, v in permission_set_response.items():
            if k == "ResponseMetadata" or not v:
                continue
            permission_set_details[k] = v
    return permission_set_details


async def apply_permission_set_aws_managed_policies(
    identity_center_client,
    instance_arn: str,
    permission_set_arn: str,
    template_policy_arns: list[str],
    existing_policy_arns: list[str],
    log_params: dict,
) -> list[ProposedChange]:
    tasks = []
    response = []

    # Create new managed policies
    new_managed_policies = [
        policy_arn
        for policy_arn in template_policy_arns
        if policy_arn not in existing_policy_arns
    ]
    if new_managed_policies:
        log_str = "New AWS managed policies discovered."
        if ctx.execute:
            log_str = f"{log_str} Attaching AWS managed policies..."

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
                    identity_center_client.attach_managed_policy_to_permission_set,
                    InstanceArn=instance_arn,
                    PermissionSetArn=permission_set_arn,
                    ManagedPolicyArn=policy_arn,
                )
                tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
        log.debug(log_str, managed_policies=new_managed_policies, **log_params)

    # Delete existing managed policies not in template
    existing_managed_policies = [
        policy_arn
        for policy_arn in existing_policy_arns
        if policy_arn not in template_policy_arns
    ]
    if existing_managed_policies:
        log_str = "Stale AWS managed policies discovered."
        if ctx.execute:
            log_str = f"{log_str} Detaching AWS managed policies..."

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
                    identity_center_client.detach_managed_policy_from_permission_set,
                    InstanceArn=instance_arn,
                    PermissionSetArn=permission_set_arn,
                    ManagedPolicyArn=policy_arn,
                )
                tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
        log.debug(log_str, managed_policies=existing_managed_policies, **log_params)

    if tasks:
        results: list[list[ProposedChange]] = await asyncio.gather(*tasks)
        return list(chain.from_iterable(results))
    else:
        return response


async def apply_permission_set_customer_managed_policies(
    identity_center_client,
    instance_arn: str,
    permission_set_arn: str,
    template_policies: list[dict],
    existing_policies: list[dict],
    log_params: dict,
) -> list[ProposedChange]:
    tasks = []
    response = []

    log.debug(
        "Customer Managed Policies",
        template_policies=template_policies,
        existing_policies=existing_policies,
    )

    template_policy_map = {
        f"{policy['Path']}{policy['Name']}": policy for policy in template_policies
    }
    existing_policy_map = {
        f"{policy['Path']}{policy['Name']}": policy for policy in existing_policies
    }

    # Create new managed policies
    new_customer_managed_policy_references = [
        policy
        for policy_path, policy in template_policy_map.items()
        if not existing_policy_map.get(policy_path)
    ]
    if new_customer_managed_policy_references:
        log_str = "New customer managed policies discovered."
        if ctx.execute:
            log_str = f"{log_str} Attaching customer managed policies..."

        for policy in new_customer_managed_policy_references:
            proposed_changes = [
                ProposedChange(
                    change_type=ProposedChangeType.ATTACH,
                    resource_type="aws:policy_document",
                    resource_id=f"{policy['Path']}{policy['Name']}",
                    attribute="customer_managed_policies",
                )
            ]
            response.extend(proposed_changes)
            if ctx.execute:
                apply_awaitable = boto_crud_call(
                    identity_center_client.attach_customer_managed_policy_reference_to_permission_set,
                    InstanceArn=instance_arn,
                    PermissionSetArn=permission_set_arn,
                    CustomerManagedPolicyReference=policy,
                )
                tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
        log.debug(
            log_str,
            customer_managed_policy_refs=new_customer_managed_policy_references,
            **log_params,
        )

    # Delete existing managed policies not in template
    existing_customer_managed_policy_references = [
        policy
        for policy_path, policy in existing_policy_map.items()
        if not template_policy_map.get(policy_path)
    ]
    if existing_customer_managed_policy_references:
        log_str = "Stale customer managed policies discovered."
        if ctx.execute:
            log_str = f"{log_str} Detaching customer managed policies..."

        for policy in existing_customer_managed_policy_references:
            proposed_changes = [
                ProposedChange(
                    change_type=ProposedChangeType.DETACH,
                    resource_type="aws:policy_document",
                    resource_id=f"{policy['Path']}{policy['Name']}",
                    attribute="customer_managed_policies",
                )
            ]
            response.extend(proposed_changes)
            if ctx.execute:
                apply_awaitable = boto_crud_call(
                    identity_center_client.detach_customer_managed_policy_reference_from_permission_set,
                    retryable_errors=["ConflictException"],
                    InstanceArn=instance_arn,
                    PermissionSetArn=permission_set_arn,
                    CustomerManagedPolicyReference=policy,
                )
                tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
        log.debug(
            log_str,
            customer_managed_policy_refs=existing_customer_managed_policy_references,
            **log_params,
        )

    if tasks:
        results: list[list[ProposedChange]] = await asyncio.gather(*tasks)
        return list(chain.from_iterable(results))
    else:
        return response


async def create_account_assignment(
    identity_center_client,
    account_id: str,
    instance_arn: str,
    permission_set_arn: str,
    resource_type: str,
    resource_id: str,
    resource_name: str,
    log_params: dict,
):
    status = await boto_crud_call(
        identity_center_client.create_account_assignment,
        InstanceArn=instance_arn,
        TargetId=account_id,
        TargetType="AWS_ACCOUNT",
        PermissionSetArn=permission_set_arn,
        PrincipalType=resource_type,
        PrincipalId=resource_id,
    )
    request_id = status.get("AccountAssignmentCreationStatus", {}).get("RequestId")
    creation_status = status.get("AccountAssignmentCreationStatus", {})

    while creation_status.get("Status") == "IN_PROGRESS":
        await asyncio.sleep(0.5)
        status = await boto_crud_call(
            identity_center_client.describe_account_assignment_creation_status,
            InstanceArn=instance_arn,
            AccountAssignmentCreationRequestId=request_id,
        )
        creation_status = status.get("AccountAssignmentCreationStatus", {})

        if creation_status.get("Status") == "FAILED":
            log_params = {
                **log_params,
                "resource_type": f"aws:identity_center:account_assignment:{resource_type.lower()}",
            }
            log.error(
                "Unable to create account assignment.",
                reason=creation_status.get("FailureReason"),
                assigned_account_id=account_id,
                resource_name=resource_name,
                **log_params,
            )
            return


async def delete_account_assignment(
    identity_center_client,
    account_id: str,
    instance_arn: str,
    permission_set_arn: str,
    resource_type: str,
    resource_id: str,
    resource_name: str,
    log_params: dict,
):
    status = await boto_crud_call(
        identity_center_client.delete_account_assignment,
        InstanceArn=instance_arn,
        TargetId=account_id,
        TargetType="AWS_ACCOUNT",
        PermissionSetArn=permission_set_arn,
        PrincipalType=resource_type,
        PrincipalId=resource_id,
    )
    request_id = status.get("AccountAssignmentDeletionStatus", {}).get("RequestId")
    deletion_status = status.get("AccountAssignmentDeletionStatus", {})

    while deletion_status.get("Status") == "IN_PROGRESS":
        await asyncio.sleep(0.5)
        status = await boto_crud_call(
            identity_center_client.describe_account_assignment_deletion_status,
            InstanceArn=instance_arn,
            AccountAssignmentDeletionRequestId=request_id,
        )
        deletion_status = status.get("AccountAssignmentDeletionStatus", {})

        if deletion_status.get("Status") == "FAILED":
            log_params = {
                **log_params,
                "resource_type": f"aws:identity_center:account_assignment:{resource_type.lower()}",
            }
            log.error(
                "Unable to delete account assignment.",
                reason=deletion_status.get("FailureReason"),
                assigned_account_id=account_id,
                resource_name=resource_name,
                **log_params,
            )
            return


async def apply_account_assignments(
    identity_center_client,
    instance_arn: str,
    permission_set_arn: str,
    template_assignments: list[dict],
    existing_assignments: list[dict],
    log_params: dict,
) -> list[ProposedChange]:
    """
    assignment objects = dict(
        account_id: str
        resource_id: str
        resource_name: str
        account_name: str
        resource_type: USER | GROUP
    )

    identity_center_client: boto3 client
    instance_arn: str
    permission_set_arn: str
    template_assignments: list[dict]. This is the desired list of assignments from the template
    existing_assignments: list[dict]. These are the existing assignments from AWS
    log_params: dict
    """
    tasks = []
    response = []
    template_assignment_map = {
        f"{ta['account_id']}:{ta['resource_type']}:{ta['resource_id']}": ta
        for ta in template_assignments
    }
    existing_assignment_map = {
        f"{ea['account_id']}:{ea['resource_type']}:{ea['resource_id']}": ea
        for ea in existing_assignments
    }

    for assignment_id, assignment in existing_assignment_map.items():
        if not template_assignment_map.get(assignment_id):
            log_str = "Stale assignments discovered."
            resource_type = (
                "arn:aws:iam::aws:user"
                if assignment["resource_type"] == "USER"
                else "arn:aws:iam::aws:group"
            )
            proposed_changes = [
                ProposedChange(
                    change_type=ProposedChangeType.DELETE,
                    account=assignment["account_name"],
                    resource_id=assignment["resource_name"],
                    resource_type=resource_type,
                    attribute="account_assignment",
                )
            ]
            response.extend(proposed_changes)
            if ctx.execute:
                log_str = f"{log_str} Removing account assignment..."
                apply_awaitable = delete_account_assignment(
                    identity_center_client,
                    account_id=assignment["account_id"],
                    instance_arn=instance_arn,
                    permission_set_arn=permission_set_arn,
                    resource_type=assignment["resource_type"],
                    resource_id=assignment["resource_id"],
                    resource_name=assignment["resource_name"],
                    log_params=log_params,
                )
                tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
            log.info(log_str, details=assignment, **log_params)

    for assignment_id, assignment in template_assignment_map.items():
        if not existing_assignment_map.get(assignment_id):
            resource_type = (
                "arn:aws:iam::aws:user"
                if assignment["resource_type"] == "USER"
                else "arn:aws:iam::aws:group"
            )
            proposed_changes = [
                ProposedChange(
                    change_type=ProposedChangeType.CREATE,
                    account=assignment["account_name"],
                    resource_id=assignment["resource_name"],
                    resource_type=resource_type,
                    attribute="account_assignment",
                )
            ]
            response.extend(proposed_changes)

            log_str = "New account assignments discovered."
            if ctx.execute:
                log_str = f"{log_str} Creating account assignment..."
                apply_awaitable = create_account_assignment(
                    identity_center_client,
                    account_id=assignment["account_id"],
                    instance_arn=instance_arn,
                    permission_set_arn=permission_set_arn,
                    resource_type=assignment["resource_type"],
                    resource_id=assignment["resource_id"],
                    resource_name=assignment["resource_name"],
                    log_params=log_params,
                )
                tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
            log.info(log_str, details=assignment, **log_params)

    if tasks:
        results: list[list[ProposedChange]] = await async_batch_processor(tasks, 10, 1)
        return list(chain.from_iterable(results))
    else:
        return response


async def apply_permission_set_inline_policy(
    identity_center_client,
    instance_arn: str,
    permission_set_arn: str,
    template_inline_policy: str,
    existing_inline_policy: str,
    log_params: dict,
) -> list[ProposedChange]:
    response = []
    policy_drift = None

    if isinstance(template_inline_policy, str):
        template_inline_policy = json.loads(template_inline_policy)

    if existing_inline_policy:
        if isinstance(existing_inline_policy, str):
            existing_inline_policy = json.loads(existing_inline_policy)

        policy_drift = await aio_wrapper(
            DeepDiff,
            existing_inline_policy,
            template_inline_policy,
            report_repetition=True,
            ignore_order=True,
        )

    if template_inline_policy and (not existing_inline_policy or bool(policy_drift)):
        log_str = "Changes to the InlinePolicyDocument discovered."
        if policy_drift:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.UPDATE,
                    attribute="inline_policy_document",
                    resource_id=permission_set_arn,
                    resource_type="aws:identity_center:permission_set",
                    change_summary=policy_drift,
                    current_value=existing_inline_policy,
                    new_value=template_inline_policy,
                )
            )
        else:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.CREATE,
                    resource_type="aws:identity_center:permission_set",
                    resource_id=permission_set_arn,
                    attribute="inline_policy_document",
                    new_value=template_inline_policy,
                )
            )

        if ctx.execute:
            boto_action = "Creating" if not existing_inline_policy else "Updating"
            log_str = f"{log_str} {boto_action} InlinePolicyDocument..."
            apply_awaitable = boto_crud_call(
                identity_center_client.put_inline_policy_to_permission_set,
                InstanceArn=instance_arn,
                PermissionSetArn=permission_set_arn,
                InlinePolicy=json.dumps(template_inline_policy),
            )
            response = await plugin_apply_wrapper(apply_awaitable, response)

        log.debug(log_str, **log_params)
    elif not template_inline_policy and existing_inline_policy:
        log_str = "Stale InlinePolicyDocument."
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.DELETE,
                attribute="inline_policy",
                resource_type="aws:identity_center:permission_set",
                resource_id=permission_set_arn,
                current_value=existing_inline_policy,
            )
        )
        if ctx.execute:
            log_str = f"{log_str} Removing InlinePolicyDocument..."
            apply_awaitable = boto_crud_call(
                identity_center_client.delete_inline_policy_from_permission_set,
                InstanceArn=instance_arn,
                PermissionSetArn=permission_set_arn,
            )
            response = await plugin_apply_wrapper(apply_awaitable, response)

        log.debug(log_str, **log_params)

    return response


async def apply_permission_set_permission_boundary(
    identity_center_client,
    instance_arn: str,
    permission_set_arn: str,
    template_permission_boundary: dict,
    existing_permission_boundary: dict,
    log_params: dict,
) -> list[ProposedChange]:
    response = []
    policy_drift = None

    if existing_permission_boundary:
        policy_drift = await aio_wrapper(
            DeepDiff,
            existing_permission_boundary,
            template_permission_boundary,
            report_repetition=True,
            ignore_order=True,
        )

    if template_permission_boundary and (
        not existing_permission_boundary or bool(policy_drift)
    ):
        log_str = "Changes to the PermissionsBoundary discovered."
        if policy_drift:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.UPDATE,
                    attribute="permissions_boundary",
                    resource_type="aws:identity_center:permission_set",
                    resource_id=permission_set_arn,
                    change_summary=policy_drift,
                    current_value=existing_permission_boundary,
                    new_value=template_permission_boundary,
                )
            )
        else:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.ATTACH,
                    resource_type="aws:identity_center:permission_set",
                    resource_id=permission_set_arn,
                    attribute="permissions_boundary",
                    new_value=template_permission_boundary,
                )
            )

        if ctx.execute:
            boto_action = "Creating" if not existing_permission_boundary else "Updating"
            log_str = f"{log_str} {boto_action} PermissionsBoundary..."
            apply_awaitable = boto_crud_call(
                identity_center_client.put_permissions_boundary_to_permission_set,
                InstanceArn=instance_arn,
                PermissionSetArn=permission_set_arn,
                PermissionsBoundary=template_permission_boundary,
            )
            response = await plugin_apply_wrapper(apply_awaitable, response)

        log.debug(log_str, **log_params)
    elif existing_permission_boundary and not template_permission_boundary:
        log_str = "Removing PermissionsBoundary discovered."
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.DETACH,
                resource_type="aws:identity_center:permission_set",
                resource_id=permission_set_arn,
                attribute="permissions_boundary",
                current_value=existing_permission_boundary,
            )
        )

        if ctx.execute:
            log_str = f"{log_str} Deleting PermissionsBoundary..."
            apply_awaitable = boto_crud_call(
                identity_center_client.delete_permissions_boundary_from_permission_set,
                InstanceArn=instance_arn,
                PermissionSetArn=permission_set_arn,
            )
            response = await plugin_apply_wrapper(apply_awaitable, response)

        log.debug(log_str, **log_params)

    return response


async def apply_permission_set_tags(
    identity_center_client,
    instance_arn: str,
    permission_set_arn: str,
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
                resource_type="aws:identity_center:permission_set",
                resource_id=permission_set_arn,
                attribute="tags",
                change_summary={"TagKeys": tags_to_remove},
            )
        ]
        response.extend(proposed_changes)
        if ctx.execute:
            log_str = f"{log_str} Removing tags..."
            apply_awaitable = boto_crud_call(
                identity_center_client.untag_resource,
                InstanceArn=instance_arn,
                ResourceArn=permission_set_arn,
                TagKeys=tags_to_remove,
            )
            tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
        log.debug(log_str, tags=tags_to_remove, **log_params)

    if tags_to_apply:
        log_str = "New tags discovered in AWS."
        proposed_changes = [
            ProposedChange(
                change_type=ProposedChangeType.ATTACH,
                resource_type="aws:identity_center:permission_set",
                resource_id=permission_set_arn,
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
                identity_center_client.tag_resource,
                InstanceArn=instance_arn,
                ResourceArn=permission_set_arn,
                Tags=tags_to_apply,
            )
            tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
        log.debug(log_str, tags=tags_to_apply, **log_params)

    if tasks:
        results: list[list[ProposedChange]] = await asyncio.gather(*tasks)
        return list(chain.from_iterable(results))
    else:
        return response


async def delete_permission_set(
    identity_center_client,
    instance_arn: str,
    permission_set_arn: str,
    current_permission_set: dict,
    account_assignments: list[dict],
    log_params: dict,
):
    tasks = []
    managed_policies = [
        mp["Arn"] for mp in current_permission_set.get("ManagedPolicies", [])
    ]
    customer_managed_policy_references = current_permission_set.get(
        "CustomerManagedPolicyReferences"
    )
    permissions_boundary = current_permission_set.get("PermissionsBoundary")
    inline_policy = current_permission_set.get("InlinePolicy")
    tags = current_permission_set.get("Tags")

    if account_assignments:
        log_params["account_assignments"] = account_assignments
        for assignment in account_assignments:
            tasks.append(
                delete_account_assignment(
                    identity_center_client,
                    account_id=assignment["account_id"],
                    instance_arn=instance_arn,
                    permission_set_arn=permission_set_arn,
                    resource_type=assignment["resource_type"],
                    resource_id=assignment["resource_id"],
                    resource_name=assignment["resource_name"],
                    log_params=log_params,
                )
            )

    if managed_policies:
        log_params["managed_policies"] = managed_policies
        tasks.extend(
            [
                boto_crud_call(
                    identity_center_client.detach_managed_policy_from_permission_set,
                    InstanceArn=instance_arn,
                    PermissionSetArn=permission_set_arn,
                    ManagedPolicyArn=policy_arn,
                )
                for policy_arn in managed_policies
            ]
        )
    if customer_managed_policy_references:
        log_params[
            "customer_managed_policy_references"
        ] = customer_managed_policy_references
        tasks.extend(
            [
                boto_crud_call(
                    identity_center_client.detach_customer_managed_policy_reference_from_permission_set,
                    retryable_errors=["ConflictException"],
                    InstanceArn=instance_arn,
                    PermissionSetArn=permission_set_arn,
                    CustomerManagedPolicyReference=policy,
                )
                for policy in customer_managed_policy_references
            ]
        )
    if permissions_boundary:
        log_params["permissions_boundary"] = permissions_boundary
        tasks.append(
            boto_crud_call(
                identity_center_client.delete_permissions_boundary_from_permission_set,
                InstanceArn=instance_arn,
                PermissionSetArn=permission_set_arn,
            )
        )
    if inline_policy:
        log_params["inline_policy"] = inline_policy
        tasks.append(
            boto_crud_call(
                identity_center_client.delete_inline_policy_from_permission_set,
                InstanceArn=instance_arn,
                PermissionSetArn=permission_set_arn,
            )
        )
    if tags:
        log_params["tags"] = tags
        tags_to_remove = [tag["Key"] for tag in tags]
        tasks.append(
            boto_crud_call(
                identity_center_client.untag_resource,
                InstanceArn=instance_arn,
                ResourceArn=permission_set_arn,
                TagKeys=tags_to_remove,
            )
        )

    log.debug(
        "Detaching resources from the permission set.",
        permission_set_arn=permission_set_arn,
        **log_params,
    )
    await async_batch_processor(tasks, 10, 1)

    retry_count = 0
    while True:
        try:
            await boto_crud_call(
                identity_center_client.delete_permission_set,
                InstanceArn=instance_arn,
                PermissionSetArn=permission_set_arn,
            )
        except ClientError as err:
            err_response = err.response["Error"]
            if (
                "PermissionSet has ApplicationProfile associated with it."
                in err_response["Message"]
            ) and retry_count < 10:
                # Wait for the detached resources to be deleted so that the permission set can be deleted.
                log.debug(
                    "Waiting for resources to be detached from the permission set.",
                    **log_params,
                )
                retry_count += 1
                await asyncio.sleep(5)
            elif err_response["Code"] == "ResourceNotFoundException":
                return
            else:
                raise
