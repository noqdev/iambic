from __future__ import annotations

import asyncio
import json
import random
from itertools import chain

from deepdiff import DeepDiff
from git import TYPE_CHECKING
from tenacity import retry, stop_after_attempt, wait_exponential

from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.core.utils import NoqSemaphore, aio_wrapper, plugin_apply_wrapper
from iambic.plugins.v0_1_0.aws.utils import boto_crud_call, legacy_paginated_search

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.aws.models import AWSAccount
    from iambic.plugins.v0_1_0.aws.organizations.scp.models import (
        ServiceControlPolicyItem,
        ServiceControlPolicyTargetItem,
    )


async def list_policies(
    client, filter="SERVICE_CONTROL_POLICY"
) -> list[ServiceControlPolicyItem]:
    """Retrieves the list of all policies in an organization of a specified type."""

    from iambic.plugins.v0_1_0.aws.organizations.scp.models import (
        ServiceControlPolicyItem,
    )

    scp_policies = await legacy_paginated_search(
        client.list_policies,
        response_key="Policies",
        **dict(Filter=filter),
    )

    scp_policies = [p for p in scp_policies if p["AwsManaged"] is False]

    list_targets_for_policy_semaphore = NoqSemaphore(list_targets_for_policy, 10)
    describe_policy_semaphore = NoqSemaphore(get_policy_statements, 10)
    list_tags_by_policy_semaphore = NoqSemaphore(list_tags_by_policy, 10)

    targets = await list_targets_for_policy_semaphore.process(
        [{"client": client, "policyId": policy["Id"]} for policy in scp_policies]
    )

    statements = await describe_policy_semaphore.process(
        [{"client": client, "policyId": policy["Id"]} for policy in scp_policies]
    )

    tags = await list_tags_by_policy_semaphore.process(
        [{"client": client, "policyId": policy["Id"]} for policy in scp_policies]
    )

    return [
        ServiceControlPolicyItem.parse_obj(
            {
                **p,
                "Targets": t,
                "PolicyDocument": s,
                "Tags": tg,
            },
        )
        for p, t, s, tg in zip(scp_policies, targets, statements, tags)
    ]


@retry(
    reraise=True,
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=4, max=15),
)
async def list_targets_for_policy(
    client, policyId: str
) -> list[ServiceControlPolicyTargetItem]:
    """
    Lists all the roots, organizational units (OUs),
    and accounts that the specified policy is attached to.
    """
    from iambic.plugins.v0_1_0.aws.organizations.scp.models import (
        ServiceControlPolicyTargetItem,
    )

    targets = await legacy_paginated_search(
        client.list_targets_for_policy,
        response_key="Targets",
        **dict(PolicyId=policyId),
    )

    return [ServiceControlPolicyTargetItem.parse_obj(t) for t in targets]


async def get_policy_statements(client, policyId: str):
    policy = await describe_policy(client, policyId)
    return policy.get("Content", {})


@retry(
    reraise=True,
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=4, max=15),
)
async def describe_policy(client, policyId: str):
    from iambic.plugins.v0_1_0.aws.organizations.scp.models import PolicyDocumentItem

    res = await boto_crud_call(client.describe_policy, PolicyId=policyId)
    return dict(
        PolicySummary=res.get("Policy", {}).get("PolicySummary", {}),
        Content=PolicyDocumentItem.parse_obj(
            json.loads(res.get("Policy", {}).get("Content", {}))
        ),
    )


@retry(
    reraise=True,
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=4, max=15),
)
async def list_tags_by_policy(client, policyId: str) -> list[dict]:
    """
    Lists tags that are attached to the specified resource.
    """
    targets = await legacy_paginated_search(
        client.list_tags_for_resource,
        response_key="Tags",
        **dict(ResourceId=policyId),
    )

    return targets


async def get_policy(client, policyId: str) -> ServiceControlPolicyItem:
    from iambic.plugins.v0_1_0.aws.organizations.scp.models import (
        ServiceControlPolicyItem,
    )

    policy = await describe_policy(client, policyId)

    list_tags_by_policy_semaphore = NoqSemaphore(list_tags_by_policy, 10)
    list_targets_for_policy_semaphore = NoqSemaphore(list_targets_for_policy, 10)

    tags = await list_tags_by_policy_semaphore.process(
        [{"client": client, "policyId": policyId}]
    )

    targets = await list_targets_for_policy_semaphore.process(
        [{"client": client, "policyId": policyId}]
    )

    return ServiceControlPolicyItem.parse_obj(
        {
            **policy.get("PolicySummary", {}),  # type: ignore
            "Targets": targets[0],
            "PolicyDocument": policy.get("Content", {}),
            "Tags": tags[0],
        },
    )


