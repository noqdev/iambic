import asyncio

from iambic.aws.models import AWSAccount
from iambic.aws.sso.permission_set.models import AWSSSOPermissionSetTemplate, AWS_SSO_PERMISSION_SET_TEMPLATE_TYPE
from iambic.aws.utils import legacy_paginated_search
from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.core.utils import aio_wrapper


async def generate_permission_set_map(
        aws_accounts: list[AWSAccount], templates: list
):
    """Generates the map of permission sets for AWS accounts that are referenced in at least 1 template

    :param aws_accounts:
    :param templates:
    :return:
    """
    org_include_set = set()
    include_all = False
    accounts_to_set_sso = []

    for template in templates:
        if template.template_type == AWS_SSO_PERMISSION_SET_TEMPLATE_TYPE:
            for org in template.included_orgs:
                if org == "*":
                    include_all = True
                    break
                org_include_set.add(org)

        if include_all:
            break

    for aws_account in aws_accounts:
        if (include_all or aws_account.org_id in org_include_set) and aws_account.sso_details:
            accounts_to_set_sso.append(aws_account)

    await asyncio.gather(*[account.set_sso_details() for account in accounts_to_set_sso])


async def enrich_permission_set_details(sso_client, instance_arn: str, permission_set_details: dict):
    permission_set_arn = permission_set_details["PermissionSetArn"]
    query_params = dict(InstanceArn=instance_arn, PermissionSetArn=permission_set_arn)
    tasks = [
        aio_wrapper(
            sso_client.get_inline_policy_for_permission_set,
            **query_params
        ),
        aio_wrapper(
            sso_client.get_permissions_boundary_for_permission_set,
            **query_params
        ),
        legacy_paginated_search(
            sso_client.list_customer_managed_policy_references_in_permission_set,
            response_key="CustomerManagedPolicyReferences",
            retain_key=True,
            **query_params
        ),
        legacy_paginated_search(
            sso_client.list_managed_policies_in_permission_set,
            response_key="AttachedManagedPolicies",
            retain_key=True,
            **query_params
        ),
        legacy_paginated_search(
            sso_client.list_accounts_for_provisioned_permission_set,
            response_key="AccountIds",
            retain_key=True,
            **query_params
        ),
        legacy_paginated_search(
            sso_client.list_tags_for_resource,
            response_key="Tags",
            retain_key=True,
            InstanceArn=instance_arn,
            ResourceArn=permission_set_arn
        ),
    ]
    permission_set_responses = await asyncio.gather(*tasks, return_exceptions=True)
    for permission_set_response in permission_set_responses:
        if isinstance(permission_set_response, Exception):
            continue

        for k, v in permission_set_response.items():
            if v and k != "ResponseMetadata":
                permission_set_details[k] = v

    return permission_set_details


async def apply_permission_set_aws_managed_policies(
    sso_client,
    instance_arn: str,
    permission_set_arn: str,
    template_policy_arns: list[str],
    existing_policy_arns: list[str],
    log_params: dict,
    context: ExecutionContext,
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
        for policy_arn in new_managed_policies:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.ATTACH,
                    resource_id=policy_arn,
                    attribute="managed_policies",
                )
            )
        if context.execute:
            log_str = f"{log_str} Attaching AWS managed policies..."
            tasks = [
                aio_wrapper(
                    sso_client.attach_managed_policy_to_permission_set,
                    InstanceArn=instance_arn,
                    PermissionSetArn=permission_set_arn,
                    PolicyArn=policy_arn,
                )
                for policy_arn in new_managed_policies
            ]
        log.info(log_str, managed_policies=new_managed_policies, **log_params)

    # Delete existing managed policies not in template
    existing_managed_policies = [
        policy_arn
        for policy_arn in existing_policy_arns
        if policy_arn not in template_policy_arns
    ]
    if existing_managed_policies:
        log_str = "Stale AWS managed policies discovered."
        for policy_arn in existing_managed_policies:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.DETACH,
                    resource_id=policy_arn,
                    attribute="managed_policies",
                )
            )
        if context.execute:
            log_str = f"{log_str} Detaching AWS managed policies..."
            tasks.extend(
                [
                    aio_wrapper(
                        sso_client.detach_managed_policy_from_permission_set,
                        InstanceArn=instance_arn,
                        PermissionSetArn=permission_set_arn,
                        PolicyArn=policy_arn,
                    )
                    for policy_arn in existing_managed_policies
                ]
            )
        log.info(log_str, managed_policies=existing_managed_policies, **log_params)

    if tasks:
        await asyncio.gather(*tasks)

    return response


async def apply_permission_set_customer_managed_policies(
    sso_client,
    instance_arn: str,
    permission_set_arn: str,
    template_policies: list[dict],
    existing_policies: list[dict],
    log_params: dict,
    context: ExecutionContext,
) -> list[ProposedChange]:
    tasks = []
    response = []
    template_policy_map = {f"{policy['Path']}{policy['PolicyName']}": policy for policy in template_policies}
    existing_policy_map = {f"{policy['Path']}{policy['PolicyName']}": policy for policy in existing_policies}

    # Create new managed policies
    new_managed_policies = [
        policy
        for policy_path, policy in template_policy_map.items()
        if not existing_policy_map.get(policy_path)
    ]
    if new_managed_policies:
        log_str = "New customer managed policies discovered."
        for policy in new_managed_policies:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.ATTACH,
                    customer_managed_policy_reference=policy,
                    attribute="customer_managed_policies",
                )
            )
        if context.execute:
            log_str = f"{log_str} Attaching customer managed policies..."
            tasks = [
                aio_wrapper(
                    sso_client.attach_customer_managed_policy_reference_to_permission_set,
                    InstanceArn=instance_arn,
                    PermissionSetArn=permission_set_arn,
                    CustomerManagedPolicyReference=policy,
                )
                for policy in new_managed_policies
            ]
        log.info(log_str, managed_policies=new_managed_policies, **log_params)

    # Delete existing managed policies not in template
    existing_managed_policies = [
        policy
        for policy_path, policy in existing_policy_map.items()
        if not template_policy_map.get(policy_path)
    ]
    if existing_managed_policies:
        log_str = "Stale customer managed policies discovered."
        for policy in existing_managed_policies:
            response.append(
                ProposedChange(
                    change_type=ProposedChangeType.DETACH,
                    customer_managed_policy_reference=policy,
                    attribute="customer_managed_policies",
                )
            )
        if context.execute:
            log_str = f"{log_str} Detaching customer managed policies..."
            tasks.extend(
                [
                    aio_wrapper(
                        sso_client.detach_customer_managed_policy_reference_from_permission_set,
                        InstanceArn=instance_arn,
                        PermissionSetArn=permission_set_arn,
                        CustomerManagedPolicyReference=policy,
                    )
                    for policy in existing_managed_policies
                ]
            )
        log.info(log_str, managed_policies=existing_managed_policies, **log_params)

    if tasks:
        await asyncio.gather(*tasks)

    return response


async def apply_account_assignments(
    sso_client,
    instance_arn: str,
    permission_set_arn: str,
    template_assignments: list[dict],
    existing_assignments: list[dict],
    log_params: dict,
    context: ExecutionContext,
) -> list[ProposedChange]:
    ...


async def apply_permission_set_inline_policy(
    sso_client,
    instance_arn: str,
    permission_set_arn: str,
    template_inline_policy: str,
    existing_inline_policy: str,
    log_params: dict,
    context: ExecutionContext,
) -> list[ProposedChange]:
    ...


async def apply_permission_set_permission_boundary(
    sso_client,
    instance_arn: str,
    permission_set_arn: str,
    template_permission_boundary: any,  # TODO: Fix type hint
    existing_permission_boundary: any,  # TODO: Fix type hint
    log_params: dict,
    context: ExecutionContext,
) -> list[ProposedChange]:
    ...


async def create_permission_set(
    sso_client,
    instance_arn: str,
    permission_set: dict,
    log_params: dict,
    context: ExecutionContext,
) -> list[ProposedChange]:
    ...


async def delete_permission_set(
    sso_client,
    instance_arn: str,
    permission_set: dict,
    log_params: dict,
    context: ExecutionContext,
) -> list[ProposedChange]:
    ...