@retry(
    reraise=True,
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=4, max=15),
)
async def detach_policy(client, policyId, targetId):
    await boto_crud_call(
        client.detach_policy,
        PolicyId=policyId,
        TargetId=targetId,
    )
    log.debug(f"Detached policy {policyId} from {targetId}")


@retry(
    reraise=True,
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=5, max=20),
)
async def delete_policy(client, policyId: str, *args, **kwargs):
    """
    Deletes the specified policy from your organization.
    Before you perform this operation, you must first detach
    the policy from all organizational units (OUs), roots, and accounts.
    """
    list_targets_for_policy_semaphore = NoqSemaphore(list_targets_for_policy, 10)

    targets = chain.from_iterable(
        await list_targets_for_policy_semaphore.process(
            [{"client": client, "policyId": policyId}]
        )
    )

    targets_tasks = [
        detach_policy(client, policyId, target.TargetId) for target in targets
    ]

    await asyncio.gather(*targets_tasks)

    await boto_crud_call(client.delete_policy, PolicyId=policyId)

    log.debug(f"Deleted policy {policyId}")


@retry(
    reraise=True,
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=4, max=15),
)
async def create_policy(client, policy):
    if isinstance(policy["PolicyDocument"], dict):
        policy["PolicyDocument"] = json.dumps(policy["PolicyDocument"])

    res = await boto_crud_call(
        client.create_policy,
        Content=policy["PolicyDocument"],
        Description=policy.get("Description", ""),
        Name=policy.get("PolicyName", f"NewPolicy-{random.randint(0, 100):03d}"),
        Type="SERVICE_CONTROL_POLICY",
    )

    policy.update(
        PolicyId=res.get("Policy", {}).get("PolicySummary", {}).get("Id"),
        PolicyName=res.get("Policy", {}).get("PolicySummary", {}).get("Name"),
    )

    return res.get("Policy", {}).get("PolicySummary", {})


@retry(
    reraise=True,
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=5, max=20),
)
async def describe_organization(
    client,
):
    """Retrieves information about the organization that the user's account belongs to.
    This operation can be called from any account in the organization.
    """
    res = await boto_crud_call(client.describe_organization)
    return res.get("Organization", {})


async def service_control_policy_is_enabled(client):
    """Check if SCPs are enabled for the organization."""
    org = await describe_organization(client)

    return (
        len(
            [
                apt
                for apt in org.get("AvailablePolicyTypes", [])
                if apt.get("Type") == "SERVICE_CONTROL_POLICY"
                and apt.get("Status") == "ENABLED"
            ]
        )
        > 0
    )


@retry(
    reraise=True,
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=4, max=15),
)
async def apply_update_policy(
    client,
    policy,
    current_policy,
    log_params,
    *args,
) -> list[ProposedChange]:
    """Apply update policy.

    Args:
        client: organization client
        policy: policy read from yaml
        current_policy (dict): Response from boto3, based on ServiceControlPolicyItem.
        log_params (dict):

    Returns:
        list[ProposedChange]: list of proposed changes
    """

    from iambic.plugins.v0_1_0.aws.organizations.scp.models import PolicyDocumentItem

    current_value = dict(
        Name=current_policy.get("Name"),
        Description=current_policy.get("Description"),
        Content=current_policy["PolicyDocument"],
    )

    new_value = dict(
        Name=policy.get("PolicyName"),
        Description=policy.get("Description"),
        Content=PolicyDocumentItem.parse_obj(policy["PolicyDocument"]).dict(),
    )

    diff = await aio_wrapper(
        DeepDiff,
        current_value,
        new_value,
        report_repetition=True,
        ignore_order=True,
        exclude_regex_paths=["metadata_commented_dict"],
    )

    if diff == {}:
        return []

    tasks = []
    policy = policy.copy()

    if isinstance(policy["PolicyDocument"], dict):
        policy["PolicyDocument"] = json.dumps(policy["PolicyDocument"])

    proposed_changes = [
        ProposedChange(
            change_type=ProposedChangeType.UPDATE,
            resource_type=log_params.get("resource_type"),
            resource_id=policy.get("Name"),
            change_summary=diff.to_dict(),
            current_value=current_value,
            new_value=new_value,
        )  # type: ignore
    ]

    if ctx.execute:
        apply_awaitable = boto_crud_call(
            client.update_policy,
            PolicyId=policy.get("PolicyId"),
            Name=policy.get("PolicyName", f"NewPolicy-{random.randint(0, 100):03d}"),
            Description=policy.get("Description", ""),
            Content=policy["PolicyDocument"],
        )

        tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))

    if tasks:
        results: list[list[ProposedChange]] = await asyncio.gather(*tasks)
        return list(chain.from_iterable(results))
    else:
        return proposed_changes


async def apply_update_policy_targets(
    client,
    policy,
    current_policy,
    log_params,
    aws_account: AWSAccount,
    *args,
) -> list[ProposedChange]:
    """Apply update policy targets.

    Args:
        client: organization client
        policy: policy read from yaml
        current_policy (dict): Response from boto3, based on ServiceControlPolicyItem.
        log_params (dict):

    Returns:
        list[ProposedChange]: list of proposed changes
    """
    tasks = []
    response = []

    t, r = __remove_targets(
        client,
        policy,
        current_policy,
        log_params,
        aws_account,
    )

    tasks += t
    response += r

    t, r = __apply_targets(
        client,
        policy,
        current_policy,
        log_params,
        aws_account,
    )

    tasks += t
    response += r

    if tasks:
        results: list[list[ProposedChange]] = await asyncio.gather(*tasks)
        return list(chain.from_iterable(results))
    else:
        return response


async def apply_update_policy_tags(
    client,
    policy,
    current_policy,
    log_params,
    *args,
) -> list[ProposedChange]:
    """Apply update policy tags.

    Args:
        client: organization client
        policy: policy read from yaml
        current_policy (dict): Response from boto3, based on ServiceControlPolicyItem.
        log_params (dict):

    Returns:
        list[ProposedChange]: list of proposed changes
    """

    tasks = []
    response = []

    t, r = __remove_tags(
        client,
        policy,
        current_policy,
        log_params,
    )

    tasks += t
    response += r

    t, r = __apply_tags(
        client,
        policy,
        current_policy,
        log_params,
    )

    tasks += t
    response += r

    if tasks:
        results: list[list[ProposedChange]] = await asyncio.gather(*tasks)
        return list(chain.from_iterable(results))
    else:
        return response


@retry(
    reraise=True,
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=4, max=15),
)
def __apply_tags(
    client,
    policy,
    current_policy,
    log_params,
):
    """Apply tags to policy"""
    response = []
    tasks = []
    existing_tag_map = {
        tag["Key"]: tag.get("Value") for tag in current_policy.get("Tags", [])
    }

    tags_to_apply = [
        tag
        for tag in policy.get("Tags", [])
        if tag.get("Value") != existing_tag_map.get(tag["Key"])
    ]

    if tags_to_apply:
        log_str = "New tags discovered in AWS."
        proposed_changes = [
            ProposedChange(
                change_type=ProposedChangeType.ATTACH,
                resource_type=log_params.get("resource_type"),
                resource_id=policy.get("Name"),
                attribute="tags",
                current_value=[],
                new_value=tags_to_apply,
            )  # type: ignore
        ]
        response.extend(proposed_changes)
        if ctx.execute:
            log_str = f"{log_str} Adding tags..."
            apply_awaitable = boto_crud_call(
                client.tag_resource,
                ResourceId=policy.get("PolicyId"),
                Tags=tags_to_apply,
            )
            tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
        log.debug(log_str, tags=tags_to_apply, **log_params)

    return tasks, response


@retry(
    reraise=True,
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=4, max=15),
)
def __remove_tags(client, policy, current_policy, log_params):
    """Remove tags from the policy that are not in the template."""
    response = []
    tasks = []
    template_tag_map = {tag["Key"]: tag.get("Value") for tag in policy.get("Tags", [])}

    if tags_to_remove := [
        tag["Key"]
        for tag in current_policy.get("Tags", [])
        if not template_tag_map.get(tag["Key"])
    ]:
        log_str = "Stale tags discovered."
        proposed_changes = [
            ProposedChange(
                change_type=ProposedChangeType.DETACH,
                attribute="tags",
                resource_type=log_params.get("resource_type"),
                resource_id=policy.get("Name"),
                current_value=tags_to_remove,
                new_value=[],
                change_summary={"TagKeys": tags_to_remove},
            )  # type: ignore
        ]
        response.extend(proposed_changes)

        if ctx.execute:
            log_str = f"{log_str} Removing tags..."
            apply_awaitable = boto_crud_call(
                client.untag_resource,
                ResourceId=policy.get("PolicyId"),
                TagKeys=tags_to_remove,
            )
            tasks.append(plugin_apply_wrapper(apply_awaitable, proposed_changes))
        log.debug(log_str, tags=tags_to_remove, **log_params)

    return tasks, response


@retry(
    reraise=True,
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=4, max=15),
)
def __apply_targets(
    client,
    policy,
    current_policy,
    log_params,
    aws_account: AWSAccount,
):
    """Apply targets to policy."""
    from iambic.plugins.v0_1_0.aws.organizations.scp.models import (
        PolicyTargetProperties,
    )

    response = []
    tasks = []

    targets = list(
        chain.from_iterable(
            policy.get(
                "Targets", dict(OrganizationalUnits=[], Accounts=[], Roots=[])
            ).values()
        )
    )
    targets = PolicyTargetProperties.unparse_targets(targets, aws_account.aws_config)

    current_targets = list(
        map(lambda t: t.get("TargetId"), current_policy.get("Targets"))
    )

    if targets_to_apply := [tag for tag in targets if tag not in current_targets]:
        log_str = "New targets discovered."
        proposed_changes = [
            ProposedChange(
                change_type=ProposedChangeType.ATTACH,
                resource_type=log_params.get("resource_type"),
                resource_id=policy.get("Name"),
                attribute="targets",
                current_value=current_targets,
                new_value=current_targets + targets_to_apply,
            )  # type: ignore
        ]
        response.extend(proposed_changes)
        if ctx.execute:
            log_str = f"{log_str} Adding targets..."

            async def attach_policies():
                """Due to ConcurrentModificationException, we need to execute it one at a time."""
                for target in targets_to_apply:
                    await boto_crud_call(
                        client.attach_policy,
                        PolicyId=policy.get("PolicyId"),
                        TargetId=target,
                    )

            tasks.append(plugin_apply_wrapper(attach_policies(), proposed_changes))

        log.debug(log_str, tags=targets_to_apply, **log_params)

    return tasks, response


@retry(
    reraise=True,
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=4, max=15),
)
def __remove_targets(
    client,
    policy,
    current_policy,
    log_params,
    aws_account: AWSAccount,
):
    """Remove targets from policy that are not in the template."""
    from iambic.plugins.v0_1_0.aws.organizations.scp.models import (
        PolicyTargetProperties,
    )

    response = []
    tasks = []

    targets = list(
        chain.from_iterable(
            policy.get(
                "Targets", dict(OrganizationalUnits=[], Accounts=[], Roots=[])
            ).values()
        )
    )
    targets = PolicyTargetProperties.unparse_targets(targets, aws_account.aws_config)

    current_targets = list(
        map(lambda t: t.get("TargetId"), current_policy.get("Targets"))
    )

    if targets_to_remove := [
        target for target in current_targets if target not in targets
    ]:
        log_str = "Stale targets discovered."
        proposed_changes = [
            ProposedChange(
                change_type=ProposedChangeType.DETACH,
                attribute="targets",
                resource_type=log_params.get("resource_type"),
                resource_id=policy.get("Name"),
                current_value=targets_to_remove,
                new_value=[],
                change_summary={"Targets": targets_to_remove},
            )  # type: ignore
        ]
        response.extend(proposed_changes)

        if ctx.execute:
            log_str = f"{log_str} Removing targets..."

            async def detach_policies():
                """Due to ConcurrentModificationException, we need to execute it one at a time."""
                for target in targets_to_remove:
                    await boto_crud_call(
                        client.detach_policy,
                        PolicyId=policy.get("PolicyId"),
                        TargetId=target,
                    )

            tasks.append(plugin_apply_wrapper(detach_policies(), proposed_changes))
        log.debug(log_str, tags=targets_to_remove, **log_params)

    return tasks, response
